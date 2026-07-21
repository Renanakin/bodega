"""Query: obtener una solicitud por ID."""

from __future__ import annotations

import uuid

from app.core.errors import SolicitudNotFoundError
from app.modules.solicitudes.actions._common import SolicitudView, to_view
from sqlalchemy.ext.asyncio import AsyncSession


async def get_solicitud(session: AsyncSession, repo, solicitud_id: uuid.UUID) -> SolicitudView:
    """Obtiene una solicitud por ID. 404 si no existe."""
    solicitud = await repo.get_by_id(solicitud_id)
    if solicitud is None:
        raise SolicitudNotFoundError(str(solicitud_id))
    return await to_view(session, repo, solicitud_id)


# Alias semantico: get es el nombre preferido en el modulo.
get = get_solicitud
