"""
Accion: enviar OC al supervisor (encolar email en outbox).

Pasos (ADR-0004 + ADR-0005):
1. Validar estado BORRADOR.
2. Generar jti + token HMAC con expiracion 7d.
3. Cambiar estado a ENVIADO_A_SUPERVISOR.
4. Insertar row en `email_outbox` con status='pending' (worker Arq
   lo procesa asincronicamente, Fase 7).

Devuelve tupla (view, token, outbox_id). El token NO se devuelve al
cliente en la API final (viaja en el email); aqui se incluye solo
para facilitar testing E2E.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.errors import InvalidOrdenCompraStatusError
from app.core.logging import get_logger
from app.core.security import issue_approval_token
from app.db.models.notificaciones import NotificationType
from app.db.models.ordenes_compra import (
    EmailOutbox,
    OrdenCompraEstado,
)
from app.db.models.supervisores import Supervisor
from app.db.models.users import UserRole
from app.modules.notificaciones.service import NotificacionesService
from app.modules.ordenes_compra.actions._common import OrdenCompraView, require_oc, to_view
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


async def enviar_correo(
    session: AsyncSession,
    notif: NotificacionesService,
    oc_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> tuple[OrdenCompraView, str, uuid.UUID]:
    """Envia la OC a supervisor (encola email en outbox).

    Returns:
        Tupla (view actualizada, token generado, outbox_id).
    """
    oc = await require_oc(session, oc_id)
    if oc.estado != OrdenCompraEstado.BORRADOR:
        raise InvalidOrdenCompraStatusError(
            current=oc.estado.value,
            expected=OrdenCompraEstado.BORRADOR.value,
        )

    # Estado + timestamp
    oc.estado = OrdenCompraEstado.ENVIADO_A_SUPERVISOR
    oc.email_enviado_at = datetime.now(UTC)
    jti = str(uuid.uuid4())
    oc.email_token_jti = jti

    # Token HMAC (ADR-0005)
    token = issue_approval_token(
        orden_id=str(oc.id),
        supervisor_id=str(oc.id_supervisor),
        action="approve",
        jti=jti,
    )

    # Insertar en outbox
    sup = await session.get(Supervisor, oc.id_supervisor)
    to_email = sup.email if sup else "noreply@bodega.example"
    subject = f"Aprobacion requerida: OC {oc.codigo}"
    body_html = (
        f"<h1>OC {oc.codigo}</h1>"
        f"<p>Proveedor: {oc.proveedor_nombre}</p>"
        f"<p>Total estimado: {oc.total_estimado}</p>"
        f'<p><a href="/ordenes-compra/aprobar/{token}">Aprobar/Rechazar OC</a></p>'
    )
    context = (
        '{"oc_id": "' + str(oc.id) + '", "codigo": "' + oc.codigo + '", "token": "' + token + '"}'
    )
    outbox = EmailOutbox(
        id=uuid.uuid4(),
        to_email=to_email,
        subject=subject,
        body_html=body_html,
        template_name="orden_compra.html.j2",
        template_context=context,
        status="pending",
    )
    session.add(outbox)
    await session.commit()
    await session.refresh(oc)

    log.info(
        "orden_compra.enviada",
        oc_id=str(oc.id),
        codigo=oc.codigo,
        supervisor_email=to_email,
        outbox_id=str(outbox.id),
        jti=jti,
    )

    # Notificar a admin+supervisor (excluyendo al actor).
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
        tipo=NotificationType.ORDEN_COMPRA_ENVIADA.value,
        titulo=f"OC {oc.codigo} enviada a supervisor",
        mensaje=f"Proveedor: {oc.proveedor_nombre} - Total: {oc.total_estimado}",
        payload=(f'{{"oc_id": "{oc.id}", "codigo": "{oc.codigo}"}}'),
    )

    return await to_view(session, oc), token, outbox.id


async def enviar_a_supervisor(
    session: AsyncSession,
    notif: NotificacionesService,
    oc_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> tuple[OrdenCompraView, str]:
    """Alias historico (Fase 8). Ver `enviar_correo` para el nombre canonico.

    Devuelve solo (view, token) por compatibilidad con la API previa.
    """
    view, token, _outbox_id = await enviar_correo(session, notif, oc_id, user_id=user_id)
    return view, token
