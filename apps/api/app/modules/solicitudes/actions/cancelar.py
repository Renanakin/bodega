"""
Accion: cancelar solicitud PENDING (origen la cancela antes de aprobar).

Solo aplica a solicitudes en estado PENDING. Si ya esta aprobada, hay
que rechazarla o reversarla (no implementado en esta fase).
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import SolicitudInvalidStateError
from app.core.logging import get_logger
from app.db.models.notificaciones import NotificationType
from app.db.models.solicitudes import SolicitudEstado
from app.db.models.users import UserRole

from app.modules.solicitudes.actions._common import (
    SolicitudView,
    lock_or_404,
    to_view,
)


if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import SolicitudCancelacion


log = get_logger(__name__)


async def cancel_solicitud(
    session: AsyncSession,
    repo,
    notif,
    solicitud_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Cancela una solicitud PENDING (origen la cancela antes de aprobar)."""
    solicitud = await lock_or_404(repo, solicitud_id)
    if solicitud.estado != SolicitudEstado.PENDING:
        raise SolicitudInvalidStateError(
            current=solicitud.estado.value, expected="pending"
        )
    await repo.update_estado(solicitud_id, "cancelled")
    await session.commit()
    log.info(
        "solicitud.cancelled",
        solicitud_id=str(solicitud_id),
        codigo=solicitud.codigo,
        user_id=str(user_id) if user_id else None,
    )

    # Notificar a admin+supervisor (excluyendo al actor).
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
        tipo=NotificationType.SOLICITUD_CANCELLED.value,
        titulo=f"Solicitud {solicitud.codigo} cancelada",
        mensaje="La solicitud fue cancelada antes de aprobar",
        payload=(
            f'{{"solicitud_id": "{solicitud.id}", '
            f'"codigo": "{solicitud.codigo}"}}'
        ),
    )

    return await to_view(session, repo, solicitud_id)


async def cancel(
    session: AsyncSession,
    repo,
    notif,
    solicitud_id: uuid.UUID,
    payload: "SolicitudCancelacion | None" = None,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Sobrecarga: acepta ``SolicitudCancelacion`` opcional."""
    return await cancel_solicitud(
        session, repo, notif, solicitud_id, user_id=user_id
    )
