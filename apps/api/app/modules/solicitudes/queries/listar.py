"""Query: listar solicitudes con filtros."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.modules.solicitudes.actions._common import SolicitudView, to_views_batch
from sqlalchemy.ext.asyncio import AsyncSession


async def list_solicitudes(
    session: AsyncSession,
    repo,
    *,
    estado: str | list[str] | None = None,
    id_bodega_origen: uuid.UUID | None = None,
) -> list[SolicitudView]:
    """Lista solicitudes con filtros (compat con tests previos).

    P0 (roadmap Big-O): usa to_views_batch() para evitar N+1.
    """
    rows = await repo.list(estado=estado, id_bodega_origen=id_bodega_origen)
    return await to_views_batch(session, repo, rows)


async def list_with_filters(
    session: AsyncSession,
    repo,
    *,
    estado: str | list[str] | None = None,
    id_bodega_origen: uuid.UUID | None = None,
    id_bodega_destino: uuid.UUID | None = None,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[SolicitudView]:
    """Lista con filtros extendidos (Fase 3 prompt).

    P0 (roadmap Big-O): usa to_views_batch() para evitar N+1.
    """
    rows = await repo.list(
        estado=estado,
        id_bodega_origen=id_bodega_origen,
        id_bodega_destino=id_bodega_destino,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        skip=skip,
        limit=limit,
    )
    return await to_views_batch(session, repo, rows)
