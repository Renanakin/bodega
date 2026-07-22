"""
Repository de inventory (async, SQLAlchemy 2.0).

Operaciones sobre ``stock_levels`` (Nivel 1) e ``inventory_movements``
(ledger) usando ``AsyncSession`` y los modelos ORM.

R3/R4: las escrituras de ``quantity`` se hacen via ``MovementEngine``;
este repository solo maneja lecturas y operaciones parametrizadas
(``upsert_stock_parameters``) que NO modifican quantity.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from app.db.models.inventory import InventoryMovement, MovementType, StockLevel
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----------------------------------------------------------------- READ

    async def get_stock_level(
        self, warehouse_id: uuid.UUID, product_id: uuid.UUID
    ) -> StockLevel | None:
        stmt = select(StockLevel).where(
            StockLevel.warehouse_id == warehouse_id,
            StockLevel.product_id == product_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_stock_levels(
        self,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[StockLevel]:
        stmt = select(StockLevel)
        if warehouse_id is not None:
            stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)
        if product_id is not None:
            stmt = stmt.where(StockLevel.product_id == product_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_stock_levels_with_joins(
        self,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[tuple[StockLevel, Warehouse, Product]]:
        """JOIN con warehouses y products. Usado por list_stock / get_summary."""
        stmt = select(StockLevel, Warehouse, Product).join(
            Warehouse, StockLevel.warehouse_id == Warehouse.id
        ).join(Product, StockLevel.product_id == Product.id)
        if warehouse_id is not None:
            stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)
        if product_id is not None:
            stmt = stmt.where(StockLevel.product_id == product_id)
        stmt = stmt.order_by(Warehouse.code, Product.sku)
        result = await self._session.execute(stmt)
        return [(sl, w, p) for sl, w, p in result.all()]

    async def add_movement(self, movement: InventoryMovement) -> InventoryMovement:
        self._session.add(movement)
        await self._session.flush()
        return movement

    async def list_movements(
        self,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
        movement_type: MovementType | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[tuple[InventoryMovement, Warehouse, Product]]:
        """JOIN con warehouses y products para incluir sku/warehouse_code."""
        stmt = (
            select(InventoryMovement, Warehouse, Product)
            .join(Warehouse, InventoryMovement.warehouse_id == Warehouse.id)
            .join(Product, InventoryMovement.product_id == Product.id)
        )
        if warehouse_id is not None:
            stmt = stmt.where(InventoryMovement.warehouse_id == warehouse_id)
        if product_id is not None:
            stmt = stmt.where(InventoryMovement.product_id == product_id)
        if movement_type is not None:
            stmt = stmt.where(InventoryMovement.movement_type == movement_type)
        if created_from is not None:
            stmt = stmt.where(InventoryMovement.created_at >= created_from)
        if created_to is not None:
            stmt = stmt.where(InventoryMovement.created_at <= created_to)
        stmt = stmt.order_by(InventoryMovement.created_at.desc())
        result = await self._session.execute(stmt)
        return [(m, w, p) for m, w, p in result.all()]

    async def count_stock_records(self) -> int:
        stmt = select(func.count(StockLevel.id))
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_movements(self) -> int:
        stmt = select(func.count(InventoryMovement.id))
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_low_stock_alerts(self) -> int:
        stmt = select(func.count(StockLevel.id)).where(
            StockLevel.min_quantity > 0,
            StockLevel.quantity <= StockLevel.min_quantity,
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_warehouses(self) -> int:
        from app.db.models.warehouses import Warehouse
        stmt = select(func.count(Warehouse.id))
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_products(self) -> int:
        from app.db.models.products import Product
        stmt = select(func.count(Product.id))
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    # -------------------------------------------------------- Fase 8: params

    async def upsert_stock_parameters(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        min_quantity: Decimal,
        max_quantity: Decimal | None,
    ) -> StockLevel:
        """Crea o actualiza la tupla ``(min, max)`` de un stock_level.

        - Si la fila existe, actualiza ``min_quantity``, ``max_quantity`` y
          ``updated_at``.
        - Si NO existe, crea la fila con ``quantity=0``.

        No verifica existencia de warehouse/product: eso es responsabilidad
        del service (que ya tiene el contexto de error de dominio).
        """
        existing = await self.get_stock_level(warehouse_id, product_id)
        if existing is not None:
            existing.min_quantity = min_quantity
            existing.max_quantity = max_quantity
            await self._session.flush()
            return existing
        new_row = StockLevel(
            id=uuid.uuid4(),
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity=Decimal("0"),
            min_quantity=min_quantity,
            max_quantity=max_quantity,
        )
        self._session.add(new_row)
        await self._session.flush()
        return new_row


__all__ = ["InventoryRepository"]
