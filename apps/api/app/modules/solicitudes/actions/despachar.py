"""
Accion: despachar solicitud (APPROVED -> IN_TRANSIT).

Descuenta stock de la bodega ORIGEN (Aux) via MovementEngine, porque
el operador de origen esta preparando el pedido y sacando unidades de
su bodega. El destino (Principal) las recibe via `receive`
(ver actions/recibir.py) que suma a la bodega destino.

FIX (FASE POST-E2E): antes este archivo restaba stock de `id_bodega_destino`
(Principal), comportamiento opuesto al documentado en el manual de usuario
(seccion 9.5 "Despachar una solicitud") y a la logica de negocio esperada.
El E2E de manual de usuario (auditoria-fase5/e2e_manual_usuario.py)
detecto el bug. Ahora descuenta de `id_bodega_origen` como debe ser.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.core.errors import (
    InvalidTransferQuantityError,
    ProductNotFoundError,
    SolicitudInvalidStateError,
)
from app.core.logging import get_logger
from app.db.models.inventory import MovementType
from app.db.models.notificaciones import NotificationType
from app.db.models.solicitudes import (
    DetalleSolicitudRecarga,
    SolicitudEstado,
    SolicitudRecarga,
)
from app.db.models.users import UserRole
from app.db.models.warehouses import Warehouse
from app.modules.solicitudes.actions._common import (
    SolicitudView,
    lock_or_404,
    to_view,
    utcnow,
)
from app.shared.movement_engine import MovementEngine, MovementRequest
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import SolicitudDespacho


log = get_logger(__name__)


async def _apply_dispatch(
    session: AsyncSession,
    repo,
    movement: MovementEngine,
    notif,
    *,
    solicitud: SolicitudRecarga,
    detalles: list[DetalleSolicitudRecarga],
    lineas: list[dict],
    notas: str | None,
    user_id: uuid.UUID | None,
) -> SolicitudView:
    """Logica transaccional comun al dispatch (total o parcial)."""
    detalles_by_id = {d.id_producto: d for d in detalles}
    # 1. Validar cada linea
    for linea in lineas:
        pid = linea["id_producto"]
        if pid not in detalles_by_id:
            raise ProductNotFoundError(str(pid))
        detalle = detalles_by_id[pid]
        cant = linea["cantidad_despachada"]
        if cant <= 0:
            raise InvalidTransferQuantityError(
                f"Cantidad a despachar para producto {pid} debe ser > 0"
            )
        if cant + detalle.cantidad_despachada > detalle.cantidad_solicitada:
            raise InvalidTransferQuantityError(
                f"Cantidad a despachar ({cant}) supera lo solicitado "
                f"({detalle.cantidad_solicitada}) para producto {pid}"
            )

    # 2. Aplicar movimientos OUT via MovementEngine (descuenta de ORIGEN)
    # FIX: el operador de origen esta preparando el pedido, asi que el
    # stock sale de SU bodega. Antes restaba de destino, que era el
    # comportamiento inverso al manual.
    now = utcnow()
    for linea in lineas:
        pid = linea["id_producto"]
        cant = linea["cantidad_despachada"]
        if cant <= 0:
            continue
        await movement.apply(
            MovementRequest(
                warehouse_id=solicitud.id_bodega_origen,  # FIX: origen, no destino
                product_id=pid,
                movement_type=MovementType.OUT,
                quantity=cant,
                reference_type="solicitud_dispatch",
                reference_id=solicitud.codigo,
                notes=notas or f"Despacho {solicitud.codigo} desde {solicitud.id_bodega_origen}",
                user_id=user_id,
            )
        )
        await repo.update_linea_despacho(
            solicitud_id=solicitud.id,
            producto_id=pid,
            cantidad=cant,
        )

    # 3. Actualizar estado y timestamp
    await repo.update_estado(solicitud.id, "in_transit", dispatched_at=now)
    await session.commit()

    # Metricas Fase 9: solicitudes despachadas (cardinalidad 0).
    from app.modules.observability.metrics import (  # noqa: PLC0415
        SOLICITUDES_DESPACHADAS_TOTAL,
    )

    SOLICITUDES_DESPACHADAS_TOTAL.inc()

    log.info(
        "solicitud.dispatched",
        solicitud_id=str(solicitud.id),
        codigo=solicitud.codigo,
        total_lineas=len(lineas),
        user_id=str(user_id) if user_id else None,
    )

    # Notificar a operadores de destino (y admin/supervisor).
    wh_destino_disp = await session.get(Warehouse, solicitud.id_bodega_destino)
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.DESTINATION_OPERATOR],
        tipo=NotificationType.SOLICITUD_DISPATCHED.value,
        titulo=f"Solicitud {solicitud.codigo} despachada",
        mensaje=(f"Recibir en {wh_destino_disp.code if wh_destino_disp else 'destino'}"),
        payload=(f'{{"solicitud_id": "{solicitud.id}", "codigo": "{solicitud.codigo}"}}'),
    )

    return await to_view(session, repo, solicitud.id)


async def dispatch_solicitud(
    session: AsyncSession,
    repo,
    movement: MovementEngine,
    notif,
    solicitud_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Despacha TODAS las lineas (compat con tests previos).

    Equivalente a `dispatch(...)` con todas las lineas en cantidad solicitada.
    """
    # 1. Lock + validar estado
    solicitud = await lock_or_404(repo, solicitud_id)
    if solicitud.estado != SolicitudEstado.APPROVED:
        raise SolicitudInvalidStateError(current=solicitud.estado.value, expected="approved")
    # 2. Cargar detalles y construir lineas "completas"
    detalles = list(await repo.list_detalles(solicitud_id))
    if not detalles:
        raise InvalidTransferQuantityError("La solicitud no tiene lineas para despachar")
    lineas_payload = [
        {
            "id_producto": d.id_producto,
            "cantidad_despachada": d.cantidad_solicitada,
            "barcode": None,
        }
        for d in detalles
    ]
    return await _apply_dispatch(
        session=session,
        repo=repo,
        movement=movement,
        notif=notif,
        solicitud=solicitud,
        detalles=detalles,
        lineas=lineas_payload,
        notas=None,
        user_id=user_id,
    )


async def dispatch(
    session: AsyncSession,
    repo,
    movement: MovementEngine,
    notif,
    solicitud_id: uuid.UUID,
    payload: SolicitudDespacho,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Despacha con payload por linea (despacho parcial permitido)."""
    solicitud = await lock_or_404(repo, solicitud_id)
    if solicitud.estado != SolicitudEstado.APPROVED:
        raise SolicitudInvalidStateError(current=solicitud.estado.value, expected="approved")
    if not payload.lineas:
        raise InvalidTransferQuantityError("El despacho debe tener al menos 1 linea")
    detalles = list(await repo.list_detalles(solicitud_id))
    lineas_payload = [
        {
            "id_producto": line.producto_id,
            "cantidad_despachada": line.cantidad_despachada,
            "barcode": line.barcode,
        }
        for line in payload.lineas
    ]
    return await _apply_dispatch(
        session=session,
        repo=repo,
        movement=movement,
        notif=notif,
        solicitud=solicitud,
        detalles=detalles,
        lineas=lineas_payload,
        notas=payload.notas,
        user_id=user_id,
    )
