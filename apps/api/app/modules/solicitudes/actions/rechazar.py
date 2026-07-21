"""
Accion: rechazar solicitud (PENDING o APPROVED -> REJECTED) con motivo.

Solo el admin o supervisor puede rechazar. Se notifica al origen.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

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
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import SolicitudRechazo


log = get_logger(__name__)


async def reject_solicitud(
    session: AsyncSession,
    repo,
    notif,
    solicitud_id: uuid.UUID,
    motivo: str,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Rechaza una solicitud PENDING o APPROVED con motivo."""
    solicitud = await lock_or_404(repo, solicitud_id)
    if solicitud.estado not in (
        SolicitudEstado.PENDING,
        SolicitudEstado.APPROVED,
    ):
        raise SolicitudInvalidStateError(
            current=solicitud.estado.value,
            expected=["pending", "approved"],
        )
    solicitud.motivo_rechazo = motivo
    await repo.update_estado(solicitud_id, "rejected")
    await session.commit()

    # Metricas Fase 9: solicitudes rechazadas.
    from app.modules.observability.metrics import (  # noqa: PLC0415
        SOLICITUDES_RECHAZADAS_TOTAL,
    )

    SOLICITUDES_RECHAZADAS_TOTAL.inc()

    log.info(
        "solicitud.rejected",
        solicitud_id=str(solicitud_id),
        codigo=solicitud.codigo,
        motivo=motivo,
        user_id=str(user_id) if user_id else None,
    )

    # Notificar a operadores de origen que la solicitud fue rechazada.
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ORIGIN_OPERATOR],
        tipo=NotificationType.SOLICITUD_REJECTED.value,
        titulo=f"Solicitud {solicitud.codigo} rechazada",
        mensaje=f"Motivo: {motivo}",
        payload=(
            f'{{"solicitud_id": "{solicitud.id}", '
            f'"codigo": "{solicitud.codigo}", '
            f'"motivo": "{motivo}"}}'
        ),
    )

    return await to_view(session, repo, solicitud_id)


async def reject(
    session: AsyncSession,
    repo,
    notif,
    solicitud_id: uuid.UUID,
    payload: SolicitudRechazo,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Sobrecarga: acepta ``SolicitudRechazo`` Pydantic."""
    return await reject_solicitud(
        session, repo, notif, solicitud_id, payload.motivo, user_id=user_id
    )
