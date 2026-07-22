"""
Router de stock por ubicación (async, FastAPI Depends(get_session)).

Endpoints (prefijo ``/inventario/real``):
- ``GET  /api/v1/inventario/real``                  — listado granular
- ``POST /api/v1/inventario/real``                  — upsert (producto, ubicación)
- ``GET  /api/v1/inventario/real/distribucion``     — grilla multibodega por SKU
- ``GET  /api/v1/inventario/real/bajo-minimo``      — alertas bajo mínimo

Convenciones:
- ``session: AsyncSession = Depends(get_session)``.
- Funciones ``async def``.
"""

from __future__ import annotations

from uuid import UUID

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.products.repository import ProductRepository
from app.modules.stock_real.repository import StockRealRepository
from app.modules.stock_real.schemas import (
    BajoMinimoItem,
    DistribucionMultibodegaResponse,
    StockRealItem,
    StockRealUpsert,
)
from app.modules.stock_real.service import StockRealService
from app.modules.ubicaciones.repository import UbicacionRepository
from app.modules.warehouses.repository import WarehouseRepository
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_stock_real_service(
    session: AsyncSession = Depends(get_session),
) -> StockRealService:
    return StockRealService(
        session=session,
        stock_real_repository=StockRealRepository(session),
        ubicacion_repository=UbicacionRepository(session),
        warehouse_repository=WarehouseRepository(session),
        product_repository=ProductRepository(session),
    )


@router.get("", response_model=list[StockRealItem])
async def list_stock_real(
    warehouse_id: UUID | None = Query(default=None),
    product_id: UUID | None = Query(default=None),
    _: object = Depends(get_current_user),
    service: StockRealService = Depends(get_stock_real_service),
) -> list[StockRealItem]:
    return await service.list_stock_real(warehouse_id=warehouse_id, product_id=product_id)


@router.post("", response_model=StockRealItem, status_code=status.HTTP_200_OK)
async def upsert_stock_real(
    payload: StockRealUpsert,
    _=Depends(require_roles("admin", "supervisor")),
    service: StockRealService = Depends(get_stock_real_service),
) -> StockRealItem:
    return await service.upsert_stock_real(
        id_producto=payload.id_producto,
        id_ubicacion=payload.id_ubicacion,
        cantidad=payload.cantidad,
    )


@router.get("/distribucion", response_model=DistribucionMultibodegaResponse)
async def distribucion_por_sku(
    sku: str = Query(min_length=1, max_length=80),
    _: object = Depends(get_current_user),
    service: StockRealService = Depends(get_stock_real_service),
) -> DistribucionMultibodegaResponse:
    return await service.distribucion_por_sku(sku)


@router.get("/bajo-minimo", response_model=list[BajoMinimoItem])
async def bajo_minimo(
    bodega_id: UUID | None = Query(default=None),
    _: object = Depends(get_current_user),
    service: StockRealService = Depends(get_stock_real_service),
) -> list[BajoMinimoItem]:
    return await service.bajo_minimo(bodega_id=bodega_id)
