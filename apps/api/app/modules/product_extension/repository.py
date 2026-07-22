"""
Repository del sub-recurso ``detalles_neumaticos`` (async, SQLAlchemy 2.0).

Acceso a datos sobre la tabla ``detalles_neumaticos`` (PK = ``producto_id``,
relación 1:1 opt-in con ``products``) usando ``AsyncSession`` y el
modelo ORM ``DetalleNeumatico``.

UPSERT: en SQLAlchemy 2.0 sobre SQLite, el equivalente de
``INSERT ... ON CONFLICT DO UPDATE`` se logra con
``session.merge()`` (que internamente hace SELECT + INSERT/UPDATE).
En Postgres, ``session.merge()`` también funciona, pero para ser
explícitos podríamos usar ``text("...ON CONFLICT...")`` con dialect.postgresql.
Por simplicidad y portabilidad usamos ``session.merge()``.
"""

from __future__ import annotations

import uuid

from app.db.models.product_extension import DetalleNeumatico
from sqlalchemy.ext.asyncio import AsyncSession


class DetalleNeumaticoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_producto(self, producto_id: uuid.UUID) -> DetalleNeumatico | None:
        return await self._session.get(DetalleNeumatico, producto_id)

    async def upsert(self, detalle: DetalleNeumatico) -> None:
        """Idempotente: si ya existe fila para producto_id, actualiza; si no, inserta."""
        # ``session.merge()`` hace SELECT por PK; si existe, UPDATE; si no, INSERT.
        await self._session.merge(detalle)
        await self._session.flush()

    async def delete(self, producto_id: uuid.UUID) -> int:
        """Devuelve la cantidad de filas borradas (0 o 1)."""
        from sqlalchemy import delete

        stmt = delete(DetalleNeumatico).where(DetalleNeumatico.producto_id == producto_id)
        result = await self._session.execute(stmt)
        return result.rowcount or 0


__all__ = ["DetalleNeumaticoRepository"]
