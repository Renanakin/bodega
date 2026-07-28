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

from app.core.cursor import apply_cursor, encode_cursor
from app.db.models.ordenes_compra import OrdenCompra
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.ordenes_compra.schemas import (
    DetalleOCResponse,
    EnviarCorreoResponse,
    OCCreate,
    OCListResponse,
    OCResponse,
    OCUpdate,
    RechazoPayload,
)
from app.modules.ordenes_compra.service import OrdenCompraService
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# BUG 13 (fix 2026-07-23): redirect_slashes=False.
# Nota historica: el bug original del flujo E2E (un POST daba 404 con
# el cuerpo interpretado como oc_id) NO era de routing - era que el
# script pasaba el id de `users` donde el endpoint espera id de
# `supervisores`. El `redirect_slashes=False` se mantiene como safety
# net: en este router coexisten `POST /` (raiz) y `POST /{oc_id}/...`
# (sub-recursos), y el redirect default de Starlette puede enmascarar
# errores del cliente. Con redirect_slashes=False, una URL mal
# formada da 404 limpio en vez de un 307 confuso.
router = APIRouter(redirect_slashes=False)


def get_orden_service(session: AsyncSession = Depends(get_session)) -> OrdenCompraService:
    return OrdenCompraService(session)


def _to_response(view, last_approval_token: str | None = None) -> OCResponse:  # type: ignore[no-untyped-def]
    """Adapta `OrdenCompraView` a `OCResponse`.

    Args:
        view: OrdenCompraView (dataclass con los datos de la OC).
        last_approval_token: Si viene, lo expone en el response. Solo el
            endpoint GET con ``?include_token=true`` lo pasa; el resto
            nunca expone el token.
    """
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
        last_approval_token=last_approval_token,
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


# --------------------------------------------------------------------------- LIST


@router.get("")
async def list_ordenes(
    estado: str | None = Query(
        default=None, description="borrador, enviado_a_supervisor, aprobado, rechazado, comprado"
    ),
    proveedor: str | None = Query(default=None, description="ILIKE sobre proveedor_nombre"),
    fecha_desde: date | None = Query(default=None, description="YYYY-MM-DD"),
    fecha_hasta: date | None = Query(default=None, description="YYYY-MM-DD"),
    cursor: str | None = Query(
        default=None,
        description="P0 (Big-O): cursor opaco. Si viene, devuelve wrapper con paginacion.",
    ),
    paginated: bool = Query(
        default=False,
        description="P0 (Big-O): si True, devuelve wrapper con paginacion "
                    "aunque no se envie cursor (primera pagina).",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    _user=Depends(get_current_user),
    service: OrdenCompraService = Depends(get_orden_service),
):
    """Lista OCs con filtros.

    P0 (roadmap Big-O): si se envia `cursor` o `paginated=true`, devuelve
    ``OCListResponse`` con paginacion cursor-based O(log n + p). Sin
    cursor, devuelve la lista plana (compat hacia atras) con `limit`
    (cap 200).
    """
    from app.core.cursor import InvalidCursorError
    from app.modules.ordenes_compra.queries.listar import list_ordenes as _list_ordenes_q

    if cursor is not None or paginated:
        try:
            stmt = select(OrdenCompra).order_by(
                OrdenCompra.created_at.desc(),
                OrdenCompra.id.desc(),
            )
            if estado:
                stmt = stmt.where(OrdenCompra.estado == estado)
            if proveedor:
                stmt = stmt.where(OrdenCompra.proveedor_nombre.ilike(f"%{proveedor}%"))
            if fecha_desde is not None:
                from datetime import UTC, datetime
                stmt = stmt.where(
                    OrdenCompra.created_at >= datetime.combine(fecha_desde, datetime.min.time(), tzinfo=UTC)
                )
            if fecha_hasta is not None:
                from datetime import UTC, datetime
                stmt = stmt.where(
                    OrdenCompra.created_at <= datetime.combine(fecha_hasta, datetime.max.time(), tzinfo=UTC)
                )
            stmt = apply_cursor(
                stmt, cursor, OrdenCompra.created_at, OrdenCompra.id
            )
            stmt = stmt.limit(limit + 1)
            result = await service._session.execute(stmt)
            ocs = list(result.scalars().all())
            has_more = len(ocs) > limit
            ocs = ocs[:limit]
            from app.modules.ordenes_compra.actions._common import to_views_batch
            views = await to_views_batch(service._session, ocs)
            next_cursor = (
                encode_cursor(views[-1].created_at, views[-1].id) if has_more and views else None
            )
            return OCListResponse(
                items=[_to_response(v) for v in views],
                next_cursor=next_cursor,
                has_more=has_more,
            )
        except InvalidCursorError as e:
            raise HTTPException(status_code=400, detail={"code": "invalid_cursor", "message": str(e)})

    # Modo compat
    views = await service.list_ordenes(
        estado=estado,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    # Cap en compat mode para evitar respuestas enormes
    return [_to_response(v) for v in views[:limit]]


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
    include_token: bool = Query(
        default=False,
        description=(
            "FIX FASE POST-E2E: si True, devuelve tambien el "
            "``last_approval_token`` (ultimo token generado al enviar el "
            "correo al supervisor). Solo admin/supervisor pueden usar "
            "este flag; otros roles lo reciben como 403."
        ),
    ),
    user=Depends(get_current_user),
    service: OrdenCompraService = Depends(get_orden_service),
) -> OCResponse:
    view = await service.get_orden(oc_id)
    last_token = None
    if include_token:
        # Solo admin o supervisor pueden pedir el token.
        if user.role not in ("admin", "supervisor"):
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "forbidden",
                    "message": "include_token=true requiere rol admin o supervisor",
                },
            )
        # Cargar el token persistido en la fila (no en la view).
        from sqlalchemy import select
        from app.db.models.ordenes_compra import OrdenCompra
        oc_row = await service._session.execute(
            select(OrdenCompra).where(OrdenCompra.id == oc_id)
        )
        oc_obj = oc_row.scalar_one_or_none()
        last_token = oc_obj.last_approval_token if oc_obj else None
    return _to_response(view, last_approval_token=last_token)


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
