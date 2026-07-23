"""
Repository de warehouses (async, SQLAlchemy 2.0).

Acceso a datos sobre la tabla ``warehouses`` usando ``AsyncSession`` y
el modelo ORM ``Warehouse``. Versión async del repository legacy
(que usaba ``SQLiteDatabase`` + SQL crudo).

Convenciones:
- Métodos ``async def`` (await required).
- Retornan el modelo ORM ``Warehouse`` directamente.
- El caller (``WarehouseService``) hace ``await session.commit()``.
"""

from __future__ import annotations

import uuid

from app.db.models.warehouses import Warehouse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class WarehouseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----------------------------------------------------------------- READ

    async def list(
        self,
        warehouse_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[Warehouse]:
        stmt = select(Warehouse).order_by(Warehouse.code)
        if warehouse_type is not None:
            stmt = stmt.where(Warehouse.warehouse_type == warehouse_type)
        if is_active is not None:
            stmt = stmt.where(Warehouse.is_active == is_active)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        stmt = select(func.count(Warehouse.id))
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_by_id(self, warehouse_id: uuid.UUID) -> Warehouse | None:
        return await self._session.get(Warehouse, warehouse_id)

    async def get_by_code(self, code: str) -> Warehouse | None:
        stmt = select(Warehouse).where(Warehouse.code == code)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Warehouse | None:
        """Lookup por ``name``.

        La unicidad de ``name`` está enforzada por la BD (migración 0001).
        Este lookup existe para que ``WarehouseService.create_warehouse``
        devuelva un 409 limpio en vez de propagar un ``IntegrityError`` de
        Postgres cuando hay race condition entre dos requests concurrentes.
        """
        stmt = select(Warehouse).where(Warehouse.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # --------------------------------------------------------------- WRITE

    async def add(self, warehouse: Warehouse) -> Warehouse:
        self._session.add(warehouse)
        await self._session.flush()
        return warehouse


__all__ = ["WarehouseRepository"]
