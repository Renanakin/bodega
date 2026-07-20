"""
OrdenCompraService: fachada delgada sobre actions/ y queries/.

Reglas:
- R3: la logica vive en actions/ y queries/. Este archivo es solo la
  fachada que mantiene la API publica estable (compatibilidad con
  router y public_router).
- ADR-0005: token HMAC firmado con expiracion 7 dias.
- ADR-0004: la OC NO se envia por SMTP en esta fase; el servicio
  registra un row en `email_outbox` (status='pending') que el worker
  Arq (Fase 7) procesa asincronicamente.
- El endpoint publico para aprobar/rechazar vive en `public_router.py`
  con rate limiting (5 req/min por IP).

API publica (delegada a actions/queries):
    - create_orden, update_orden, enviar_a_supervisor, enviar_correo,
      aprobar_orden, rechazar_orden, marcar_comprada, aprobar_con_token,
      list_ordenes, get_orden, get_orden_por_token.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notificaciones.service import NotificacionesService
from app.modules.ordenes_compra.actions._common import OrdenCompraView
from app.modules.ordenes_compra.actions.actualizar import update_orden as _update_orden
from app.modules.ordenes_compra.actions.aprobar import (
    aprobar_con_token as _aprobar_con_token,
    aprobar_orden as _aprobar_orden,
)
from app.modules.ordenes_compra.actions.crear import create_orden as _create_orden
from app.modules.ordenes_compra.actions.enviar import (
    enviar_a_supervisor as _enviar_a_supervisor,
    enviar_correo as _enviar_correo,
)
from app.modules.ordenes_compra.actions.marcar_comprada import (
    marcar_comprada as _marcar_comprada,
)
from app.modules.ordenes_compra.actions.rechazar import rechazar_orden as _rechazar_orden
from app.modules.ordenes_compra.queries.listar import list_ordenes as _list_ordenes
from app.modules.ordenes_compra.queries.obtener import (
    get_orden as _get_orden,
    get_orden_por_token as _get_orden_por_token,
)


class OrdenCompraService:
    """Fachada de OrdenCompraService. Logica en actions/ y queries/."""

    def __init__(
        self,
        session: AsyncSession,
        notif_service: NotificacionesService | None = None,
    ) -> None:
        self._session = session
        # Si el caller no inyecta un service, instanciamos uno por
        # defecto que comparte la misma session.
        self._notif: NotificacionesService = (
            notif_service if notif_service is not None else NotificacionesService(session)
        )

    # ============================================================== CREATE

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
        return await _create_orden(
            self._session,
            id_bodega_principal=id_bodega_principal,
            id_supervisor=id_supervisor,
            proveedor_nombre=proveedor_nombre,
            lineas=lineas,
            proveedor_contacto=proveedor_contacto,
            notas=notas,
        )

    # ============================================================== UPDATE

    async def update_orden(
        self,
        oc_id: uuid.UUID,
        *,
        proveedor_nombre: str | None = None,
        proveedor_contacto: str | None = None,
        notas: str | None = None,
        id_supervisor: uuid.UUID | None = None,
    ) -> OrdenCompraView:
        return await _update_orden(
            self._session, oc_id,
            proveedor_nombre=proveedor_nombre,
            proveedor_contacto=proveedor_contacto,
            notas=notas,
            id_supervisor=id_supervisor,
        )

    # ============================================================== ENVIAR

    async def enviar_a_supervisor(
        self,
        oc_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> tuple[OrdenCompraView, str]:
        return await _enviar_a_supervisor(
            self._session, self._notif, oc_id, user_id=user_id
        )

    async def enviar_correo(
        self,
        oc_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ) -> tuple[OrdenCompraView, str, uuid.UUID]:
        return await _enviar_correo(
            self._session, self._notif, oc_id, user_id=user_id
        )

    # ============================================================== APROBAR

    async def aprobar_orden(
        self, oc_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> OrdenCompraView:
        return await _aprobar_orden(
            self._session, self._notif, oc_id, user_id
        )

    async def aprobar_con_token(
        self, token: str, decision: str, motivo: str | None = None
    ) -> OrdenCompraView:
        return await _aprobar_con_token(
            self._session, self._notif, token, decision, motivo
        )

    # ============================================================== RECHAZAR

    async def rechazar_orden(
        self,
        oc_id: uuid.UUID,
        motivo: str,
        user_id: uuid.UUID | None = None,
    ) -> OrdenCompraView:
        return await _rechazar_orden(
            self._session, self._notif, oc_id, motivo, user_id
        )

    # ============================================================== COMPRADA

    async def marcar_comprada(
        self, oc_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> OrdenCompraView:
        return await _marcar_comprada(
            self._session, self._notif, oc_id, user_id
        )

    # ============================================================== LIST / GET

    async def list_ordenes(
        self,
        estado: str | None = None,
        proveedor: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> list[OrdenCompraView]:
        return await _list_ordenes(
            self._session,
            estado=estado,
            proveedor=proveedor,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )

    async def get_orden(self, oc_id: uuid.UUID) -> OrdenCompraView:
        return await _get_orden(self._session, oc_id)

    async def get_orden_por_token(self, token: str) -> OrdenCompraView:
        return await _get_orden_por_token(self._session, self._notif, token)


# Re-export para retrocompatibilidad con imports que hacen
# ``from app.modules.ordenes_compra.service import OrdenCompraView``.
__all__ = ["OrdenCompraService", "OrdenCompraView"]
