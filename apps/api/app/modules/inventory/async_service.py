"""
InventoryService async (Fase 3+): usa MovementEngine, sin SQLiteDatabase legacy.

Esta es la VERSION ASYNC del InventoryService. Toda escritura de stock
pasa por ``MovementEngine`` (Regla R4: único punto de escritura de
``stock_levels``). El legacy ``service.py`` (sync) se eliminó en la
migración a ``Depends(get_session)``.

API pública:
- ``register_movement`` (escribe via MovementEngine)
- ``list_stock`` (JOIN stock_levels + warehouses + products)
- ``get_stock`` / ``get_stock_with_lock`` (lectura directa del modelo)
- ``list_movements`` (JOIN inventory_movements + warehouses + products)
- ``get_summary`` (counts agregados para /inventory/summary)
- ``upsert_stock_parameters`` (Fase 8: parametrización min/max por bodega x producto)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.db.models.inventory import InventoryMovement, MovementType, StockLevel
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from app.modules.inventory.repository import InventoryRepository
from app.shared.movement_engine import MovementEngine, MovementRequest, MovementResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.inventory.schemas import MovementType as MovementTypeSchema

log = get_logger(__name__)


@dataclass(slots=True)
class StockLevelView:
    warehouse_id: uuid.UUID
    warehouse_code: str
    warehouse_name: str
    product_id: uuid.UUID
    product_sku: str
    product_name: str
    quantity: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
    updated_at: datetime


@dataclass(slots=True)
class InventoryMovementView:
    id: uuid.UUID
    warehouse_id: uuid.UUID
    warehouse_code: str
    product_id: uuid.UUID
    product_sku: str
    movement_type: MovementType
    quantity: Decimal
    reference_type: str | None
    reference_id: str | None
    notes: str | None
    created_at: datetime


@dataclass(slots=True)
class StockParametersView:
    """Vista de los parámetros de un (producto, bodega) específico (Fase 8)."""

    id: uuid.UUID
    warehouse_id: uuid.UUID
    warehouse_code: str
    product_id: uuid.UUID
    product_sku: str
    quantity: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
    updated_at: datetime


@dataclass(slots=True)
class InventorySummaryView:
    """Resumen del estado del inventario (para /inventory/summary)."""

    warehouses: int
    products: int
    stock_records: int
    movements: int
    low_stock_alerts: int


class InventoryServiceAsync:
    """InventoryService versión async (Fase 3+)."""

    def __init__(
        self,
        session: AsyncSession,
        repository: InventoryRepository | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or InventoryRepository(session)
        self._movement = MovementEngine(session)

    # ====================================================== REGISTER MOVEMENT

    async def register_movement(
        self,
        *,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        movement_type: MovementType,
        quantity: Decimal,
        reference_type: str | None = None,
        reference_id: str | None = None,
        notes: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> MovementResult:
        """Registra un movimiento de stock usando MovementEngine."""
        result = await self._movement.apply(
            MovementRequest(
                warehouse_id=warehouse_id,
                product_id=product_id,
                movement_type=movement_type,
                quantity=quantity,
                reference_type=reference_type,
                reference_id=reference_id,
                notes=notes,
                user_id=user_id,
            )
        )
        await self._session.commit()
        return result

    # ============================================================ LIST STOCK

    async def list_stock(
        self,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        sku: str | None = None,
    ) -> list[StockLevelView]:
        """Lista stock con JOIN a warehouses y products.

        Si ``sku`` viene, primero resuelve el product_id y filtra
        (evita listar stock de productos inactivos o sin match).
        """
        resolved_product_id: uuid.UUID | None = product_id
        filter_matches = True
        if sku is not None:
            stmt = select(Product).where(Product.sku == sku.strip().upper())
            product = (await self._session.execute(stmt)).scalar_one_or_none()
            if product is None:
                filter_matches = False
            else:
                resolved_product_id = product.id

        if not filter_matches:
            return []

        rows = await self._repository.list_stock_levels_with_joins(
            warehouse_id=warehouse_id, product_id=resolved_product_id
        )
        return [
            StockLevelView(
                warehouse_id=sl.warehouse_id,
                warehouse_code=w.code,
                warehouse_name=w.name,
                product_id=sl.product_id,
                product_sku=p.sku,
                product_name=p.name,
                quantity=sl.quantity,
                min_quantity=sl.min_quantity,
                max_quantity=sl.max_quantity,
                updated_at=sl.updated_at,
            )
            for sl, w, p in rows
        ]

    async def get_stock(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> StockLevel | None:
        """Lee el stock actual de (warehouse, product) SIN lock."""
        return await self._repository.get_stock_level(warehouse_id, product_id)

    async def get_stock_with_lock(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> StockLevel | None:
        """Lee el stock actual CON SELECT FOR UPDATE.

        Útil cuando el caller quiere hacer el lock explícitamente,
        sin pasar por MovementEngine (e.g. lectura previa + lógica custom).
        """
        stmt = (
            select(StockLevel)
            .where(
                StockLevel.warehouse_id == warehouse_id,
                StockLevel.product_id == product_id,
            )
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ============================================================ MOVEMENTS

    async def list_movements(
        self,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        sku: str | None = None,
        movement_type: MovementType | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[InventoryMovementView]:
        """Lista movements con JOIN a warehouses y products."""
        resolved_product_id: uuid.UUID | None = product_id
        if sku is not None:
            stmt = select(Product).where(Product.sku == sku.strip().upper())
            product = (await self._session.execute(stmt)).scalar_one_or_none()
            if product is None:
                return []
            resolved_product_id = product.id

        rows = await self._repository.list_movements(
            warehouse_id=warehouse_id,
            product_id=resolved_product_id,
            movement_type=movement_type,
            created_from=created_from,
            created_to=created_to,
        )
        return [
            InventoryMovementView(
                id=m.id,
                warehouse_id=m.warehouse_id,
                warehouse_code=w.code,
                product_id=m.product_id,
                product_sku=p.sku,
                movement_type=m.movement_type,
                quantity=m.quantity,
                reference_type=m.reference_type,
                reference_id=m.reference_id,
                notes=m.notes,
                created_at=m.created_at,
            )
            for m, w, p in rows
        ]

    # ============================================================ SUMMARY

    async def get_summary(self) -> InventorySummaryView:
        return InventorySummaryView(
            warehouses=await self._repository.count_warehouses(),
            products=await self._repository.count_products(),
            stock_records=await self._repository.count_stock_records(),
            movements=await self._repository.count_movements(),
            low_stock_alerts=await self._repository.count_low_stock_alerts(),
        )

    # ====================================================== STOCK PARAMETERS (Fase 8)

    async def upsert_stock_parameters(
        self,
        *,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        min_quantity: Decimal,
        max_quantity: Decimal | None,
    ) -> StockParametersView:
        """Crea o actualiza ``(min, max)`` para (product, warehouse).

        Reglas:
        - max >= min (sino InvalidStockParameterError).
        - warehouse y product deben existir (sino 404).
        - Devuelve la vista final con sku/cantidad actual.
        """
        from app.core.errors import (
            InvalidStockParameterError,
            ProductNotFoundError,
            WarehouseNotFoundError,
        )
        from app.modules.products.repository import ProductRepository
        from app.modules.warehouses.repository import WarehouseRepository

        if max_quantity is not None and max_quantity < min_quantity:
            raise InvalidStockParameterError(min_quantity, max_quantity)

        warehouses = WarehouseRepository(self._session)
        products = ProductRepository(self._session)
        if await warehouses.get_by_id(warehouse_id) is None:
            raise WarehouseNotFoundError(str(warehouse_id))
        if await products.get_by_id(product_id) is None:
            raise ProductNotFoundError(str(product_id))

        sl = await self._repository.upsert_stock_parameters(
            warehouse_id=warehouse_id,
            product_id=product_id,
            min_quantity=min_quantity,
            max_quantity=max_quantity,
        )
        await self._session.commit()
        await self._session.refresh(sl)
        # Necesitamos el warehouse_code y product_sku para la vista.
        wh = await warehouses.get_by_id(warehouse_id)
        prod = await products.get_by_id(product_id)
        assert wh is not None  # ya validado arriba
        assert prod is not None
        return StockParametersView(
            id=sl.id,
            warehouse_id=sl.warehouse_id,
            warehouse_code=wh.code,
            product_id=sl.product_id,
            product_sku=prod.sku,
            quantity=sl.quantity,
            min_quantity=sl.min_quantity,
            max_quantity=sl.max_quantity,
            updated_at=sl.updated_at,
        )


__all__ = [
    "InventoryServiceAsync",
    "StockLevelView",
    "InventoryMovementView",
    "StockParametersView",
    "InventorySummaryView",
]
