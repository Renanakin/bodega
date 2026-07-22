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

    async def list(self) -> list[Warehouse]:
        stmt = select(Warehouse).order_by(Warehouse.code)
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

    # --------------------------------------------------------------- WRITE

    async def add(self, warehouse: Warehouse) -> Warehouse:
        self._session.add(warehouse)
        await self._session.flush()
        return warehouse


__all__ = ["WarehouseRepository"]
