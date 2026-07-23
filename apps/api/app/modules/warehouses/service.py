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

from app.core.errors import (
    DuplicateWarehouseCodeError,
    DuplicateWarehouseNameError,
    WarehouseNotFoundError,
)
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

    async def list_warehouses(
        self,
        warehouse_type: str | None = None,
        is_active: bool | None = None,
    ) -> list[Warehouse]:
        return await self._repository.list(
            warehouse_type=warehouse_type, is_active=is_active
        )

    async def get_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        warehouse = await self._repository.get_by_id(warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError(str(warehouse_id))
        return warehouse

    # --------------------------------------------------------------- WRITE

    async def create_warehouse(self, payload: WarehouseCreate) -> Warehouse:
        if await self._repository.get_by_code(payload.code) is not None:
            raise DuplicateWarehouseCodeError(payload.code)

        # C1.1: el CHECK/UNIQUE en ``name`` existe en BD (migración 0001) pero
        # sin este check previo, dos requests concurrentes podrían pasar
        # ambos lookups y el segundo recibiría un 500 IntegrityError. Con el
        # check, ambos casos devuelven 409 limpio.
        if await self._repository.get_by_name(payload.name) is not None:
            raise DuplicateWarehouseNameError(payload.name)

        now = _now_utc()
        warehouse = Warehouse(
            id=uuid.uuid4(),
            code=payload.code,
            name=payload.name,
            warehouse_type=payload.warehouse_type,
            parent_warehouse_id=payload.parent_warehouse_id,
            is_active=payload.is_active,
            created_at=now,
            updated_at=now,
        )
        await self._repository.add(warehouse)
        await self._session.commit()
        await self._session.refresh(warehouse)
        return warehouse


__all__ = ["WarehouseService"]
