"""
Accion: rechazar orden de compra (estado ENVIADO -> RECHAZADO).

Solo se puede rechazar una OC que este en ENVIADO_A_SUPERVISOR.
La accion `aprobar_con_token` cubre el rechazo via token publico HMAC
(ver actions/aprobar.py).
"""

from __future__ import annotations

import uuid

from app.core.errors import InvalidOrdenCompraStatusError
from app.core.logging import get_logger
from app.db.models.notificaciones import NotificationType
from app.db.models.ordenes_compra import OrdenCompraEstado
from app.db.models.users import UserRole
from app.modules.notificaciones.service import NotificacionesService
from app.modules.ordenes_compra.actions._common import OrdenCompraView, require_oc, to_view
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


async def rechazar_orden(
    session: AsyncSession,
    notif: NotificacionesService,
    oc_id: uuid.UUID,
    motivo: str,
    user_id: uuid.UUID | None = None,
) -> OrdenCompraView:
    """Rechazar OC desde la app (con auth). Solo valido si esta ENVIADO."""
    oc = await require_oc(session, oc_id)
    if oc.estado != OrdenCompraEstado.ENVIADO_A_SUPERVISOR:
        raise InvalidOrdenCompraStatusError(
            current=oc.estado.value,
            expected=OrdenCompraEstado.ENVIADO_A_SUPERVISOR.value,
        )
    oc.estado = OrdenCompraEstado.RECHAZADO
    oc.motivo_rechazo = motivo
    await session.commit()
    await session.refresh(oc)
    log.info(
        "orden_compra.rejected",
        oc_id=str(oc.id),
        codigo=oc.codigo,
        motivo=motivo,
    )

    # Notificar a admin+supervisor (excluyendo al actor).
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
        tipo=NotificationType.ORDEN_COMPRA_RECHAZADA.value,
        titulo=f"OC {oc.codigo} rechazada",
        mensaje=f"Motivo: {motivo}",
        payload=(f'{{"oc_id": "{oc.id}", "codigo": "{oc.codigo}", "motivo": "{motivo}"}}'),
    )

    return await to_view(session, oc)
