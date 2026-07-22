"""
Service de warehouses (async).

Reglas de negocio:
- ``code`` único (la unicidad la enforza el constraint UNIQUE en la tabla
  ``warehouses``; el service verifica antes de insertar para devolver un
  409 limpio).
- Al crear, ``is_active=True`` por defecto.

Convenciones:
- Métodos ``async def``.
- ``await session.commit()`` + ``refresh()`` después de mutaciones.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.errors import DuplicateWarehouseCodeError, WarehouseNotFoundError
from app.db.models.warehouses import Warehouse
from app.modules.warehouses.repository import WarehouseRepository
from app.modules.warehouses.schemas import WarehouseCreate
from sqlalchemy.ext.asyncio import AsyncSession


def _now_utc() -> datetime:
    return datetime.now(UTC)


class WarehouseService:
    def __init__(self, session: AsyncSession, repository: WarehouseRepository | None = None) -> None:
        self._session = session
        self._repository = repository or WarehouseRepository(session)

    # --------------------------------------------------------------- READ

    async def list_warehouses(self) -> list[Warehouse]:
        return await self._repository.list()

    async def get_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        warehouse = await self._repository.get_by_id(warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError(str(warehouse_id))
        return warehouse

    # --------------------------------------------------------------- WRITE

    async def create_warehouse(self, payload: WarehouseCreate) -> Warehouse:
        if await self._repository.get_by_code(payload.code) is not None:
            raise DuplicateWarehouseCodeError(payload.code)

        now = _now_utc()
        warehouse = Warehouse(
            id=uuid.uuid4(),
            code=payload.code,
            name=payload.name,
            warehouse_type=payload.warehouse_type,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        await self._repository.add(warehouse)
        await self._session.commit()
        await self._session.refresh(warehouse)
        return warehouse


__all__ = ["WarehouseService"]
