"""
Repository de stock por ubicación (async, SQLAlchemy 2.0).

Operaciones sobre ``inventario_stock_real`` (Nivel 2 — granularidad
por ubicación) usando ``AsyncSession`` y el modelo ORM
``InventarioStockReal``.

R3/R4: este repository NO escribe ``stock_levels`` (Nivel 1). El
``MovementEngine`` es el único que mantiene ambos sincronizados.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.db.models.stock_real import InventarioStockReal
from app.db.models.ubicaciones import UbicacionEstanteria
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class StockRealRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[InventarioStockReal]:
        """Consulta granular; JOIN a ubicaciones cuando se filtra por bodega."""
        stmt = select(InventarioStockReal)
        if warehouse_id is not None:
            stmt = stmt.join(
                UbicacionEstanteria,
                UbicacionEstanteria.id == InventarioStockReal.id_ubicacion,
            ).where(UbicacionEstanteria.id_bodega == warehouse_id)
        if product_id is not None:
            stmt = stmt.where(InventarioStockReal.id_producto == product_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(
        self, id_producto: uuid.UUID, id_ubicacion: uuid.UUID
    ) -> InventarioStockReal | None:
        return await self._session.get(InventarioStockReal, (id_producto, id_ubicacion))

    async def upsert(
        self,
        id_producto: uuid.UUID,
        id_ubicacion: uuid.UUID,
        cantidad: Decimal,
    ) -> InventarioStockReal:
        """Idempotente: si ya existe fila para (id_producto, id_ubicacion),
        actualiza; si no, inserta.
        """
        existing = await self.get(id_producto, id_ubicacion)
        if existing is not None:
            existing.cantidad = cantidad
            await self._session.flush()
            return existing
        new_row = InventarioStockReal(
            id_producto=id_producto,
            id_ubicacion=id_ubicacion,
            cantidad=cantidad,
        )
        self._session.add(new_row)
        await self._session.flush()
        return new_row


__all__ = ["StockRealRepository"]
