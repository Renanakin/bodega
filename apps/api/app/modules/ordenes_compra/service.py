"""
OrdenCompraService: workflow de ordenes de compra externas (Fase 6).

Reglas:
- ADR-0005: token HMAC firmado con expiracion 7 dias.
- ADR-0004: la OC NO se envia por SMTP en esta fase; el servicio registra
  un row en `email_outbox` (status='pending') que el worker Arq (Fase 7)
  procesara asincronicamente.
- El endpoint publico para aprobar/rechazar vive en `public_router.py`
  con rate limiting (5 req/min por IP).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.errors import (
    InvalidOrdenCompraStatusError,
    OrdenCompraNotFoundError,
    ProductNotFoundError,
    WarehouseNotFoundError,
)
from app.core.logging import get_logger
from app.core.security import (
    ApprovalTokenExpiredError,
    ApprovalTokenInvalidError,
    issue_approval_token,
    verify_approval_token,
)
from app.db.models.notificaciones import NotificationType
from app.db.models.ordenes_compra import (
    DetalleOrdenCompra,
    EmailOutbox,
    OrdenCompra,
    OrdenCompraEstado,
)
from app.db.models.products import Product
from app.db.models.supervisores import Supervisor
from app.db.models.users import UserRole
from app.db.models.warehouses import Warehouse
from app.modules.notificaciones.service import NotificacionesService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


# Estado terminal: un OC en estos estados NO acepta nuevas transiciones.
ESTADOS_TERMINALES = frozenset({
    OrdenCompraEstado.RECHAZADO,
    OrdenCompraEstado.COMPRADO,
})


@dataclass(slots=True)
class OrdenCompraView:
    """Vista agregada que el router expone como JSON."""

    id: uuid.UUID
    codigo: str
    id_bodega_principal: uuid.UUID
    id_supervisor: uuid.UUID
    supervisor_nombre: str | None
    supervisor_email: str | None
    proveedor_nombre: str
    proveedor_contacto: str | None
    estado: str
    total_estimado: Decimal
    notas: str | None
    motivo_rechazo: str | None
    email_enviado_at: datetime | None
    email_token_jti: str | None
    aprobado_at: datetime | None
    comprado_at: datetime | None
    created_at: datetime
    updated_at: datetime | None
    detalles: list[dict] = field(default_factory=list)


class OrdenCompraService:
    def __init__(
        self,
        session: AsyncSession,
        notif_service: NotificacionesService | None = None,
    ) -> None:
        self._session = session
        # Deuda #7: emision automatica de notificaciones in-app en cada
        # transicion. Si el caller no inyecta un service, instanciamos
        # uno por defecto que comparte la misma session.
        self._notif: NotificacionesService = (
            notif_service if notif_service is not None else NotificacionesService(session)
        )



    async def create_orden(
        self,
        *,
        id_bodega_principal: uuid.UUID,
        id_supervisor: uuid.UUID,
        proveedor_nombre: str,
        lineas: list[dict],
        proveedor_contacto: str | None = None,
        notas: str | None = None,
    ) -> OrdenCompraView:
        """Crea una OC en estado BORRADOR.

        Args:
            id_bodega_principal: FK a warehouses (debe ser tipo=principal).
            id_supervisor: FK a supervisores (debe estar activo).
            proveedor_nombre: nombre libre del proveedor externo.
            lineas: lista de dicts con `id_producto`, `cantidad_pedida`,
                `costo_unitario_pactado`.
            proveedor_contacto: opcional, telefono/email del proveedor.
            notas: opcional, notas libres.

        Returns:
            `OrdenCompraView` con la OC recien creada.

        Raises:
            WarehouseNotFoundError: si la bodega no existe o no es principal.
            ProductNotFoundError: si algun producto no existe.
            SupervisorNotFoundError / InvalidOrdenCompraStatusError: si el
                supervisor no existe o esta inactivo.
        """
        # Validar bodega principal
        wh = await self._session.get(Warehouse, id_bodega_principal)
        if wh is None:
            raise WarehouseNotFoundError(str(id_bodega_principal))
        if wh.warehouse_type != "principal":
            raise InvalidOrdenCompraStatusError(
                current=wh.warehouse_type,
                expected="principal (bodega)",
            )

        # Validar supervisor
        sup = await self._session.get(Supervisor, id_supervisor)
        if sup is None or not sup.activo:
            raise OrdenCompraNotFoundError(str(id_supervisor))

        if not lineas:
            raise InvalidOrdenCompraStatusError(current="empty", expected=">=1 linea")

        # Validar productos y calcular total
        total = Decimal("0")
        for linea in lineas:
            p = await self._session.get(Product, linea["id_producto"])
            if p is None:
                raise ProductNotFoundError(str(linea["id_producto"]))
            total += linea["cantidad_pedida"] * linea["costo_unitario_pactado"]

        # Generar codigo OC-NNNN (secuencial, con prefijo zero-padded)
        count_stmt = select(OrdenCompra)
        result = await self._session.execute(count_stmt)
        next_code = f"OC-{len(result.scalars().all()) + 1:04d}"

        oc = OrdenCompra(
            id=uuid.uuid4(),
            codigo=next_code,
            id_bodega_principal=id_bodega_principal,
            id_supervisor=id_supervisor,
            proveedor_nombre=proveedor_nombre.strip(),
            proveedor_contacto=proveedor_contacto,
            estado=OrdenCompraEstado.BORRADOR,
            total_estimado=total,
            notas=notas,
        )
        self._session.add(oc)
        # Flush para que `oc.id` exista antes de crear los detalles
        # (la PK compuesta del detalle referencia `id_orden_compra`).
        await self._session.flush()
        for linea in lineas:
            detalle = DetalleOrdenCompra(
                id_orden_compra=oc.id,
                id_producto=linea["id_producto"],
                cantidad_pedida=linea["cantidad_pedida"],
                costo_unitario_pactado=linea["costo_unitario_pactado"],
            )
            self._session.add(detalle)
        await self._session.commit()
        await self._session.refresh(oc)
        log.info(
            "orden_compra.created",
            oc_id=str(oc.id),
            codigo=oc.codigo,
            total=str(total),
            lineas=len(lineas),
        )
        return await self._to_view(oc)



    async def update_orden(
        self,
        oc_id: uuid.UUID,
        *,
        proveedor_nombre: str | None = None,
        proveedor_contacto: str | None = None,
        notas: str | None = None,
        id_supervisor: uuid.UUID | None = None,
    ) -> OrdenCompraView:
        """Actualiza una OC SOLO si esta en estado BORRADOR.

        Raises:
            InvalidOrdenCompraStatusError: si la OC no esta en BORRADOR.
            SupervisorNotFoundError: si se cambia el supervisor a uno inexistente.
        """
        oc = await self._require_oc(oc_id)
        if oc.estado != OrdenCompraEstado.BORRADOR:
            raise InvalidOrdenCompraStatusError(
                current=oc.estado.value,
                expected=OrdenCompraEstado.BORRADOR.value,
            )

        if id_supervisor is not None and id_supervisor != oc.id_supervisor:
            sup = await self._session.get(Supervisor, id_supervisor)
            if sup is None or not sup.activo:
                raise OrdenCompraNotFoundError(str(id_supervisor))
            oc.id_supervisor = id_supervisor

        if proveedor_nombre is not None:
            oc.proveedor_nombre = proveedor_nombre.strip()
        if proveedor_contacto is not None:
            oc.proveedor_contacto = proveedor_contacto
        if notas is not None:
            oc.notas = notas

        await self._session.commit()
        await self._session.refresh(oc)
        log.info("orden_compra.updated", oc_id=str(oc.id))
        return await self._to_view(oc)



    async def enviar_a_supervisor(
        self,
        oc_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> tuple[OrdenCompraView, str]:
        """Alias historico (Fase 8). Ver `enviar_correo` para el nombre canonico.

        Devuelve solo (view, token) por compatibilidad con la API previa.
        """
        view, token, _outbox_id = await self.enviar_correo(oc_id, user_id=user_id)
        return view, token

    async def enviar_correo(
        self,
        oc_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> tuple[OrdenCompraView, str, uuid.UUID]:
        """Envia la OC a supervisor (encola email en outbox).

        Pasos (ADR-0004 + ADR-0005):
        1. Validar estado BORRADOR.
        2. Generar jti + token HMAC con expiracion 7d.
        3. Cambiar estado a ENVIADO_A_SUPERVISOR.
        4. Insertar row en `email_outbox` con status='pending'.

        Args:
            oc_id: UUID de la OC a enviar.

        Returns:
            Tupla (view actualizada, token generado, outbox_id). El token NO
            se devuelve al cliente en la API final (viaja en el email); aqui
            se incluye solo para facilitar testing E2E.

        Raises:
            InvalidOrdenCompraStatusError: si la OC no esta en BORRADOR.
        """
        oc = await self._require_oc(oc_id)
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
        sup = await self._session.get(Supervisor, oc.id_supervisor)
        to_email = sup.email if sup else "noreply@bodega.example"
        subject = f"Aprobacion requerida: OC {oc.codigo}"
        body_html = (
            f"<h1>OC {oc.codigo}</h1>"
            f"<p>Proveedor: {oc.proveedor_nombre}</p>"
            f"<p>Total estimado: {oc.total_estimado}</p>"
            f'<p><a href="/ordenes-compra/aprobar/{token}">Aprobar/Rechazar OC</a></p>'
        )
        context = (
            '{"oc_id": "' + str(oc.id) + '", '
            '"codigo": "' + oc.codigo + '", '
            '"token": "' + token + '"}'
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
        self._session.add(outbox)
        await self._session.commit()
        await self._session.refresh(oc)

        log.info(
            "orden_compra.enviada",
            oc_id=str(oc.id),
            codigo=oc.codigo,
            supervisor_email=to_email,
            outbox_id=str(outbox.id),
            jti=jti,
        )

        # Deuda #7: notificar a admin+supervisor (excluyendo al actor) que
        # la OC fue enviada al supervisor externo. La aprobacion final
        # vendra por el flujo publico (token).
        await self._notif.notify_role_except_actor(
            actor_id=user_id,
            roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
            tipo=NotificationType.ORDEN_COMPRA_ENVIADA.value,
            titulo=f"OC {oc.codigo} enviada a supervisor",
            mensaje=f"Proveedor: {oc.proveedor_nombre} - Total: {oc.total_estimado}",
            payload=(
                f'{{"oc_id": "{oc.id}", '
                f'"codigo": "{oc.codigo}"}}'
            ),
        )

        return await self._to_view(oc), token, outbox.id



    async def aprobar_orden(
        self, oc_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> OrdenCompraView:
        """Aprobar OC desde la app (con auth). Solo valido si esta ENVIADO."""
        oc = await self._require_oc(oc_id)
        if oc.estado != OrdenCompraEstado.ENVIADO_A_SUPERVISOR:
            raise InvalidOrdenCompraStatusError(
                current=oc.estado.value,
                expected=OrdenCompraEstado.ENVIADO_A_SUPERVISOR.value,
            )
        oc.estado = OrdenCompraEstado.APROBADO
        oc.aprobado_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(oc)
        log.info("orden_compra.approved", oc_id=str(oc.id), codigo=oc.codigo)

        # Deuda #7: notificar a admin+supervisor (excluyendo al actor).
        await self._notif.notify_role_except_actor(
            actor_id=user_id,
            roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
            tipo=NotificationType.ORDEN_COMPRA_APROBADA.value,
            titulo=f"OC {oc.codigo} aprobada",
            mensaje=f"Proveedor: {oc.proveedor_nombre}",
            payload=(
                f'{{"oc_id": "{oc.id}", '
                f'"codigo": "{oc.codigo}"}}'
            ),
        )

        return await self._to_view(oc)

    async def rechazar_orden(
        self,
        oc_id: uuid.UUID,
        motivo: str,
        user_id: uuid.UUID | None = None,
    ) -> OrdenCompraView:
        """Rechazar OC desde la app (con auth). Solo valido si esta ENVIADO."""
        oc = await self._require_oc(oc_id)
        if oc.estado != OrdenCompraEstado.ENVIADO_A_SUPERVISOR:
            raise InvalidOrdenCompraStatusError(
                current=oc.estado.value,
                expected=OrdenCompraEstado.ENVIADO_A_SUPERVISOR.value,
            )
        oc.estado = OrdenCompraEstado.RECHAZADO
        oc.motivo_rechazo = motivo
        await self._session.commit()
        await self._session.refresh(oc)
        log.info(
            "orden_compra.rejected",
            oc_id=str(oc.id),
            codigo=oc.codigo,
            motivo=motivo,
        )

        # Deuda #7: notificar a admin+supervisor (excluyendo al actor).
        await self._notif.notify_role_except_actor(
            actor_id=user_id,
            roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
            tipo=NotificationType.ORDEN_COMPRA_RECHAZADA.value,
            titulo=f"OC {oc.codigo} rechazada",
            mensaje=f"Motivo: {motivo}",
            payload=(
                f'{{"oc_id": "{oc.id}", '
                f'"codigo": "{oc.codigo}", '
                f'"motivo": "{motivo}"}}'
            ),
        )

        return await self._to_view(oc)

    async def marcar_comprada(
        self, oc_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> OrdenCompraView:
        """Marcar OC como comprada (proveedor entrego mercaderia).

        Solo valido si esta APROBADO.
        """
        oc = await self._require_oc(oc_id)
        if oc.estado != OrdenCompraEstado.APROBADO:
            raise InvalidOrdenCompraStatusError(
                current=oc.estado.value,
                expected=OrdenCompraEstado.APROBADO.value,
            )
        oc.estado = OrdenCompraEstado.COMPRADO
        oc.comprado_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(oc)
        log.info("orden_compra.comprada", oc_id=str(oc.id), codigo=oc.codigo)

        # Deuda #7: notificar a admin+supervisor (excluyendo al actor).
        await self._notif.notify_role_except_actor(
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

        return await self._to_view(oc)



    async def aprobar_con_token(
        self, token: str, decision: str, motivo: str | None = None
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
            from app.core.errors import ExpiredApprovalTokenError
            raise ExpiredApprovalTokenError() from e
        except ApprovalTokenInvalidError as e:
            from app.core.errors import InvalidApprovalTokenError
            raise InvalidApprovalTokenError() from e

        oc_id = uuid.UUID(payload["orden_id"])
        oc = await self._require_oc(oc_id)

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

        await self._session.commit()
        await self._session.refresh(oc)
        log.info(
            "orden_compra.decided_via_token",
            oc_id=str(oc.id),
            codigo=oc.codigo,
            decision=decision,
        )

        # Deuda #7: notificar a admin+supervisor. En el flujo por token
        # no hay un User autenticado (el supervisor externo decidio), asi
        # que pasamos user_id=None y NO se excluye a nadie.
        if decision == "approve":
            await self._notif.notify_role_except_actor(
                actor_id=None,
                roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
                tipo=NotificationType.ORDEN_COMPRA_APROBADA.value,
                titulo=f"OC {oc.codigo} aprobada (vía token)",
                mensaje=f"Proveedor: {oc.proveedor_nombre}",
                payload=(
                    f'{{"oc_id": "{oc.id}", '
                    f'"codigo": "{oc.codigo}", '
                    f'"via": "token"}}'
                ),
            )
        else:
            await self._notif.notify_role_except_actor(
                actor_id=None,
                roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
                tipo=NotificationType.ORDEN_COMPRA_RECHAZADA.value,
                titulo=f"OC {oc.codigo} rechazada (vía token)",
                mensaje=(
                    f"Motivo: {oc.motivo_rechazo or 'No especificado'}"
                ),
                payload=(
                    f'{{"oc_id": "{oc.id}", '
                    f'"codigo": "{oc.codigo}", '
                    f'"via": "token"}}'
                ),
            )

        return await self._to_view(oc)



    async def list_ordenes(
        self,
        estado: str | None = None,
        proveedor: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> list[OrdenCompraView]:
        """Lista OCs con filtros opcionales.

        Args:
            estado: filtrar por estado exacto (borrador, enviado_a_supervisor, ...).
            proveedor: filtro ILIKE sobre `proveedor_nombre`.
            fecha_desde: OC con created_at >= fecha_desde (00:00).
            fecha_hasta: OC con created_at <= fecha_hasta (23:59:59).
        """
        stmt = select(OrdenCompra).order_by(OrdenCompra.created_at.desc())
        if estado:
            stmt = stmt.where(OrdenCompra.estado == estado)
        if proveedor:
            stmt = stmt.where(OrdenCompra.proveedor_nombre.ilike(f"%{proveedor}%"))
        if fecha_desde is not None:
            stmt = stmt.where(OrdenCompra.created_at >= datetime.combine(fecha_desde, datetime.min.time(), tzinfo=UTC))
        if fecha_hasta is not None:
            stmt = stmt.where(OrdenCompra.created_at <= datetime.combine(fecha_hasta, datetime.max.time(), tzinfo=UTC))
        result = await self._session.execute(stmt)
        return [await self._to_view(o) for o in result.scalars().all()]

    async def get_orden(self, oc_id: uuid.UUID) -> OrdenCompraView:
        oc = await self._require_oc(oc_id)
        return await self._to_view(oc)



    async def get_orden_por_token(self, token: str) -> OrdenCompraView:
        """Lee la OC asociada al token (sin auth, sin mutar estado).

        Raises:
            InvalidApprovalTokenError: firma invalida o malformada.
            ExpiredApprovalTokenError: token expirado.
            InvalidOrdenCompraStatusError: si la OC ya fue procesada.
        """
        try:
            payload = verify_approval_token(token)
        except ApprovalTokenExpiredError as e:
            from app.core.errors import ExpiredApprovalTokenError
            raise ExpiredApprovalTokenError() from e
        except ApprovalTokenInvalidError as e:
            from app.core.errors import InvalidApprovalTokenError
            raise InvalidApprovalTokenError() from e

        oc_id = uuid.UUID(payload["orden_id"])
        oc = await self._require_oc(oc_id)
        return await self._to_view(oc)



    async def _require_oc(self, oc_id: uuid.UUID) -> OrdenCompra:
        oc = await self._session.get(OrdenCompra, oc_id)
        if oc is None:
            raise OrdenCompraNotFoundError(str(oc_id))
        return oc

    async def _to_view(self, oc: OrdenCompra) -> OrdenCompraView:
        detalles_stmt = select(DetalleOrdenCompra).where(
            DetalleOrdenCompra.id_orden_compra == oc.id
        )
        detalles = list((await self._session.execute(detalles_stmt)).scalars().all())
        detalles_view: list[dict] = []
        for d in detalles:
            p = await self._session.get(Product, d.id_producto)
            detalles_view.append({
                "id_orden_compra": d.id_orden_compra,
                "id_producto": d.id_producto,
                "product_sku": p.sku if p else None,
                "product_name": p.name if p else None,
                "cantidad_pedida": d.cantidad_pedida,
                "costo_unitario_pactado": d.costo_unitario_pactado,
            })

        sup = await self._session.get(Supervisor, oc.id_supervisor)
        return OrdenCompraView(
            id=oc.id,
            codigo=oc.codigo,
            id_bodega_principal=oc.id_bodega_principal,
            id_supervisor=oc.id_supervisor,
            supervisor_nombre=sup.nombre if sup else None,
            supervisor_email=sup.email if sup else None,
            proveedor_nombre=oc.proveedor_nombre,
            proveedor_contacto=oc.proveedor_contacto,
            estado=oc.estado.value,
            total_estimado=oc.total_estimado,
            notas=oc.notas,
            motivo_rechazo=oc.motivo_rechazo,
            email_enviado_at=oc.email_enviado_at,
            email_token_jti=oc.email_token_jti,
            aprobado_at=oc.aprobado_at,
            comprado_at=oc.comprado_at,
            created_at=oc.created_at,
            updated_at=oc.created_at,  # modelo reusa created_at_column para updated_at
            detalles=detalles_view,
        )
