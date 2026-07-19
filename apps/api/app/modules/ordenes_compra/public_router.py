"""Router publico (sin auth) para aprobacion de OC por token (Fase 6).

Decisiones (ADR-0005):
- Los endpoints NO requieren auth: el token HMAC ES la credencial.
- Rate limiting: 5 requests/min por IP para `/public/ordenes-compra/*`.
- Solo expone 3 endpoints: GET (ver OC), POST aprobar, POST rechazar.
- Cualquiera con el token puede actuar; el supervisor puede reenviar el
  email (riesgo aceptable segun NEG-002 del ADR-0005).

Reglas:
- R3: el router solo orquesta; toda logica vive en `OrdenCompraService`.
- R5: el path publico usa prefijo `/public` para distinguir visualmente
  en OpenAPI y logs que NO requiere auth.
"""
from __future__ import annotations

from decimal import Decimal

from app.core.rate_limit import rate_limit_dependency
from app.db.session import get_session
from app.modules.ordenes_compra.service import OrdenCompraService
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

# 5 req/min por IP para endpoints publicos de OC (ADR-0005 IMP-004)
public_rate_limit = rate_limit_dependency(
    scope="public_oc",
    max_requests=5,
    window_seconds=60,
)


router = APIRouter(prefix="/public/ordenes-compra", tags=["ordenes_compra_public"])


# --- Schemas ---


class DetalleOCPublico(BaseModel):
    id_producto: str
    product_sku: str | None = None
    product_name: str | None = None
    cantidad_pedida: Decimal
    costo_unitario_pactado: Decimal


class OrdenCompraPublicaView(BaseModel):
    """Vista que se envia al supervisor (sin auth)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    codigo: str
    proveedor_nombre: str
    proveedor_contacto: str | None = None
    total_estimado: Decimal
    estado: str
    notas: str | None = None
    created_at: str
    email_enviado_at: str | None = None
    supervisor_nombre: str | None = None
    detalles: list[DetalleOCPublico] = Field(default_factory=list)


class RechazoPayload(BaseModel):
    motivo: str = Field(min_length=1, max_length=500)


def get_orden_service(session: AsyncSession = Depends(get_session)) -> OrdenCompraService:
    return OrdenCompraService(session)


def _to_public_view(view) -> OrdenCompraPublicaView:  # type: ignore[no-untyped-def]
    """Adapta `OrdenCompraView` (interno) a la vista publica."""
    return OrdenCompraPublicaView(
        id=str(view.id),
        codigo=view.codigo,
        proveedor_nombre=view.proveedor_nombre,
        proveedor_contacto=view.proveedor_contacto,
        total_estimado=view.total_estimado,
        estado=view.estado,
        notas=view.notas,
        created_at=view.created_at.isoformat(),
        email_enviado_at=view.email_enviado_at.isoformat() if view.email_enviado_at else None,
        supervisor_nombre=view.supervisor_nombre,
        detalles=[
            DetalleOCPublico(
                id_producto=str(d["id_producto"]),
                product_sku=d.get("product_sku"),
                product_name=d.get("product_name"),
                cantidad_pedida=d["cantidad_pedida"],
                costo_unitario_pactado=d["costo_unitario_pactado"],
            )
            for d in view.detalles
        ],
    )


# --- Endpoints publicos (sin auth, rate limited) ---


@router.get(
    "/aprobar/{token}",
    response_model=OrdenCompraPublicaView,
    dependencies=[Depends(public_rate_limit)],
)
async def ver_oc_por_token(
    token: str,
    service: OrdenCompraService = Depends(get_orden_service),
) -> OrdenCompraPublicaView:
    """Ver la OC asociada al token (sin auth, sin mutar estado).

    Raises:
        401 invalid_approval_token si la firma es invalida.
        410 approval_token_expired si el token expiro.
        404 orden_compra_not_found si el UUID no existe.
    """
    view = await service.get_orden_por_token(token)
    return _to_public_view(view)


@router.post(
    "/aprobar/{token}",
    response_model=OrdenCompraPublicaView,
    dependencies=[Depends(public_rate_limit)],
)
async def aprobar_oc_por_token(
    token: str,
    service: OrdenCompraService = Depends(get_orden_service),
) -> OrdenCompraPublicaView:
    """Aprobar OC por token (sin auth). One-shot."""
    view = await service.aprobar_con_token(token, "approve", motivo=None)
    return _to_public_view(view)


@router.post(
    "/rechazar/{token}",
    response_model=OrdenCompraPublicaView,
    dependencies=[Depends(public_rate_limit)],
)
async def rechazar_oc_por_token(
    token: str,
    payload: RechazoPayload = Body(...),
    service: OrdenCompraService = Depends(get_orden_service),
) -> OrdenCompraPublicaView:
    """Rechazar OC por token (sin auth). One-shot."""
    view = await service.aprobar_con_token(token, "reject", motivo=payload.motivo)
    return _to_public_view(view)
