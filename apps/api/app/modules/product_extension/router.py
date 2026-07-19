"""
Router del sub-recurso ``detalles_neumaticos`` (Fase 2).

Endpoints (prefijo ``/products``):
- ``GET    /api/v1/products/{product_id}/neumatico``  — 404 si no aplica
- ``PUT    /api/v1/products/{product_id}/neumatico``  — upsert
- ``DELETE /api/v1/products/{product_id}/neumatico``  — 404 si no existe
"""
from __future__ import annotations

from uuid import UUID

from app.db.session import SQLiteDatabase, get_database
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

router = APIRouter()


def get_detalle_service(
    db: SQLiteDatabase = Depends(get_database),
) -> DetalleNeumaticoService:
    return DetalleNeumaticoService(
        repository=DetalleNeumaticoRepository(db),
        product_repository=ProductRepository(db),
    )


@router.get("/{product_id}/neumatico", response_model=DetalleNeumaticoResponse)
def get_detalle_neumatico(
    product_id: UUID,
    _: object = Depends(get_current_user),
    service: DetalleNeumaticoService = Depends(get_detalle_service),
) -> DetalleNeumaticoResponse:
    return service.get(product_id)


@router.put(
    "/{product_id}/neumatico",
    response_model=DetalleNeumaticoResponse,
    status_code=status.HTTP_200_OK,
)
def upsert_detalle_neumatico(
    product_id: UUID,
    payload: DetalleNeumaticoUpsert,
    _=Depends(require_roles("admin", "supervisor")),
    service: DetalleNeumaticoService = Depends(get_detalle_service),
) -> DetalleNeumaticoResponse:
    return service.upsert(product_id, payload)


@router.delete(
    "/{product_id}/neumatico", status_code=status.HTTP_204_NO_CONTENT
)
def delete_detalle_neumatico(
    product_id: UUID,
    _=Depends(require_roles("admin", "supervisor")),
    service: DetalleNeumaticoService = Depends(get_detalle_service),
) -> None:
    service.delete(product_id)
