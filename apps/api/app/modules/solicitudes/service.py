"""
SolicitudService: fachada delgada sobre actions/ y queries/.

Reglas:
- R3: la logica vive en actions/ y queries/. Este archivo es solo la
  fachada que mantiene la API publica estable (compatibilidad con
  router y tests existentes).
- R4: toda escritura de stock pasa por MovementEngine.
- ADR-0002: origen ∈ {auxiliar, mecanico_box con parent_warehouse_id}, destino = principal.
- ADR-0003: namespace unificado pending/approved/in_transit/received/partial/...

API publica (delegada a actions/queries):
    - create_solicitud, create, approve_solicitud, approve,
      dispatch_solicitud, dispatch, receive_solicitud, receive,
      reject_solicitud, reject, cancel_solicitud, cancel,
      list_solicitudes, get_solicitud,
      get_distribucion_multibodega, get_derived_transfer.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notificaciones.service import NotificacionesService
from app.modules.solicitudes.actions._common import SolicitudView
from app.modules.solicitudes.actions.aprobar import (
    approve as _approve,
    approve_solicitud as _approve_solicitud,
)
from app.modules.solicitudes.actions.cancelar import (
    cancel as _cancel,
    cancel_solicitud as _cancel_solicitud,
)
from app.modules.solicitudes.actions.crear import (
    create as _create,
    create_solicitud as _create_solicitud,
)
from app.modules.solicitudes.actions.despachar import (
    dispatch as _dispatch,
    dispatch_solicitud as _dispatch_solicitud,
)
from app.modules.solicitudes.actions.recibir import (
    receive as _receive,
    receive_solicitud as _receive_solicitud,
)
from app.modules.solicitudes.actions.rechazar import (
    reject as _reject,
    reject_solicitud as _reject_solicitud,
)
from app.modules.solicitudes.queries.distribucion import (
    get_distribucion_multibodega as _get_distribucion_multibodega,
)
from app.modules.solicitudes.queries.listar import (
    list_solicitudes as _list_solicitudes,
    list_with_filters as _list_with_filters,
)
from app.modules.solicitudes.queries.obtener import get_solicitud as _get_solicitud
from app.modules.solicitudes.queries.transfers import (
    get_derived_transfer as _get_derived_transfer,
)
from app.modules.solicitudes.repository import SolicitudRepository
from app.shared.movement_engine import MovementEngine


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


class SolicitudService:
    """Fachada de SolicitudService. Logica en actions/ y queries/."""

    def __init__(
        self,
        session: AsyncSession,
        notif_service: NotificacionesService | None = None,
    ) -> None:
        self._session = session
        self._repo = SolicitudRepository(session)
        self._movement = MovementEngine(session)
        # Si el caller no inyecta un service (e.g. tests legacy),
        # creamos uno por defecto que comparte la misma session, asi
        # el comportamiento es consistente.
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
        return await _create_solicitud(
            self._session, self._repo, self._notif,
            id_bodega_origen=id_bodega_origen,
            id_bodega_destino=id_bodega_destino,
            lineas=lineas,
            prioridad=prioridad,
            notas=notas,
            user_id=user_id,
        )

    async def create(
        self, payload: "SolicitudCreate", user_id: uuid.UUID | None = None
    ) -> SolicitudView:
        return await _create(
            self._session, self._repo, self._notif, payload, user_id
        )

    # ============================================================== APPROVE

    async def approve_solicitud(
        self, solicitud_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> SolicitudView:
        return await _approve_solicitud(
            self._session, self._repo, self._notif, solicitud_id, user_id
        )

    async def approve(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudAprobacion | None" = None,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        return await _approve(
            self._session, self._repo, self._notif,
            solicitud_id, payload, user_id,
        )

    # ============================================================== DISPATCH

    async def dispatch_solicitud(
        self, solicitud_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> SolicitudView:
        return await _dispatch_solicitud(
            self._session, self._repo, self._movement, self._notif,
            solicitud_id, user_id,
        )

    async def dispatch(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudDespacho",
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        return await _dispatch(
            self._session, self._repo, self._movement, self._notif,
            solicitud_id, payload, user_id,
        )

    # ============================================================== RECEIVE

    async def receive_solicitud(
        self,
        solicitud_id: uuid.UUID,
        lineas: list[dict],
        notas: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        return await _receive_solicitud(
            self._session, self._repo, self._movement, self._notif,
            solicitud_id, lineas, notas, user_id,
        )

    async def receive(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudRecepcion",
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        return await _receive(
            self._session, self._repo, self._movement, self._notif,
            solicitud_id, payload, user_id,
        )

    # ============================================================== REJECT / CANCEL

    async def reject_solicitud(
        self,
        solicitud_id: uuid.UUID,
        motivo: str,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        return await _reject_solicitud(
            self._session, self._repo, self._notif,
            solicitud_id, motivo, user_id,
        )

    async def reject(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudRechazo",
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        return await _reject(
            self._session, self._repo, self._notif,
            solicitud_id, payload, user_id,
        )

    async def cancel_solicitud(
        self, solicitud_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> SolicitudView:
        return await _cancel_solicitud(
            self._session, self._repo, self._notif, solicitud_id, user_id
        )

    async def cancel(
        self,
        solicitud_id: uuid.UUID,
        payload: "SolicitudCancelacion | None" = None,
        user_id: uuid.UUID | None = None,
    ) -> SolicitudView:
        return await _cancel(
            self._session, self._repo, self._notif,
            solicitud_id, payload, user_id,
        )

    # ============================================================== LIST / GET

    async def list_solicitudes(
        self,
        estado: str | None = None,
        id_bodega_origen: uuid.UUID | None = None,
    ) -> list[SolicitudView]:
        return await _list_solicitudes(
            self._session, self._repo,
            estado=estado, id_bodega_origen=id_bodega_origen,
        )

    async def list(
        self,
        *,
        estado: str | None = None,
        id_bodega_origen: uuid.UUID | None = None,
        id_bodega_destino: uuid.UUID | None = None,
        fecha_desde=None,
        fecha_hasta=None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SolicitudView]:
        return await _list_with_filters(
            self._session, self._repo,
            estado=estado,
            id_bodega_origen=id_bodega_origen,
            id_bodega_destino=id_bodega_destino,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            skip=skip,
            limit=limit,
        )

    async def get_solicitud(self, solicitud_id: uuid.UUID) -> SolicitudView:
        return await _get_solicitud(self._session, self._repo, solicitud_id)

    async def get(self, solicitud_id: uuid.UUID) -> SolicitudView:
        return await self.get_solicitud(solicitud_id)

    # ============================================================== DISTRIBUCION

    async def get_distribucion_multibodega(
        self, sku: str
    ) -> "DistribucionMultibodegaResponse | None":
        return await _get_distribucion_multibodega(self._session, sku)

    # ============================================================== TRANSFERS LEGACY

    async def get_derived_transfer(
        self, codigo_legacy: str
    ) -> "TransferDerivedResponse | None":
        return await _get_derived_transfer(
            self._session, self._repo, codigo_legacy
        )


# Re-export SolicitudView para retrocompatibilidad con imports que
# hacen ``from app.modules.solicitudes.service import SolicitudView``.
__all__ = ["SolicitudService", "SolicitudView"]
