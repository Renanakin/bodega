"""Router FastAPI para proveedores (Fase 8).

Endpoints:
- ``GET    /api/v1/proveedores``               — listar (filtro ?activo=true|false)
- ``POST   /api/v1/proveedores``               — crear (admin only)
- ``GET    /api/v1/proveedores/{id}``          — obtener
- ``PATCH  /api/v1/proveedores/{id}``          — actualizar parcial (admin only)
- ``DELETE /api/v1/proveedores/{id}``          — soft delete (admin only)
"""

from __future__ import annotations

import uuid

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.proveedores.schemas import (
    ProveedorCreate,
    ProveedorResponse,
    ProveedorUpdate,
)
from app.modules.proveedores.service import ProveedorService
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_proveedor_service(
    session: AsyncSession = Depends(get_session),
) -> ProveedorService:
    return ProveedorService(session)


@router.get("", response_model=list[ProveedorResponse])
async def list_proveedores(
    activo: bool | None = Query(default=None, description="Filtrar por activo (true|false)"),
    _user=Depends(get_current_user),
    service: ProveedorService = Depends(get_proveedor_service),
) -> list[ProveedorResponse]:
    proveedores = await service.list_proveedores(solo_activos=activo)
    return [ProveedorResponse.model_validate(p) for p in proveedores]


@router.get("/{proveedor_id}", response_model=ProveedorResponse)
async def get_proveedor(
    proveedor_id: uuid.UUID,
    _user=Depends(get_current_user),
    service: ProveedorService = Depends(get_proveedor_service),
) -> ProveedorResponse:
    p = await service.get_proveedor(proveedor_id)
    return ProveedorResponse.model_validate(p)


@router.post("", response_model=ProveedorResponse, status_code=status.HTTP_201_CREATED)
async def create_proveedor(
    payload: ProveedorCreate,
    _user=Depends(require_roles("admin")),
    service: ProveedorService = Depends(get_proveedor_service),
) -> ProveedorResponse:
    p = await service.create_proveedor(payload.model_dump())
    return ProveedorResponse.model_validate(p)


@router.patch("/{proveedor_id}", response_model=ProveedorResponse)
async def update_proveedor(
    proveedor_id: uuid.UUID,
    payload: ProveedorUpdate,
    _user=Depends(require_roles("admin")),
    service: ProveedorService = Depends(get_proveedor_service),
) -> ProveedorResponse:
    data = payload.model_dump(exclude_unset=True)
    p = await service.update_proveedor(proveedor_id, data)
    return ProveedorResponse.model_validate(p)


@router.delete("/{proveedor_id}", response_model=ProveedorResponse)
async def soft_delete_proveedor(
    proveedor_id: uuid.UUID,
    _user=Depends(require_roles("admin")),
    service: ProveedorService = Depends(get_proveedor_service),
) -> ProveedorResponse:
    """Soft delete: marca ``activo=False`` (no se borra la fila)."""
    p = await service.soft_delete_proveedor(proveedor_id)
    return ProveedorResponse.model_validate(p)
