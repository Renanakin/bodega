"""
Router de products (async, FastAPI Depends(get_session)).

Endpoints:
- ``GET    /api/v1/products``         — listado (filtro opcional ?sku=)
- ``POST   /api/v1/products``         — crear
- ``GET    /api/v1/products/{id}``    — detalle
- ``PATCH  /api/v1/products/{id}``    — actualización parcial

Convenciones:
- ``session: AsyncSession = Depends(get_session)`` (no más ``get_database``).
- Funciones ``async def``.
- Audit via ``app.core.audit.record_audit`` (best-effort).
"""

from __future__ import annotations

from uuid import UUID

from app.core.audit import record_audit
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreate, ProductResponse, ProductUpdate
from app.modules.products.service import ProductService
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_product_service(
    session: AsyncSession = Depends(get_session),
) -> ProductService:
    return ProductService(session, ProductRepository(session))


@router.get("", response_model=list[ProductResponse])
async def list_products(
    sku: str | None = Query(default=None, max_length=80, description="Filtro exacto por SKU"),
    _: object = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> list[ProductResponse]:
    """Lista productos. Si se pasa ``?sku=XXX`` filtra exacto (case-insensitive
    via la normalización en el repository).
    """
    if sku is not None:
        normalized = sku.strip().upper()
        product = await service.get_by_sku(normalized)
        return [ProductResponse.model_validate(product)] if product is not None else []
    products = await service.list_products()
    return [ProductResponse.model_validate(p) for p in products]


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    user=Depends(require_roles("admin", "supervisor")),
    service: ProductService = Depends(get_product_service),
    session: AsyncSession = Depends(get_session),
) -> ProductResponse:
    product = await service.create_product(payload)
    await record_audit(
        session=session,
        user_id=user.id,
        action="product.create",
        entity_type="product",
        entity_id=str(product.id),
        detail=f"Producto {product.sku} creado",
    )
    return ProductResponse.model_validate(product)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    _: object = Depends(get_current_user),
    service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    product = await service.get_product(product_id)
    return ProductResponse.model_validate(product)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    user=Depends(require_roles("admin", "supervisor")),
    service: ProductService = Depends(get_product_service),
    session: AsyncSession = Depends(get_session),
) -> ProductResponse:
    product = await service.update_product(product_id, payload)
    await record_audit(
        session=session,
        user_id=user.id,
        action="product.update",
        entity_type="product",
        entity_id=str(product_id),
        detail=f"Producto {product.sku} actualizado",
    )
    return ProductResponse.model_validate(product)
