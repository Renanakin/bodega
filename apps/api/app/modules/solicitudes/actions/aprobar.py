"""
Accion: aprobar solicitud (PENDING -> APPROVED).

No descuenta stock. Solo valida estado, actualiza, notifica.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.core.errors import SolicitudInvalidStateError
from app.core.logging import get_logger
from app.db.models.notificaciones import NotificationType
from app.db.models.solicitudes import SolicitudEstado
from app.db.models.users import UserRole
from app.db.models.warehouses import Warehouse
from app.modules.solicitudes.actions._common import (
    SolicitudView,
    lock_or_404,
    to_view,
    utcnow,
)
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import SolicitudAprobacion


log = get_logger(__name__)


async def approve_solicitud(
    session: AsyncSession,
    repo,
    notif,
    solicitud_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Aprueba una solicitud (PENDING -> APPROVED). No descuenta stock."""
    solicitud = await lock_or_404(repo, solicitud_id)
    if solicitud.estado != SolicitudEstado.PENDING:
        raise SolicitudInvalidStateError(current=solicitud.estado.value, expected="pending")
    now = utcnow()
    await repo.update_estado(solicitud_id, "approved", approved_at=now)
    await session.commit()
    log.info(
        "solicitud.approved",
        solicitud_id=str(solicitud_id),
        codigo=solicitud.codigo,
        user_id=str(user_id) if user_id else None,
    )

    # Notificar a operadores de origen que la solicitud fue aprobada
    # (y deben despachar).
    wh_origen_appr = await session.get(Warehouse, solicitud.id_bodega_origen)
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ORIGIN_OPERATOR],
        tipo=NotificationType.SOLICITUD_APPROVED.value,
        titulo=f"Solicitud {solicitud.codigo} aprobada",
        mensaje=(
            f"Proceder con despacho desde {wh_origen_appr.code if wh_origen_appr else 'origen'}"
        ),
        payload=(f'{{"solicitud_id": "{solicitud.id}", "codigo": "{solicitud.codigo}"}}'),
    )

    return await to_view(session, repo, solicitud_id)


async def approve(
    session: AsyncSession,
    repo,
    notif,
    solicitud_id: uuid.UUID,
    _payload: SolicitudAprobacion | None = None,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Sobrecarga: acepta ``SolicitudAprobacion`` opcional."""
    return await approve_solicitud(session, repo, notif, solicitud_id, user_id=user_id)
