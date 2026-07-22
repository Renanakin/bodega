"""
Router del sub-recurso ``detalles_neumaticos`` (async, FastAPI Depends(get_session)).

Endpoints (prefijo ``/products``):
- ``GET    /api/v1/products/{product_id}/neumatico``  — 404 si no aplica
- ``PUT    /api/v1/products/{product_id}/neumatico``  — upsert
- ``DELETE /api/v1/products/{product_id}/neumatico``  — 404 si no existe

Convenciones:
- ``session: AsyncSession = Depends(get_session)``.
- Funciones ``async def``.
"""

from __future__ import annotations

from uuid import UUID

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.product_extension.repository import DetalleNeumaticoRepository
from app.modules.product_extension.schemas import (
    DetalleNeumaticoResponse,
    DetalleNeumaticoUpsert,
)
from app.modules.product_extension.service import DetalleNeumaticoService
from app.modules.products.repository import ProductRepository
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_detalle_service(
    session: AsyncSession = Depends(get_session),
) -> DetalleNeumaticoService:
    return DetalleNeumaticoService(
        session,
        DetalleNeumaticoRepository(session),
        ProductRepository(session),
    )


@router.get("/{product_id}/neumatico", response_model=DetalleNeumaticoResponse)
async def get_detalle_neumatico(
    product_id: UUID,
    _: object = Depends(get_current_user),
    service: DetalleNeumaticoService = Depends(get_detalle_service),
) -> DetalleNeumaticoResponse:
    detalle = await service.get(product_id)
    return DetalleNeumaticoResponse.model_validate(detalle)


@router.put(
    "/{product_id}/neumatico",
    response_model=DetalleNeumaticoResponse,
    status_code=status.HTTP_200_OK,
)
async def upsert_detalle_neumatico(
    product_id: UUID,
    payload: DetalleNeumaticoUpsert,
    _=Depends(require_roles("admin", "supervisor")),
    service: DetalleNeumaticoService = Depends(get_detalle_service),
) -> DetalleNeumaticoResponse:
    detalle = await service.upsert(product_id, payload)
    return DetalleNeumaticoResponse.model_validate(detalle)


@router.delete(
    "/{product_id}/neumatico",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_detalle_neumatico(
    product_id: UUID,
    _=Depends(require_roles("admin", "supervisor")),
    service: DetalleNeumaticoService = Depends(get_detalle_service),
) -> None:
    await service.delete(product_id)
