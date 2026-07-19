"""
InventoryService async (Fase 3): usa MovementEngine.

Este servicio es la VERSIÓN ASYNC del InventoryService legacy.
Se usa en nuevos endpoints / cuando el caller tenga AsyncSession.
El legacy `service.py` (sync) sigue existiendo para compat con código
existente y se depreca gradualmente en Fases 4-5.

Regla R4: el service no llama a db.execute ni db.query directamente.
Toda la escritura de stock pasa por MovementEngine.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.db.models.inventory import StockLevel
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from app.shared.movement_engine import MovementEngine, MovementRequest, MovementResult
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.inventory.schemas import MovementType


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
    updated_at: datetime


class InventoryServiceAsync:
    """
    InventoryService versión async (Fase 3+).

    Toda escritura de stock pasa por MovementEngine.
    Las lecturas son queries directos al modelo SQLAlchemy.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        """Registra un movimiento de stock usando MovementEngine.

        Args:
            warehouse_id: bodega afectada.
            product_id: producto afectado.
            movement_type: in, out, adjustment_in, adjustment_out.
            quantity: cantidad del movimiento (siempre > 0).
            reference_type: tipo de referencia (e.g. "transfer", "purchase").
            reference_id: ID externo de la referencia.
            notes: nota libre.
            user_id: usuario que ejecuta (para audit).

        Returns:
            MovementResult con previous/new quantity y delta.

        Raises:
            WarehouseNotFoundError, ProductNotFoundError, InsufficientStockError.
        """
        engine = MovementEngine(self._session)
        result = await engine.apply(
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

    async def list_stock(
        self,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        sku: str | None = None,
    ) -> list[StockLevelView]:
        """Lista stock con JOIN a warehouses y products."""
        stmt = select(StockLevel, Warehouse, Product).join(
            Warehouse, StockLevel.warehouse_id == Warehouse.id
        ).join(
            Product, StockLevel.product_id == Product.id
        )

        if warehouse_id is not None:
            stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)
        if product_id is not None:
            stmt = stmt.where(StockLevel.product_id == product_id)
        if sku is not None:
            stmt = stmt.where(Product.sku == sku.strip().upper())

        stmt = stmt.order_by(Warehouse.code, Product.sku)
        result = await self._session.execute(stmt)
        rows = result.all()

        views: list[StockLevelView] = []
        for stock, wh, prod in rows:
            views.append(
                StockLevelView(
                    warehouse_id=stock.warehouse_id,
                    warehouse_code=wh.code,
                    warehouse_name=wh.name,
                    product_id=stock.product_id,
                    product_sku=prod.sku,
                    product_name=prod.name,
                    quantity=stock.quantity,
                    min_quantity=stock.min_quantity,
                    updated_at=stock.updated_at,
                )
            )
        return views

    async def get_stock(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
    ) -> StockLevel | None:
        """Lee el stock actual de (warehouse, product) SIN lock."""
        stmt = select(StockLevel).where(
            StockLevel.warehouse_id == warehouse_id,
            StockLevel.product_id == product_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

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
