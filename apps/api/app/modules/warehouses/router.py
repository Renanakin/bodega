"""
Router de warehouses (async, FastAPI Depends(get_session)).

Endpoints:
- ``GET    /api/v1/warehouses``           — listado
- ``POST   /api/v1/warehouses``           — crear
- ``GET    /api/v1/warehouses/{id}``      — detalle

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
from app.modules.warehouses.repository import WarehouseRepository
from app.modules.warehouses.schemas import WarehouseCreate, WarehouseResponse
from app.modules.warehouses.service import WarehouseService
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_warehouse_service(
    session: AsyncSession = Depends(get_session),
) -> WarehouseService:
    return WarehouseService(session, WarehouseRepository(session))


@router.get("", response_model=list[WarehouseResponse])
async def list_warehouses(
    _: object = Depends(get_current_user),
    service: WarehouseService = Depends(get_warehouse_service),
) -> list[WarehouseResponse]:
    warehouses = await service.list_warehouses()
    return [WarehouseResponse.model_validate(w) for w in warehouses]


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    payload: WarehouseCreate,
    user=Depends(require_roles("admin")),
    service: WarehouseService = Depends(get_warehouse_service),
) -> WarehouseResponse:
    warehouse = await service.create_warehouse(payload)
    await record_audit(
        user_id=user.id,
        action="warehouse.create",
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        detail=f"Bodega {warehouse.code} creada",
    )
    return WarehouseResponse.model_validate(warehouse)


@router.get("/{warehouse_id}", response_model=WarehouseResponse)
async def get_warehouse(
    warehouse_id: UUID,
    _: object = Depends(get_current_user),
    service: WarehouseService = Depends(get_warehouse_service),
) -> WarehouseResponse:
    warehouse = await service.get_warehouse(warehouse_id)
    return WarehouseResponse.model_validate(warehouse)
