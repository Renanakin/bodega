"""
Accion: aprobar orden de compra.

Hay dos paths:
- `aprobar_orden`: desde la app con auth. Valida estado ENVIADO.
- `aprobar_con_token`: desde el endpoint publico HMAC (sin auth).
  Valida firma, expiracion y one-shot (invalida jti al consumir).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.errors import (
    ExpiredApprovalTokenError,
    InvalidApprovalTokenError,
    InvalidOrdenCompraStatusError,
)
from app.core.logging import get_logger
from app.core.security import (
    ApprovalTokenExpiredError,
    ApprovalTokenInvalidError,
    verify_approval_token,
)
from app.db.models.notificaciones import NotificationType
from app.db.models.ordenes_compra import OrdenCompraEstado
from app.db.models.users import UserRole
from app.modules.notificaciones.service import NotificacionesService
from app.modules.ordenes_compra.actions._common import (
    ESTADOS_TERMINALES,
    OrdenCompraView,
    require_oc,
    to_view,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


async def aprobar_orden(
    session: AsyncSession,
    notif: NotificacionesService,
    oc_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> OrdenCompraView:
    """Aprobar OC desde la app (con auth). Solo valido si esta ENVIADO."""
    oc = await require_oc(session, oc_id)
    if oc.estado != OrdenCompraEstado.ENVIADO_A_SUPERVISOR:
        raise InvalidOrdenCompraStatusError(
            current=oc.estado.value,
            expected=OrdenCompraEstado.ENVIADO_A_SUPERVISOR.value,
        )
    oc.estado = OrdenCompraEstado.APROBADO
    oc.aprobado_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(oc)
    log.info("orden_compra.approved", oc_id=str(oc.id), codigo=oc.codigo)

    # Notificar a admin+supervisor (excluyendo al actor).
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
        tipo=NotificationType.ORDEN_COMPRA_APROBADA.value,
        titulo=f"OC {oc.codigo} aprobada",
        mensaje=f"Proveedor: {oc.proveedor_nombre}",
        payload=(f'{{"oc_id": "{oc.id}", "codigo": "{oc.codigo}"}}'),
    )

    return await to_view(session, oc)


async def aprobar_con_token(
    session: AsyncSession,
    notif: NotificacionesService,
    token: str,
    decision: str,
    motivo: str | None = None,
) -> OrdenCompraView:
    """Aprobar o rechazar OC via token publico (SIN auth).

    Raises:
        InvalidApprovalTokenError: firma invalida o malformada.
        ExpiredApprovalTokenError: token expirado.
        InvalidOrdenCompraStatusError: si la OC ya fue procesada.
    """
    try:
        payload = verify_approval_token(token)
    except ApprovalTokenExpiredError as e:
        raise ExpiredApprovalTokenError() from e
    except ApprovalTokenInvalidError as e:
        raise InvalidApprovalTokenError() from e

    oc_id = uuid.UUID(payload["orden_id"])
    oc = await require_oc(session, oc_id)

    # One-shot: estados terminales no aceptan mas transiciones.
    if oc.estado in ESTADOS_TERMINALES:
        raise InvalidOrdenCompraStatusError(
            current=oc.estado.value,
            expected=OrdenCompraEstado.ENVIADO_A_SUPERVISOR.value,
        )
    # Solo se puede aprobar/rechazar si esta en ENVIADO_A_SUPERVISOR.
    if oc.estado != OrdenCompraEstado.ENVIADO_A_SUPERVISOR:
        raise InvalidOrdenCompraStatusError(
            current=oc.estado.value,
            expected=OrdenCompraEstado.ENVIADO_A_SUPERVISOR.value,
        )

    if decision == "approve":
        oc.estado = OrdenCompraEstado.APROBADO
        oc.aprobado_at = datetime.now(UTC)
    else:
        oc.estado = OrdenCompraEstado.RECHAZADO
        oc.motivo_rechazo = motivo or "Rechazado por supervisor"
    # Invalidar token (one-shot) - ADR-0005
    oc.email_token_jti = None

    await session.commit()
    await session.refresh(oc)
    log.info(
        "orden_compra.decided_via_token",
        oc_id=str(oc.id),
        codigo=oc.codigo,
        decision=decision,
    )

    # Notificar a admin+supervisor. En el flujo por token no hay un User
    # autenticado (el supervisor externo decidio), asi que pasamos
    # user_id=None y NO se excluye a nadie.
    if decision == "approve":
        await notif.notify_role_except_actor(
            actor_id=None,
            roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
            tipo=NotificationType.ORDEN_COMPRA_APROBADA.value,
            titulo=f"OC {oc.codigo} aprobada (via token)",
            mensaje=f"Proveedor: {oc.proveedor_nombre}",
            payload=(f'{{"oc_id": "{oc.id}", "codigo": "{oc.codigo}", "via": "token"}}'),
        )
    else:
        await notif.notify_role_except_actor(
            actor_id=None,
            roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
            tipo=NotificationType.ORDEN_COMPRA_RECHAZADA.value,
            titulo=f"OC {oc.codigo} rechazada (via token)",
            mensaje=(f"Motivo: {oc.motivo_rechazo or 'No especificado'}"),
            payload=(f'{{"oc_id": "{oc.id}", "codigo": "{oc.codigo}", "via": "token"}}'),
        )

    return await to_view(session, oc)
