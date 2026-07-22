"""
Service de ubicaciones (async).

Reglas de negocio:
- UNIQUE constraint (id_bodega, pasillo, estanteria, altura) — validado
  antes de INSERT para devolver 409 limpio (duplicate_ubicacion).
- id_bodega debe apuntar a una bodega existente.
- DELETE es soft: marca ``is_active=False``.

Convenciones:
- Métodos ``async def``.
- ``await session.commit()`` + ``refresh()`` después de mutaciones.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.errors import DuplicateUbicacionError, UbicacionNotFoundError
from app.db.models.ubicaciones import UbicacionEstanteria
from app.modules.ubicaciones.repository import UbicacionRepository
from app.modules.ubicaciones.schemas import UbicacionCreate, UbicacionUpdate
from app.modules.warehouses.repository import WarehouseRepository
from sqlalchemy.ext.asyncio import AsyncSession


def _now_utc() -> datetime:
    return datetime.now(UTC)


class UbicacionService:
    def __init__(
        self,
        session: AsyncSession,
        repository: UbicacionRepository | None = None,
        warehouse_repository: WarehouseRepository | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or UbicacionRepository(session)
        self._warehouses = warehouse_repository or WarehouseRepository(session)

    # --------------------------------------------------------------- READ

    async def list_by_bodega(self, id_bodega: uuid.UUID) -> list[UbicacionEstanteria]:
        if await self._warehouses.get_by_id(id_bodega) is None:
            raise UbicacionNotFoundError(str(id_bodega))
        return await self._repository.list_by_bodega(id_bodega)

    async def get_ubicacion(self, ubicacion_id: uuid.UUID) -> UbicacionEstanteria:
        ubicacion = await self._repository.get_by_id(ubicacion_id)
        if ubicacion is None:
            raise UbicacionNotFoundError(str(ubicacion_id))
        return ubicacion

    # --------------------------------------------------------------- WRITE

    async def create_ubicacion(
        self, id_bodega: uuid.UUID, payload: UbicacionCreate
    ) -> UbicacionEstanteria:
        if await self._warehouses.get_by_id(id_bodega) is None:
            raise UbicacionNotFoundError(str(id_bodega))

        if (
            await self._repository.find_by_slot(
                id_bodega, payload.pasillo, payload.estanteria, payload.altura
            )
            is not None
        ):
            raise DuplicateUbicacionError(
                f"Bodega {id_bodega} ya tiene la ubicación "
                f"P-{payload.pasillo:02d}/E-{payload.estanteria:02d}/"
                f"A-{payload.altura:02d}"
            )

        now = _now_utc()
        ubicacion = UbicacionEstanteria(
            id=uuid.uuid4(),
            id_bodega=id_bodega,
            pasillo=payload.pasillo,
            estanteria=payload.estanteria,
            altura=payload.altura,
            descripcion=payload.descripcion,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        await self._repository.add(ubicacion)
        await self._session.commit()
        await self._session.refresh(ubicacion)
        return ubicacion

    async def update_ubicacion(
        self, ubicacion_id: uuid.UUID, payload: UbicacionUpdate
    ) -> UbicacionEstanteria:
        ubicacion = await self.get_ubicacion(ubicacion_id)  # 404 si no existe
        await self._repository.update(
            ubicacion,
            descripcion=payload.descripcion,
            is_active=payload.is_active,
        )
        await self._session.commit()
        await self._session.refresh(ubicacion)
        return ubicacion

    async def delete_ubicacion(self, ubicacion_id: uuid.UUID) -> None:
        ubicacion = await self.get_ubicacion(ubicacion_id)  # 404 si no existe
        await self._repository.soft_delete(ubicacion)
        await self._session.commit()


__all__ = ["UbicacionService"]
