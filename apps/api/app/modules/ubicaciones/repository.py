"""
Repository de ubicaciones (async, SQLAlchemy 2.0).

Operaciones CRUD sobre ``ubicaciones_estanteria`` usando ``AsyncSession``
y el modelo ORM ``UbicacionEstanteria``. Versión async del repository
legacy (que usaba ``SQLiteDatabase`` + SQL crudo).
"""

from __future__ import annotations

import uuid

from app.db.models.ubicaciones import UbicacionEstanteria
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class UbicacionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----------------------------------------------------------------- READ

    async def list_by_bodega(self, id_bodega: uuid.UUID) -> list[UbicacionEstanteria]:
        stmt = (
            select(UbicacionEstanteria)
            .where(UbicacionEstanteria.id_bodega == id_bodega)
            .order_by(
                UbicacionEstanteria.pasillo,
                UbicacionEstanteria.estanteria,
                UbicacionEstanteria.altura,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, ubicacion_id: uuid.UUID) -> UbicacionEstanteria | None:
        return await self._session.get(UbicacionEstanteria, ubicacion_id)

    async def find_by_slot(
        self,
        id_bodega: uuid.UUID,
        pasillo: int,
        estanteria: int,
        altura: int,
    ) -> UbicacionEstanteria | None:
        stmt = select(UbicacionEstanteria).where(
            UbicacionEstanteria.id_bodega == id_bodega,
            UbicacionEstanteria.pasillo == pasillo,
            UbicacionEstanteria.estanteria == estanteria,
            UbicacionEstanteria.altura == altura,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # --------------------------------------------------------------- WRITE

    async def add(self, ubicacion: UbicacionEstanteria) -> UbicacionEstanteria:
        self._session.add(ubicacion)
        await self._session.flush()
        return ubicacion

    async def update(
        self,
        ubicacion: UbicacionEstanteria,
        *,
        descripcion: str | None = None,
        is_active: bool | None = None,
    ) -> UbicacionEstanteria:
        if descripcion is not None:
            ubicacion.descripcion = descripcion
        if is_active is not None:
            ubicacion.is_active = is_active
        await self._session.flush()
        return ubicacion

    async def soft_delete(self, ubicacion: UbicacionEstanteria) -> None:
        ubicacion.is_active = False
        await self._session.flush()


__all__ = ["UbicacionRepository"]
