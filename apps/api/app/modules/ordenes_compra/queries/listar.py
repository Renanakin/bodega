"""Query: listar ordenes de compra con filtros."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.db.models.ordenes_compra import OrdenCompra
from app.modules.ordenes_compra.actions._common import OrdenCompraView, to_view
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def list_ordenes(
    session: AsyncSession,
    *,
    estado: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> list[OrdenCompraView]:
    """Lista OCs con filtros opcionales.

    Args:
        estado: filtrar por estado exacto (borrador, enviado_a_supervisor, ...).
        proveedor: filtro ILIKE sobre `proveedor_nombre`.
        fecha_desde: OC con created_at >= fecha_desde (00:00).
        fecha_hasta: OC con created_at <= fecha_hasta (23:59:59).
    """
    stmt = select(OrdenCompra).order_by(OrdenCompra.created_at.desc())
    if estado:
        stmt = stmt.where(OrdenCompra.estado == estado)
    if proveedor:
        stmt = stmt.where(OrdenCompra.proveedor_nombre.ilike(f"%{proveedor}%"))
    if fecha_desde is not None:
        stmt = stmt.where(
            OrdenCompra.created_at >= datetime.combine(fecha_desde, datetime.min.time(), tzinfo=UTC)
        )
    if fecha_hasta is not None:
        stmt = stmt.where(
            OrdenCompra.created_at <= datetime.combine(fecha_hasta, datetime.max.time(), tzinfo=UTC)
        )
    result = await session.execute(stmt)
    return [await to_view(session, o) for o in result.scalars().all()]
