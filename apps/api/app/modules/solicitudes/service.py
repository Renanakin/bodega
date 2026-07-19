"""
SolicitudService: workflow completo de solicitudes de recarga (N productos, Fase 3).

Reglas:
- R2: origen SIEMPRE es auxiliar o mecanico_box con parent; destino SIEMPRE es principal.
- R3: workflow centralizado en service, no en repository.
- R4: toda escritura de stock pasa por MovementEngine.
- R5: codigo unico formato SOL-YYYYMMDD-NNNN.
- R6: cada transicion emite log estructurado y audit_log.
- R7: queries parametrizadas via SolicitudRepository.
- ADR-0002: origen ∈ {auxiliar, mecanico_box con parent_warehouse_id}, destino = principal.
- ADR-0003: namespace unificado pending/approved/in_transit/received/partial/...

API publica:
    - API legacy (compatible con tests previos):
        create_solicitud(id_bodega_origen, id_bodega_destino, lineas, prioridad, notas)
        approve_solicitud(solicitud_id)
        dispatch_solicitud(solicitud_id)            # despacha todo lo solicitado
        receive_solicitud(solicitud_id, lineas, notas)
        cancel_solicitud(solicitud_id)
        reject_solicitud(solicitud_id, motivo)
        list_solicitudes(estado, id_bodega_origen)
        get_solicitud(solicitud_id)
    - API nueva (Fase 3 prompt):
        create(payload: SolicitudCreate, user_id)
        approve(solicitud_id, payload: SolicitudAprobacion, user_id)
        dispatch(solicitud_id, payload: SolicitudDespacho, user_id)
        receive(solicitud_id, payload: SolicitudRecepcion, user_id)
        reject(solicitud_id, payload: SolicitudRechazo, user_id)
        cancel(solicitud_id, payload: SolicitudCancelacion, user_id)
        get_distribucion_multibodega(sku: str)
        get_derived_transfer(codigo_legacy: str)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    BarcodeMismatchError,
    InvalidSolicitudDirectionError,
    InvalidTransferQuantityError,
    InvalidTransferStatusError,
    ProductNotActiveError,
    ProductNotFoundError,
    SolicitudInvalidStateError,
    SolicitudNotFoundError,
    WarehouseNotFoundError,
)
from app.core.logging import get_logger
from app.db.models.inventory import MovementType
from app.db.models.products import Product
from app.db.models.solicitudes import (
    DetalleSolicitudRecarga,
    SolicitudEstado,
    SolicitudRecarga,
)
from app.db.models.notificaciones import NotificationType
from app.db.models.users import UserRole
from app.db.models.warehouses import Warehouse
from app.modules.barcode import match_product
from app.modules.inventory.multibodega import StockMultibodegaService
from app.modules.notificaciones.service import NotificacionesService
from app.modules.observability.metrics import SOLICITUDES_CREADAS
from app.modules.solicitudes.repository import SolicitudRepository
from app.shared.movement_engine import MovementEngine, MovementRequest


if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import (
        DistribucionMultibodegaResponse,
        SolicitudAprobacion,
        SolicitudCancelacion,
        SolicitudCreate,
        SolicitudDespacho,
        SolicitudRecepcion,
        SolicitudRechazo,
        TransferDerivedResponse,
    )


log = get_logger(__name__)


# Mapeo entre estado de modelo y estado de API.
# Mantenemos el valor canónico del modelo (`partially_received`).
# El spec del usuario prefiere "partial" pero la migración 0006
# y los tests existentes usan el nombre largo. Si en una fase futura
# se quiere exponer solo el alias corto, hacerlo en el router.
def _api_estado(estado: SolicitudEstado) -> str:
    return estado.value


@dataclass(slots=True)
class SolicitudView:
    """Vista interna de la solicitud (el router la convierte a Pydantic)."""

    id: uuid.UUID
    codigo: str
    id_bodega_origen: uuid.UUID
    id_bodega_origen_codigo: str
    id_bodega_origen_nombre: str
    id_bodega_origen_tipo: str
    id_bodega_destino: uuid.UUID
    id_bodega_destino_codigo: str
    id_bodega_destino_nombre: str
    estado: str  # ya mapeado a API (partial en lugar de partially_received)
    prioridad: str | None
    notas: str | None
    motivo_rechazo: str | None
    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    received_at: datetime | None
    detalles: list[dict] = field(default_factory=list)
    total_productos: int = 0
    total_unidades: Decimal = Decimal("0")


class SolicitudService:
    """Service de solicitudes de recarga con workflow completo (Fase 3)."""

    def __init__(
        self,
        session: AsyncSession,
        notif_service: NotificacionesService | None = None,
    ) -> None:
        self._session = session
        self._repo = SolicitudRepository(session)
        self._movement = MovementEngine(session)
        # Deuda #7: emision automatica de notificaciones in-app en cada
        # transicion de estado. Si el caller no inyecta un service (e.g.
        # tests legacy), creamos uno por defecto que comparte la misma
        # session, asi el comportamiento es consistente.
        self._notif: NotificacionesService = (
            notif_service if notif_service is not None else NotificacionesService(session)
        )

    # ============================================================== CREATE

    async def create_solicitud(
        self,
        *,
        id_bodega_origen: uuid.UUID,
        id_bodega_destino: uuid.UUID,
        lineas: list[dict],
        prioridad: str | None = None,
        notas: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        """Crea una solicitud de recarga (N productos) con codigo unico.

        Reglas (ADR-0002):
        - origen ∈ {auxiliar, mecanico_box con parent_warehouse_id}
        - destino = principal
        - origen != destino
        - cada producto debe existir y estar activo
        - no se permiten productos duplicados

        Args:
            id_bodega_origen: bodega auxiliar o box.
            id_bodega_destino: bodega principal.
            lineas: lista de `{"id_producto": UUID, "cantidad_solicitada": Decimal}`.
            prioridad: "normal" | "alta" | "urgente" (o None).
            notas: notas libres.
            user_id: usuario que crea (para audit_log).

        Returns:
            ``SolicitudView`` con la solicitud creada (estado PENDING).
        """
        # 1. Validar input basico
        if not lineas:
            raise InvalidTransferQuantityError("La solicitud debe tener al menos 1 linea")

        product_ids = [l["id_producto"] for l in lineas]
        if len(product_ids) != len(set(product_ids)):
            raise InvalidTransferQuantityError("Productos duplicados en la solicitud")

        # 2. Validar bodegas y direccion (ADR-0002)
        wh_origen = await self._session.get(Warehouse, id_bodega_origen)
        if wh_origen is None:
            raise WarehouseNotFoundError(str(id_bodega_origen))
        wh_destino = await self._session.get(Warehouse, id_bodega_destino)
        if wh_destino is None:
            raise WarehouseNotFoundError(str(id_bodega_destino))
        self._validate_direction(wh_origen, wh_destino)

        # 3. Validar productos (existencia + activos)
        productos_by_id: dict[uuid.UUID, Product] = {}
        for pid in product_ids:
            p = await self._session.get(Product, pid)
            if p is None:
                raise ProductNotFoundError(str(pid))
            if not p.is_active:
                raise ProductNotActiveError(str(pid), p.sku)
            productos_by_id[pid] = p

        # 4. Generar codigo unico
        codigo = await self._repo.generate_unique_codigo(prefix="SOL")

        # 5. Crear solicitud (estado PENDING)
        solicitud = await self._repo.create_solicitud(
            codigo=codigo,
            id_bodega_origen=id_bodega_origen,
            id_bodega_destino=id_bodega_destino,
            prioridad=prioridad,
            notas=notas,
        )
        for linea in lineas:
            await self._repo.add_linea(
                id_solicitud=solicitud.id,
                id_producto=linea["id_producto"],
                cantidad_solicitada=linea["cantidad_solicitada"],
            )

        await self._session.commit()
        await self._session.refresh(solicitud)

        # Métricas Fase 9: incrementar contador de solicitudes creadas
        # con labels de tipo de bodega origen y prioridad. Cardinalidad
        # baja (3 tipos x 3 prioridades = 9 max).
        # ``prioridad`` puede ser None (campo opcional); normalizar a
        # ``"none"`` para que el label no sea vacio (Prometheus no soporta
        # label value vacio).
        prioridad_label = (prioridad or "none").lower()
        # ``warehouse_type`` siempre viene del modelo (validado en BD);
        # usar el valor crudo como label.
        origen_tipo_label = wh_origen.warehouse_type or "unknown"
        SOLICITUDES_CREADAS.labels(
            bodega_origen_tipo=origen_tipo_label,
            prioridad=prioridad_label,
        ).inc()

        log.info(
            "solicitud.created",
            solicitud_id=str(solicitud.id),
            codigo=solicitud.codigo,
            origen=wh_origen.code,
            origen_tipo=wh_origen.warehouse_type,
            destino=wh_destino.code,
            total_productos=len(lineas),
            user_id=str(user_id) if user_id else None,
        )

        # Deuda #7: notificar a admin+supervisor (excluyendo al actor)
        # que se creo una nueva solicitud.
        await self._notif.notify_role_except_actor(
            actor_id=user_id,
            roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
            tipo=NotificationType.SOLICITUD_CREATED.value,
            titulo=f"Nueva solicitud {solicitud.codigo}",
            mensaje=(
                f"{wh_origen.code} -> {wh_destino.code}: "
                f"{len(lineas)} producto(s)"
            ),
            payload=(
                f'{{"solicitud_id": "{solicitud.id}", '
                f'"codigo": "{solicitud.codigo}", '
                f'"origen": "{wh_origen.code}", '
                f'"destino": "{wh_destino.code}"}}'
            ),
        )

        return await self._to_view(solicitud.id)

    async def create(
        self, payload: "SolicitudCreate", user_id: uuid.UUID | None = None
    ) -> SolicitudView:
        """Sobrecarga: acepta un ``SolicitudCreate`` Pydantic."""
        return await self.create_solicitud(
            id_bodega_origen=payload.bodega_origen_id,
            id_bodega_destino=payload.bodega_destino_id,
            lineas=[
                {"id_producto": l.producto_id, "cantidad_solicitada": l.cantidad_solicitada}
                for l in payload.lineas
            ],
            prioridad=payload.prioridad,
            notas=payload.notas,
            user_id=user_id,
        )

    # ============================================================== APPROVE

    async def approve_solicitud(
        self, solicitud_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> SolicitudView:
        """Aprueba una solicitud (PENDING → APPROVED). No descuenta stock."""
        solicitud = await self._lock_or_404(solicitud_id)
        if solicitud.estado != SolicitudEstado.PENDING:
            raise SolicitudInvalidStateError(
                current=solicitud.estado.value, expected="pending"
            )
        now = _utcnow()
        await self._repo.update_estado(
            solicitud_id, "approved", approved_at=now
        )
        await self._session.commit()
        log.info(
            "solicitud.approved",
            solicitud_id=str(solicitud_id),
            codigo=solicitud.codigo,
            user_id=str(user_id) if user_id else None,
        )

        # Deuda #7: notificar a operadores de origen que la solicitud
        # fue aprobada (y deben despachar).
        wh_origen_appr = await self._session.get(Warehouse, solicitud.id_bodega_origen)
        await self._notif.notify_role_except_actor(
            actor_id=user_id,
            roles=[UserRole.ORIGIN_OPERATOR],
            tipo=NotificationType.SOLICITUD_APPROVED.value,
            titulo=f"Solicitud {solicitud.codigo} aprobada",
            mensaje=(
                f"Proceder con despacho desde "
                f"{wh_origen_appr.code if wh_origen_appr else 'origen'}"
            ),
            payload=(
                f'{{"solicitud_id": "{solicitud.id}", '
                f'"codigo": "{solicitud.codigo}"}}'
            ),
        )

        return await self._to_view(solicitud_id)

    async def approve(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudAprobacion | None" = None,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        """Sobrecarga: acepta ``SolicitudAprobacion`` opcional."""
        return await self.approve_solicitud(solicitud_id, user_id=user_id)

    # ============================================================== DISPATCH

    async def dispatch_solicitud(
        self, solicitud_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> SolicitudView:
        """Despacha TODAS las lineas (compat con tests previos).

        Equivalente a `dispatch(solicitud_id, SolicitudDespacho(lineas=[...]))`
        donde cada linea tiene cantidad_despachada = cantidad_solicitada.
        """
        # 1. Lock + validar estado
        solicitud = await self._lock_or_404(solicitud_id)
        if solicitud.estado != SolicitudEstado.APPROVED:
            raise SolicitudInvalidStateError(
                current=solicitud.estado.value, expected="approved"
            )
        # 2. Cargar detalles y construir lineas "completas"
        detalles = list(await self._repo.list_detalles(solicitud_id))
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
        return await self._apply_dispatch(
            solicitud=solicitud,
            detalles=detalles,
            lineas=lineas_payload,
            notas=None,
            user_id=user_id,
        )

    async def dispatch(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudDespacho",
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        """Despacha con payload por linea (despacho parcial permitido)."""
        solicitud = await self._lock_or_404(solicitud_id)
        if solicitud.estado != SolicitudEstado.APPROVED:
            raise SolicitudInvalidStateError(
                current=solicitud.estado.value, expected="approved"
            )
        if not payload.lineas:
            raise InvalidTransferQuantityError("El despacho debe tener al menos 1 linea")
        detalles = list(await self._repo.list_detalles(solicitud_id))
        detalles_by_id = {d.id_producto: d for d in detalles}
        lineas_payload = [
            {
                "id_producto": l.producto_id,
                "cantidad_despachada": l.cantidad_despachada,
                "barcode": l.barcode,
            }
            for l in payload.lineas
        ]
        return await self._apply_dispatch(
            solicitud=solicitud,
            detalles=detalles,
            lineas=lineas_payload,
            notas=payload.notas,
            user_id=user_id,
        )

    async def _apply_dispatch(
        self,
        *,
        solicitud: SolicitudRecarga,
        detalles: list[DetalleSolicitudRecarga],
        lineas: list[dict],
        notas: str | None,
        user_id: uuid.UUID | None,
    ) -> SolicitudView:
        """Logica transaccional comun al dispatch (total o parcial).

        IMPORTANTE (ADR-0003 / spec): el dispatch descuenta stock de
        `id_bodega_destino` (Principal), NO del origen. El origen (Aux)
        aun no tiene unidades; las recibira cuando el auxiliar las
        confirma via `receive`. Si descontaramos del origen, generariamos
        stock negativo en una bodega que no deberia tenerlo.
        """
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

        # 2. Aplicar movimientos OUT via MovementEngine (descuenta de Principal)
        now = _utcnow()
        for linea in lineas:
            pid = linea["id_producto"]
            cant = linea["cantidad_despachada"]
            if cant <= 0:
                continue
            await self._movement.apply(
                MovementRequest(
                    warehouse_id=solicitud.id_bodega_destino,  # Principal
                    product_id=pid,
                    movement_type=MovementType.OUT,
                    quantity=cant,
                    reference_type="solicitud_dispatch",
                    reference_id=solicitud.codigo,
                    notes=notas or f"Despacho {solicitud.codigo} desde Principal",
                    user_id=user_id,
                )
            )
            await self._repo.update_linea_despacho(
                solicitud_id=solicitud.id,
                producto_id=pid,
                cantidad=cant,
            )

        # 3. Actualizar estado y timestamp
        await self._repo.update_estado(
            solicitud.id, "in_transit", dispatched_at=now
        )
        await self._session.commit()

        # Métricas Fase 9: solicitudes despachadas (sin label para
        # mantener cardinalidad 0; los detalles se infieren de
        # SOLICITUDES_CREADAS.labels).
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

        # Deuda #7: notificar a operadores de destino (y admin/supervisor)
        # que se despachó la solicitud y deben recibirla.
        wh_destino_disp = await self._session.get(
            Warehouse, solicitud.id_bodega_destino
        )
        await self._notif.notify_role_except_actor(
            actor_id=user_id,
            roles=[UserRole.DESTINATION_OPERATOR],
            tipo=NotificationType.SOLICITUD_DISPATCHED.value,
            titulo=f"Solicitud {solicitud.codigo} despachada",
            mensaje=(
                f"Recibir en {wh_destino_disp.code if wh_destino_disp else 'destino'}"
            ),
            payload=(
                f'{{"solicitud_id": "{solicitud.id}", '
                f'"codigo": "{solicitud.codigo}"}}'
            ),
        )

        return await self._to_view(solicitud.id)

    # ============================================================== RECEIVE

    async def receive_solicitud(
        self,
        solicitud_id: uuid.UUID,
        lineas: list[dict],
        notas: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        """Recibe una o mas lineas (compat con tests previos).

        `lineas` es una lista de dicts con keys: id_producto, cantidad_recibida,
        barcode (opcional).
        """
        solicitud = await self._lock_or_404(solicitud_id)
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
        detalles = list(await self._repo.list_detalles(solicitud_id))
        return await self._apply_receive(
            solicitud=solicitud,
            detalles=detalles,
            lineas=lineas,
            notas=notas,
            user_id=user_id,
        )

    async def receive(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudRecepcion",
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        """Recibe con payload Pydantic (incluye barcode + incidencia)."""
        solicitud = await self._lock_or_404(solicitud_id)
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
        detalles = list(await self._repo.list_detalles(solicitud_id))
        lineas_dicts = [
            {
                "id_producto": l.producto_id,
                "cantidad_recibida": l.cantidad_recibida,
                "barcode": l.barcode,
                "incidencia": l.incidencia,
            }
            for l in payload.lineas
        ]
        return await self._apply_receive(
            solicitud=solicitud,
            detalles=detalles,
            lineas=lineas_dicts,
            notas=payload.notas,
            user_id=user_id,
        )

    async def _apply_receive(
        self,
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
                    f"Cantidad a recibir ({cant}) supera el pendiente ({pending}) "
                    f"para producto {pid}"
                )

            # Validar barcode si viene (Fase 5: usa el validador puro).
            # Reglas:
            # - Si el producto no tiene codigo_barras, el validador hace
            #   skip (match_product retorna True).
            # - Si el producto tiene codigo_barras, match_product valida
            #   formato + checksum del escaneado y compara normalizado.
            if barcode is not None:
                producto = await self._session.get(Product, pid)
                if producto is not None:
                    if not match_product(barcode, producto.codigo_barras):
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
            await self._movement.apply(
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
            await self._repo.update_linea_recepcion(
                solicitud_id=solicitud.id,
                producto_id=pid,
                cantidad=cant,
                barcode=barcode,
            )

        # 4. Decidir estado final
        detalles = list(await self._repo.list_detalles(solicitud.id))
        all_done = all(
            d.cantidad_recibida == d.cantidad_despachada for d in detalles
        )
        any_dispatched = any(d.cantidad_despachada > 0 for d in detalles)
        now = _utcnow()
        if all_done and any_dispatched:
            await self._repo.update_estado(
                solicitud.id, "received", received_at=now
            )
        else:
            await self._repo.update_estado(solicitud.id, "partially_received")

        if notas:
            # Append a notas (no sobreescribe)
            current = await self._repo.get_by_id(solicitud.id)
            if current is not None and current.notas:
                current.notas = current.notas + " | " + notas
            elif current is not None:
                current.notas = notas
            await self._session.flush()
        await self._session.commit()

        log.info(
            "solicitud.received",
            solicitud_id=str(solicitud.id),
            codigo=solicitud.codigo,
            total_lineas=len(lineas),
            user_id=str(user_id) if user_id else None,
        )

        # Métricas Fase 9: solicitudes recibidas (completa=True) o
        # parcialmente recibidas (completa=False). Cardinalidad 1 (label
        # con 2 valores).
        from app.modules.observability.metrics import (  # noqa: PLC0415
            SOLICITUDES_RECIBIDAS_TOTAL,
        )

        all_done = all(
            d.cantidad_recibida == d.cantidad_despachada for d in detalles
        )
        any_dispatched = any(d.cantidad_despachada > 0 for d in detalles)
        if all_done and any_dispatched:
            SOLICITUDES_RECIBIDAS_TOTAL.labels(completa="true").inc()
        else:
            SOLICITUDES_RECIBIDAS_TOTAL.labels(completa="false").inc()

        # Deuda #7: notificar a admin+supervisor (excluyendo al actor) que
        # la solicitud fue recibida (total o parcialmente).
        estado_notif = (
            "recibida" if all_done and any_dispatched else "parcialmente recibida"
        )
        await self._notif.notify_role_except_actor(
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

        return await self._to_view(solicitud.id)

    # ============================================================== CANCEL / REJECT

    async def cancel_solicitud(
        self, solicitud_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> SolicitudView:
        """Cancela una solicitud PENDING (origen la cancela antes de aprobar)."""
        solicitud = await self._lock_or_404(solicitud_id)
        if solicitud.estado != SolicitudEstado.PENDING:
            raise SolicitudInvalidStateError(
                current=solicitud.estado.value, expected="pending"
            )
        await self._repo.update_estado(solicitud_id, "cancelled")
        await self._session.commit()
        log.info(
            "solicitud.cancelled",
            solicitud_id=str(solicitud_id),
            codigo=solicitud.codigo,
            user_id=str(user_id) if user_id else None,
        )

        # Deuda #7: notificar a admin+supervisor (excluyendo al actor)
        # que se canceló una solicitud pendiente.
        await self._notif.notify_role_except_actor(
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

        return await self._to_view(solicitud_id)

    async def cancel(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudCancelacion | None" = None,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        """Sobrecarga: acepta ``SolicitudCancelacion`` opcional."""
        return await self.cancel_solicitud(solicitud_id, user_id=user_id)

    async def reject_solicitud(
        self,
        solicitud_id: uuid.UUID,
        motivo: str,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        """Rechaza una solicitud PENDING o APPROVED con motivo."""
        solicitud = await self._lock_or_404(solicitud_id)
        if solicitud.estado not in (
            SolicitudEstado.PENDING,
            SolicitudEstado.APPROVED,
        ):
            raise SolicitudInvalidStateError(
                current=solicitud.estado.value,
                expected=["pending", "approved"],
            )
        solicitud.motivo_rechazo = motivo
        await self._repo.update_estado(solicitud_id, "rejected")
        await self._session.commit()

        # Métricas Fase 9: solicitudes rechazadas.
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

        # Deuda #7: notificar a operadores de origen que la solicitud
        # fue rechazada (para que no esperen despacho).
        await self._notif.notify_role_except_actor(
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

        return await self._to_view(solicitud_id)

    async def reject(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudRechazo",
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        """Sobrecarga: acepta ``SolicitudRechazo`` Pydantic."""
        return await self.reject_solicitud(
            solicitud_id, payload.motivo, user_id=user_id
        )

    # ============================================================== LIST / GET

    async def list_solicitudes(
        self,
        estado: str | None = None,
        id_bodega_origen: uuid.UUID | None = None,
    ) -> list[SolicitudView]:
        """Lista solicitudes con filtros (compat con tests previos)."""
        rows = await self._repo.list(
            estado=estado, id_bodega_origen=id_bodega_origen
        )
        return [await self._to_view(s.id) for s in rows]

    async def list(
        self,
        *,
        estado: str | None = None,
        id_bodega_origen: uuid.UUID | None = None,
        id_bodega_destino: uuid.UUID | None = None,
        fecha_desde: datetime | None = None,
        fecha_hasta: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SolicitudView]:
        """Lista con filtros extendidos (Fase 3 prompt)."""
        rows = await self._repo.list(
            estado=estado,
            id_bodega_origen=id_bodega_origen,
            id_bodega_destino=id_bodega_destino,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            skip=skip,
            limit=limit,
        )
        return [await self._to_view(s.id) for s in rows]

    async def get_solicitud(self, solicitud_id: uuid.UUID) -> SolicitudView:
        solicitud = await self._repo.get_by_id(solicitud_id)
        if solicitud is None:
            raise SolicitudNotFoundError(str(solicitud_id))
        return await self._to_view(solicitud_id)

    async def get(self, solicitud_id: uuid.UUID) -> SolicitudView:
        return await self.get_solicitud(solicitud_id)

    # ============================================================== DISTRIBUCION

    async def get_distribucion_multibodega(
        self, sku: str
    ) -> "DistribucionMultibodegaResponse | None":
        """Vista de distribucion de un SKU por bodega (spec §4.1).

        Delega en ``StockMultibodegaService`` para mantener una sola
        implementacion. Retorna None si el SKU no existe.
        """
        from app.modules.solicitudes.schemas import DistribucionMultibodegaResponse

        svc = StockMultibodegaService(self._session)
        dist = await svc.distribucion_por_sku(sku)
        if dist is None:
            return None
        # Mapear dataclass interno → schema Pydantic
        from app.modules.solicitudes.schemas import DistribucionBodegaItem
        items = [
            DistribucionBodegaItem(
                bodega_id=b.bodega_id,
                bodega_codigo=b.bodega_code,
                bodega_nombre=b.bodega_name,
                bodega_tipo=b.bodega_type,
                total_quantity=b.total_quantity,
                min_quantity=b.min_quantity,
                max_quantity=b.max_quantity,
                estado=b.estado,  # type: ignore[arg-type]
                ubicacion_principal=None,  # F5+: completar con ubicaciones
            )
            for b in dist.bodegas
        ]
        return DistribucionMultibodegaResponse(
            producto_id=dist.producto_id,
            sku=dist.sku,
            nombre=dist.name,
            total_global=dist.total_global,
            bodegas=items,
        )

    # ============================================================== TRANSFERS LEGACY

    async def get_derived_transfer(
        self, codigo_legacy: str
    ) -> "TransferDerivedResponse | None":
        """Vista derivada de una solicitud como Transfer (compat legacy).

        Mapea:
        - solicitud.codigo == transfer.code
        - solicitud.id_bodega_origen == transfer.from_warehouse_id
        - solicitud.id_bodega_destino == transfer.to_warehouse_id
        - solicitud.estado → transfer.status (namespace unificado)
        - primera linea → transfer.product_id/quantity
        """
        from app.modules.solicitudes.schemas import (
            TransferDerivedLinea,
            TransferDerivedResponse,
        )

        solicitud = await self._repo.get_by_codigo(codigo_legacy)
        if solicitud is None:
            return None
        wh_origen = await self._session.get(Warehouse, solicitud.id_bodega_origen)
        wh_destino = await self._session.get(Warehouse, solicitud.id_bodega_destino)
        detalles = list(await self._repo.list_detalles(solicitud.id))

        # Mapear estado
        status_map = {
            SolicitudEstado.PENDING.value: "requested",
            SolicitudEstado.APPROVED.value: "approved",
            SolicitudEstado.IN_TRANSIT.value: "dispatched",
            SolicitudEstado.PARTIALLY_RECEIVED.value: "partially_received",
            SolicitudEstado.RECEIVED.value: "received",
            SolicitudEstado.REJECTED.value: "cancelled",
            SolicitudEstado.CANCELLED.value: "cancelled",
        }
        transfer_status = status_map.get(solicitud.estado.value, "requested")

        # Construir lineas
        lineas: list[TransferDerivedLinea] = []
        first_product_id = detalles[0].id_producto if detalles else uuid.uuid4()
        first_product_sku = ""
        first_product_name = ""
        first_quantity = Decimal("0")
        for d in detalles:
            prod = await self._session.get(Product, d.id_producto)
            lineas.append(
                TransferDerivedLinea(
                    producto_id=d.id_producto,
                    producto_sku=prod.sku if prod else "",
                    producto_nombre=prod.name if prod else "",
                    cantidad_solicitada=d.cantidad_solicitada,
                    cantidad_despachada=d.cantidad_despachada,
                    cantidad_recibida=d.cantidad_recibida,
                )
            )
            if prod and not first_product_sku:
                first_product_sku = prod.sku
                first_product_name = prod.name
            if not first_quantity:
                first_quantity = d.cantidad_solicitada

        return TransferDerivedResponse(
            id=solicitud.id,
            code=solicitud.codigo,
            from_warehouse_id=solicitud.id_bodega_origen,
            from_warehouse_code=wh_origen.code if wh_origen else "",
            to_warehouse_id=solicitud.id_bodega_destino,
            to_warehouse_code=wh_destino.code if wh_destino else "",
            product_id=first_product_id,
            product_sku=first_product_sku,
            product_name=first_product_name,
            quantity=first_quantity,
            received_quantity=detalles[0].cantidad_recibida if detalles else Decimal("0"),
            status=transfer_status,
            priority=solicitud.prioridad,
            notes=solicitud.notas,
            created_at=solicitud.created_at,
            approved_at=solicitud.approved_at,
            dispatched_at=solicitud.dispatched_at,
            received_at=solicitud.received_at,
            lineas=lineas,
        )

    # ============================================================== HELPERS

    def _validate_direction(
        self, origen: Warehouse, destino: Warehouse
    ) -> None:
        """Valida la regla de direccion (ADR-0002)."""
        if origen.id == destino.id:
            raise InvalidSolicitudDirectionError(
                "Origen y destino no pueden ser la misma bodega."
            )
        if origen.warehouse_type == "mecanico_box" and not origen.parent_warehouse_id:
            raise InvalidSolicitudDirectionError(
                f"Bodega origen '{origen.code}' es box sin auxiliar padre asignado."
            )
        if destino.warehouse_type == "mecanico_box":
            raise InvalidSolicitudDirectionError(
                f"Bodega destino '{destino.code}' es box de mecanico; "
                "no recibe solicitudes de recarga."
            )
        if origen.warehouse_type == "principal":
            raise InvalidSolicitudDirectionError(
                f"Bodega origen '{origen.code}' es principal; "
                "las recargas se originan en auxiliares o boxes."
            )
        if destino.warehouse_type != "principal":
            raise InvalidSolicitudDirectionError(
                f"Bodega destino '{destino.code}' debe ser 'principal'; "
                f"recibio '{destino.warehouse_type}'."
            )

    async def _lock_or_404(
        self, solicitud_id: uuid.UUID
    ) -> SolicitudRecarga:
        """Obtiene la solicitud con lock pesimista o lanza 404."""
        solicitud = await self._repo.get_by_id_with_lock(solicitud_id)
        if solicitud is None:
            raise SolicitudNotFoundError(str(solicitud_id))
        return solicitud

    async def _to_view(self, solicitud_id: uuid.UUID) -> SolicitudView:
        """Construye la vista interna (dataclass) a partir del modelo.

        Cachea bodegas y productos en la sesión actual para evitar N+1
        al expandir todas las lineas.
        """
        solicitud = await self._repo.get_by_id(solicitud_id)
        if solicitud is None:
            raise SolicitudNotFoundError(str(solicitud_id))

        # Cache de bodegas y productos en esta sesion
        wh_origen = await self._session.get(Warehouse, solicitud.id_bodega_origen)
        wh_destino = await self._session.get(Warehouse, solicitud.id_bodega_destino)

        detalles = list(await self._repo.list_detalles(solicitud.id))
        detalles_view: list[dict] = []
        total_unidades = Decimal("0")
        product_ids = [d.id_producto for d in detalles]
        productos: dict[uuid.UUID, Product] = {}
        if product_ids:
            stmt = select(Product).where(Product.id.in_(product_ids))
            result = await self._session.execute(stmt)
            for p in result.scalars().all():
                productos[p.id] = p

        for d in detalles:
            prod = productos.get(d.id_producto)
            detalles_view.append({
                "id_solicitud": d.id_solicitud,
                "id_producto": d.id_producto,
                "product_sku": prod.sku if prod else None,
                "product_name": prod.name if prod else None,
                "cantidad_solicitada": d.cantidad_solicitada,
                "cantidad_despachada": d.cantidad_despachada,
                "cantidad_recibida": d.cantidad_recibida,
                "barcode_validado": d.barcode_validado,
                "notas": d.notas,
            })
            total_unidades += d.cantidad_solicitada

        return SolicitudView(
            id=solicitud.id,
            codigo=solicitud.codigo,
            id_bodega_origen=solicitud.id_bodega_origen,
            id_bodega_origen_codigo=wh_origen.code if wh_origen else "",
            id_bodega_origen_nombre=wh_origen.name if wh_origen else "",
            id_bodega_origen_tipo=wh_origen.warehouse_type if wh_origen else "",
            id_bodega_destino=solicitud.id_bodega_destino,
            id_bodega_destino_codigo=wh_destino.code if wh_destino else "",
            id_bodega_destino_nombre=wh_destino.name if wh_destino else "",
            estado=_api_estado(solicitud.estado),
            prioridad=solicitud.prioridad,
            notas=solicitud.notas,
            motivo_rechazo=solicitud.motivo_rechazo,
            created_at=solicitud.created_at,
            approved_at=solicitud.approved_at,
            dispatched_at=solicitud.dispatched_at,
            received_at=solicitud.received_at,
            detalles=detalles_view,
            total_productos=len(detalles),
            total_unidades=total_unidades,
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)
