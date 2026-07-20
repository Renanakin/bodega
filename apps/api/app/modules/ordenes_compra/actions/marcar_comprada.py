"""
Accion: marcar OC como comprada (proveedor entrego mercaderia).

Solo valido si la OC esta en APROBADO. Transiciona a COMPRADO
(estado terminal).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidOrdenCompraStatusError
from app.core.logging import get_logger
from app.db.models.notificaciones import NotificationType
from app.db.models.ordenes_compra import OrdenCompraEstado
from app.db.models.users import UserRole
from app.modules.notificaciones.service import NotificacionesService

from app.modules.ordenes_compra.actions._common import OrdenCompraView, require_oc, to_view


log = get_logger(__name__)


async def marcar_comprada(
    session: AsyncSession,
    notif: NotificacionesService,
    oc_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> OrdenCompraView:
    """Marcar OC como comprada (proveedor entrego mercaderia).

    Solo valido si esta APROBADO.
    """
    oc = await require_oc(session, oc_id)
    if oc.estado != OrdenCompraEstado.APROBADO:
        raise InvalidOrdenCompraStatusError(
            current=oc.estado.value,
            expected=OrdenCompraEstado.APROBADO.value,
        )
    oc.estado = OrdenCompraEstado.COMPRADO
    oc.comprado_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(oc)
    log.info("orden_compra.comprada", oc_id=str(oc.id), codigo=oc.codigo)

    # Notificar a admin+supervisor (excluyendo al actor).
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
        tipo=NotificationType.ORDEN_COMPRA_RECIBIDA.value,
        titulo=f"OC {oc.codigo} marcada como comprada",
        mensaje=f"Proveedor: {oc.proveedor_nombre}",
        payload=(
            f'{{"oc_id": "{oc.id}", '
            f'"codigo": "{oc.codigo}"}}'
        ),
    )

    return await to_view(session, oc)
