"""
Accion: recibir solicitud (IN_TRANSIT o PARTIALLY_RECEIVED -> RECEIVED o PARTIALLY_RECEIVED).

Incrementa stock de la bodega origen (Aux) via MovementEngine.
Soporta recepcion parcial: cada linea puede tener cantidad_recibida <= cantidad_despachada.
Valida barcode si viene (Fase 5).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.core.errors import (
    BarcodeMismatchError,
    InvalidTransferQuantityError,
    ProductNotFoundError,
    SolicitudInvalidStateError,
)
from app.core.logging import get_logger
from app.db.models.inventory import MovementType
from app.db.models.notificaciones import NotificationType
from app.db.models.products import Product
from app.db.models.solicitudes import (
    DetalleSolicitudRecarga,
    SolicitudEstado,
    SolicitudRecarga,
)
from app.db.models.users import UserRole
from app.modules.barcode import match_product
from app.modules.solicitudes.actions._common import (
    SolicitudView,
    lock_or_404,
    to_view,
    utcnow,
)
from app.shared.movement_engine import MovementEngine, MovementRequest
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import SolicitudRecepcion


log = get_logger(__name__)


async def _apply_receive(
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
    """Logica transaccional comun al receive (parcial o completo)."""
    detalles_by_id = {d.id_producto: d for d in detalles}

    for linea in lineas:
        pid = linea["id_producto"]
        if pid not in detalles_by_id:
            raise ProductNotFoundError(str(pid))
        detalle = detalles_by_id[pid]
        cant = linea["cantidad_recibida"]
        barcode = linea.get("barcode")
        incidencia = linea.get("incidencia")

        if cant <= 0:
            raise InvalidTransferQuantityError(
                f"Cantidad recibida para producto {pid} debe ser > 0"
            )
        pending = detalle.cantidad_despachada - detalle.cantidad_recibida
        if cant > pending:
            raise InvalidTransferQuantityError(
                f"Cantidad a recibir ({cant}) supera el pendiente ({pending}) para producto {pid}"
            )

        # Validar barcode si viene (Fase 5).
        # - Si el producto no tiene codigo_barras, el validador hace skip.
        # - Si tiene, match_product valida formato + checksum + compara normalizado.
        producto = await session.get(Product, pid) if barcode is not None else None
        if (
            barcode is not None
            and producto is not None
            and not match_product(barcode, producto.codigo_barras)
        ):
            log.warning(
                "solicitud.barcode_mismatch",
                solicitud_id=str(solicitud.id),
                producto_id=str(pid),
                expected=producto.codigo_barras,
                received=barcode,
            )
            raise BarcodeMismatchError(
                producto_id=str(pid),
                expected=producto.codigo_barras or "",
                received=barcode,
            )

        # Aplicar movimiento IN (incrementa bodega origen)
        await movement.apply(
            MovementRequest(
                warehouse_id=solicitud.id_bodega_origen,
                product_id=pid,
                movement_type=MovementType.IN,
                quantity=cant,
                reference_type="solicitud_receive",
                reference_id=solicitud.codigo,
                notes=incidencia or notas or f"Recepcion {solicitud.codigo}",
                user_id=user_id,
            )
        )
        await repo.update_linea_recepcion(
            solicitud_id=solicitud.id,
            producto_id=pid,
            cantidad=cant,
            barcode=barcode,
        )

    # 4. Decidir estado final
    detalles = list(await repo.list_detalles(solicitud.id))
    all_done = all(d.cantidad_recibida == d.cantidad_despachada for d in detalles)
    any_dispatched = any(d.cantidad_despachada > 0 for d in detalles)
    now = utcnow()
    if all_done and any_dispatched:
        await repo.update_estado(solicitud.id, "received", received_at=now)
    else:
        await repo.update_estado(solicitud.id, "partially_received")

    if notas:
        # Append a notas (no sobreescribe)
        current = await repo.get_by_id(solicitud.id)
        if current is not None and current.notas:
            current.notas = current.notas + " | " + notas
        elif current is not None:
            current.notas = notas
        await session.flush()
    await session.commit()

    log.info(
        "solicitud.received",
        solicitud_id=str(solicitud.id),
        codigo=solicitud.codigo,
        total_lineas=len(lineas),
        user_id=str(user_id) if user_id else None,
    )

    # Metricas Fase 9: solicitudes recibidas (completa o parcial).
    from app.modules.observability.metrics import (  # noqa: PLC0415
        SOLICITUDES_RECIBIDAS_TOTAL,
    )

    if all_done and any_dispatched:
        SOLICITUDES_RECIBIDAS_TOTAL.labels(completa="true").inc()
    else:
        SOLICITUDES_RECIBIDAS_TOTAL.labels(completa="false").inc()

    # Notificar a admin+supervisor (excluyendo al actor).
    estado_notif = "recibida" if all_done and any_dispatched else "parcialmente recibida"
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
        tipo=NotificationType.SOLICITUD_RECEIVED.value,
        titulo=f"Solicitud {solicitud.codigo} {estado_notif}",
        mensaje=f"{len(lineas)} linea(s) procesada(s)",
        payload=(
            f'{{"solicitud_id": "{solicitud.id}", '
            f'"codigo": "{solicitud.codigo}", '
            f'"completa": {str(all_done and any_dispatched).lower()}}}'
        ),
    )

    return await to_view(session, repo, solicitud.id)


async def receive_solicitud(
    session: AsyncSession,
    repo,
    movement: MovementEngine,
    notif,
    solicitud_id: uuid.UUID,
    lineas: list[dict],
    notas: str | None = None,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Recibe una o mas lineas (compat con tests previos).

    `lineas` es una lista de dicts con keys: id_producto, cantidad_recibida,
    barcode (opcional).
    """
    solicitud = await lock_or_404(repo, solicitud_id)
    if solicitud.estado not in (
        SolicitudEstado.IN_TRANSIT,
        SolicitudEstado.PARTIALLY_RECEIVED,
    ):
        raise SolicitudInvalidStateError(
            current=solicitud.estado.value,
            expected=["in_transit", "partially_received"],
        )
    if not lineas:
        raise InvalidTransferQuantityError("La recepcion debe tener al menos 1 linea")
    detalles = list(await repo.list_detalles(solicitud_id))
    return await _apply_receive(
        session=session,
        repo=repo,
        movement=movement,
        notif=notif,
        solicitud=solicitud,
        detalles=detalles,
        lineas=lineas,
        notas=notas,
        user_id=user_id,
    )


async def receive(
    session: AsyncSession,
    repo,
    movement: MovementEngine,
    notif,
    solicitud_id: uuid.UUID,
    payload: SolicitudRecepcion,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Recibe con payload Pydantic (incluye barcode + incidencia)."""
    solicitud = await lock_or_404(repo, solicitud_id)
    if solicitud.estado not in (
        SolicitudEstado.IN_TRANSIT,
        SolicitudEstado.PARTIALLY_RECEIVED,
    ):
        raise SolicitudInvalidStateError(
            current=solicitud.estado.value,
            expected=["in_transit", "partially_received"],
        )
    if not payload.lineas:
        raise InvalidTransferQuantityError("La recepcion debe tener al menos 1 linea")
    detalles = list(await repo.list_detalles(solicitud_id))
    lineas_dicts = [
        {
            "id_producto": line.producto_id,
            "cantidad_recibida": line.cantidad_recibida,
            "barcode": line.barcode,
            "incidencia": line.incidencia,
        }
        for line in payload.lineas
    ]
    return await _apply_receive(
        session=session,
        repo=repo,
        movement=movement,
        notif=notif,
        solicitud=solicitud,
        detalles=detalles,
        lineas=lineas_dicts,
        notas=payload.notas,
        user_id=user_id,
    )
