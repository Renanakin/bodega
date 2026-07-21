"""Router FastAPI para ordenes de compra (Fase 6).

Endpoints internos (requieren auth):
- GET    /api/v1/ordenes-compra                      - listar con filtros
- POST   /api/v1/ordenes-compra                      - crear (Borrador)
- GET    /api/v1/ordenes-compra/{oc_id}              - obtener
- PATCH  /api/v1/ordenes-compra/{oc_id}              - actualizar (solo si Borrador)
- POST   /api/v1/ordenes-compra/{oc_id}/enviar-correo - encolar email + token
- POST   /api/v1/ordenes-compra/{oc_id}/aprobar      - aprobar internamente
- POST   /api/v1/ordenes-compra/{oc_id}/rechazar     - rechazar internamente
- POST   /api/v1/ordenes-compra/{oc_id}/comprar      - marcar como comprada

Endpoints publicos (sin auth, rate limited) viven en `public_router.py`.
"""

from __future__ import annotations

import uuid
from datetime import date

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.ordenes_compra.schemas import (
    DetalleOCResponse,
    EnviarCorreoResponse,
    OCCreate,
    OCResponse,
    OCUpdate,
    RechazoPayload,
)
from app.modules.ordenes_compra.service import OrdenCompraService
from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_orden_service(session: AsyncSession = Depends(get_session)) -> OrdenCompraService:
    return OrdenCompraService(session)


def _to_response(view) -> OCResponse:  # type: ignore[no-untyped-def]
    """Adapta `OrdenCompraView` a `OCResponse`."""
    return OCResponse(
        id=view.id,
        codigo=view.codigo,
        id_bodega_principal=view.id_bodega_principal,
        id_supervisor=view.id_supervisor,
        supervisor_nombre=view.supervisor_nombre,
        supervisor_email=view.supervisor_email,
        proveedor_nombre=view.proveedor_nombre,
        proveedor_contacto=view.proveedor_contacto,
        estado=view.estado,
        total_estimado=view.total_estimado,
        notas=view.notas,
        motivo_rechazo=view.motivo_rechazo,
        email_enviado_at=view.email_enviado_at,
        aprobado_at=view.aprobado_at,
        comprado_at=view.comprado_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
        detalles=[
            DetalleOCResponse(
                id_orden_compra=d["id_orden_compra"],
                id_producto=d["id_producto"],
                product_sku=d.get("product_sku"),
                product_name=d.get("product_name"),
                cantidad_pedida=d["cantidad_pedida"],
                costo_unitario_pactado=d["costo_unitario_pactado"],
            )
            for d in view.detalles
        ],
    )


# --------------------------------------------------------------------------- LIST


@router.get("", response_model=list[OCResponse])
async def list_ordenes(
    estado: str | None = Query(
        default=None, description="borrador, enviado_a_supervisor, aprobado, rechazado, comprado"
    ),
    proveedor: str | None = Query(default=None, description="ILIKE sobre proveedor_nombre"),
    fecha_desde: date | None = Query(default=None, description="YYYY-MM-DD"),
    fecha_hasta: date | None = Query(default=None, description="YYYY-MM-DD"),
    _user=Depends(get_current_user),
    service: OrdenCompraService = Depends(get_orden_service),
) -> list[OCResponse]:
    views = await service.list_ordenes(
        estado=estado,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    return [_to_response(v) for v in views]


# -------------------------------------------------------------------------- CREATE


@router.post("", response_model=OCResponse, status_code=status.HTTP_201_CREATED)
async def create_oc(
    payload: OCCreate,
    _user=Depends(require_roles("admin", "supervisor")),
    service: OrdenCompraService = Depends(get_orden_service),
) -> OCResponse:
    view = await service.create_orden(
        id_bodega_principal=payload.id_bodega_principal,
        id_supervisor=payload.id_supervisor,
        proveedor_nombre=payload.proveedor_nombre,
        lineas=[line.model_dump() for line in payload.lineas],
        proveedor_contacto=payload.proveedor_contacto,
        notas=payload.notas,
    )
    return _to_response(view)


# -------------------------------------------------------------------------------- GET


@router.get("/{oc_id}", response_model=OCResponse)
async def get_oc(
    oc_id: uuid.UUID,
    _user=Depends(get_current_user),
    service: OrdenCompraService = Depends(get_orden_service),
) -> OCResponse:
    view = await service.get_orden(oc_id)
    return _to_response(view)


# ---------------------------------------------------------------------------- UPDATE


@router.patch("/{oc_id}", response_model=OCResponse)
async def update_oc(
    oc_id: uuid.UUID,
    payload: OCUpdate,
    _user=Depends(require_roles("admin", "supervisor")),
    service: OrdenCompraService = Depends(get_orden_service),
) -> OCResponse:
    data = payload.model_dump(exclude_unset=True)
    view = await service.update_orden(oc_id, **data)
    return _to_response(view)


# ---------------------------------------------------------------------- ENVIAR CORREO


@router.post("/{oc_id}/enviar-correo", response_model=EnviarCorreoResponse)
async def enviar_correo(
    oc_id: uuid.UUID,
    current_user=Depends(require_roles("admin", "supervisor")),
    service: OrdenCompraService = Depends(get_orden_service),
) -> EnviarCorreoResponse:
    """Encola email al supervisor y genera token de aprobacion.

    Cambia estado a `enviado_a_supervisor`. El token se devuelve SOLO
    en esta respuesta para facilitar testing E2E; en produccion NO se
    expone al cliente (viaja en el email via outbox).
    """
    view, token, outbox_id = await service.enviar_correo(oc_id, user_id=current_user.id)
    return EnviarCorreoResponse(
        oc=_to_response(view),
        approval_token=token,
        outbox_id=outbox_id,
    )


# SEPARATOR: APPROVE (internal) - /aprobar endpoint below


@router.post("/{oc_id}/aprobar", response_model=OCResponse)
async def aprobar_oc(
    oc_id: uuid.UUID,
    current_user=Depends(require_roles("admin", "supervisor")),
    service: OrdenCompraService = Depends(get_orden_service),
) -> OCResponse:
    """Aprobar OC desde la app (con auth)."""
    view = await service.aprobar_orden(oc_id, user_id=current_user.id)
    return _to_response(view)


# SEPARATOR: REJECT (internal) - /rechazar endpoint below


@router.post("/{oc_id}/rechazar", response_model=OCResponse)
async def rechazar_oc(
    oc_id: uuid.UUID,
    payload: RechazoPayload = Body(...),
    current_user=Depends(require_roles("admin", "supervisor")),
    service: OrdenCompraService = Depends(get_orden_service),
) -> OCResponse:
    """Rechazar OC desde la app (con auth)."""
    view = await service.rechazar_orden(oc_id, payload.motivo, user_id=current_user.id)
    return _to_response(view)


# ------------------------------------------------------------------------------ COMPRAR


@router.post("/{oc_id}/comprar", response_model=OCResponse)
async def marcar_comprada(
    oc_id: uuid.UUID,
    current_user=Depends(require_roles("admin", "supervisor")),
    service: OrdenCompraService = Depends(get_orden_service),
) -> OCResponse:
    """Marcar OC como comprada (proveedor entrego mercaderia)."""
    view = await service.marcar_comprada(oc_id, user_id=current_user.id)
    return _to_response(view)
