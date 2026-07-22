"""
Router de ubicaciones (async, FastAPI Depends(get_session)).

Endpoints:
- ``GET    /api/v1/bodegas/{id_bodega}/ubicaciones`` — listado por bodega
- ``POST   /api/v1/bodegas/{id_bodega}/ubicaciones`` — crear en la bodega
- ``GET    /api/v1/ubicaciones/{id}``                — detalle
- ``PATCH  /api/v1/ubicaciones/{id}``                — activar/desactivar
- ``DELETE /api/v1/ubicaciones/{id}``                — soft delete

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
from app.modules.ubicaciones.repository import UbicacionRepository
from app.modules.ubicaciones.schemas import (
    UbicacionCreate,
    UbicacionResponse,
    UbicacionUpdate,
)
from app.modules.ubicaciones.service import UbicacionService
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_ubicacion_service(
    session: AsyncSession = Depends(get_session),
) -> UbicacionService:
    return UbicacionService(session, UbicacionRepository(session))


# --- Rutas anidadas bajo /bodegas/{id_bodega}/ubicaciones ---


@router.get(
    "/bodegas/{id_bodega}/ubicaciones",
    response_model=list[UbicacionResponse],
)
async def list_ubicaciones_by_bodega(
    id_bodega: UUID,
    _: object = Depends(get_current_user),
    service: UbicacionService = Depends(get_ubicacion_service),
) -> list[UbicacionResponse]:
    ubicaciones = await service.list_by_bodega(id_bodega)
    return [UbicacionResponse.model_validate(u) for u in ubicaciones]


@router.post(
    "/bodegas/{id_bodega}/ubicaciones",
    response_model=UbicacionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ubicacion(
    id_bodega: UUID,
    payload: UbicacionCreate,
    user=Depends(require_roles("admin", "supervisor")),
    service: UbicacionService = Depends(get_ubicacion_service),
    session: AsyncSession = Depends(get_session),
) -> UbicacionResponse:
    ubicacion = await service.create_ubicacion(id_bodega, payload)
    await record_audit(
        session=session,
        user_id=user.id,
        action="ubicacion.create",
        entity_type="ubicacion",
        entity_id=str(ubicacion.id),
        detail=(
            f"Ubicación P-{ubicacion.pasillo:02d}/E-{ubicacion.estanteria:02d}/"
            f"A-{ubicacion.altura:02d} creada en bodega {id_bodega}"
        ),
    )
    return UbicacionResponse.model_validate(ubicacion)


# --- Rutas globales bajo /ubicaciones/{id} ---


@router.get("/ubicaciones/{ubicacion_id}", response_model=UbicacionResponse)
async def get_ubicacion(
    ubicacion_id: UUID,
    _: object = Depends(get_current_user),
    service: UbicacionService = Depends(get_ubicacion_service),
) -> UbicacionResponse:
    ubicacion = await service.get_ubicacion(ubicacion_id)
    return UbicacionResponse.model_validate(ubicacion)


@router.patch("/ubicaciones/{ubicacion_id}", response_model=UbicacionResponse)
async def update_ubicacion(
    ubicacion_id: UUID,
    payload: UbicacionUpdate,
    user=Depends(require_roles("admin", "supervisor")),
    service: UbicacionService = Depends(get_ubicacion_service),
    session: AsyncSession = Depends(get_session),
) -> UbicacionResponse:
    ubicacion = await service.update_ubicacion(ubicacion_id, payload)
    await record_audit(
        session=session,
        user_id=user.id,
        action="ubicacion.update",
        entity_type="ubicacion",
        entity_id=str(ubicacion_id),
        detail=f"Ubicación {ubicacion_id} actualizada",
    )
    return UbicacionResponse.model_validate(ubicacion)


@router.delete(
    "/ubicaciones/{ubicacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_ubicacion(
    ubicacion_id: UUID,
    user=Depends(require_roles("admin", "supervisor")),
    service: UbicacionService = Depends(get_ubicacion_service),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_ubicacion(ubicacion_id)
    await record_audit(
        session=session,
        user_id=user.id,
        action="ubicacion.delete",
        entity_type="ubicacion",
        entity_id=str(ubicacion_id),
        detail=f"Ubicación {ubicacion_id} desactivada",
    )
