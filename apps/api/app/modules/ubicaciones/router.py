"""
Router de ubicaciones físicas (Fase 2).

Endpoints:
- ``GET    /api/v1/bodegas/{id_bodega}/ubicaciones`` — listado por bodega
- ``POST   /api/v1/bodegas/{id_bodega}/ubicaciones`` — crear en la bodega
- ``GET    /api/v1/ubicaciones/{id}``                — detalle
- ``PATCH  /api/v1/ubicaciones/{id}``                — activar/desactivar
- ``DELETE /api/v1/ubicaciones/{id}``                — soft delete
"""

from __future__ import annotations

from uuid import UUID

from app.db.session import SQLiteDatabase, get_database
from app.modules.auth.dependencies import require_roles
from app.modules.auth.repository import AuthRepository
from app.modules.auth.router import get_current_user
from app.modules.auth.service import AuthService
from app.modules.ubicaciones.repository import UbicacionRepository
from app.modules.ubicaciones.schemas import (
    UbicacionCreate,
    UbicacionResponse,
    UbicacionUpdate,
)
from app.modules.ubicaciones.service import UbicacionService
from app.modules.warehouses.repository import WarehouseRepository
from fastapi import APIRouter, Depends, status

router = APIRouter()


def get_ubicacion_service(db: SQLiteDatabase = Depends(get_database)) -> UbicacionService:
    return UbicacionService(
        repository=UbicacionRepository(db),
        warehouse_repository=WarehouseRepository(db),
    )


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


# --- Rutas anidadas bajo /bodegas/{id_bodega}/ubicaciones ---


@router.get(
    "/bodegas/{id_bodega}/ubicaciones",
    response_model=list[UbicacionResponse],
)
def list_ubicaciones_by_bodega(
    id_bodega: UUID,
    _: object = Depends(get_current_user),
    service: UbicacionService = Depends(get_ubicacion_service),
) -> list[UbicacionResponse]:
    return service.list_by_bodega(id_bodega)


@router.post(
    "/bodegas/{id_bodega}/ubicaciones",
    response_model=UbicacionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ubicacion(
    id_bodega: UUID,
    payload: UbicacionCreate,
    user=Depends(require_roles("admin", "supervisor")),
    service: UbicacionService = Depends(get_ubicacion_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> UbicacionResponse:
    ubicacion = service.create_ubicacion(id_bodega, payload)
    auth_service.audit(
        user_id=user.id,
        action="ubicacion.create",
        entity_type="ubicacion",
        entity_id=str(ubicacion.id),
        detail=(
            f"Ubicación P-{ubicacion.pasillo:02d}/E-{ubicacion.estanteria:02d}/"
            f"A-{ubicacion.altura:02d} creada en bodega {id_bodega}"
        ),
    )
    return ubicacion


# --- Rutas globales bajo /ubicaciones/{id} ---


@router.get("/ubicaciones/{ubicacion_id}", response_model=UbicacionResponse)
def get_ubicacion(
    ubicacion_id: UUID,
    _: object = Depends(get_current_user),
    service: UbicacionService = Depends(get_ubicacion_service),
) -> UbicacionResponse:
    return service.get_ubicacion(ubicacion_id)


@router.patch("/ubicaciones/{ubicacion_id}", response_model=UbicacionResponse)
def update_ubicacion(
    ubicacion_id: UUID,
    payload: UbicacionUpdate,
    user=Depends(require_roles("admin", "supervisor")),
    service: UbicacionService = Depends(get_ubicacion_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> UbicacionResponse:
    ubicacion = service.update_ubicacion(ubicacion_id, payload)
    auth_service.audit(
        user_id=user.id,
        action="ubicacion.update",
        entity_type="ubicacion",
        entity_id=str(ubicacion_id),
        detail=f"Ubicación {ubicacion_id} actualizada",
    )
    return ubicacion


@router.delete(
    "/ubicaciones/{ubicacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # explicito: FastAPI >= 0.116 confunde -> None con NoneType
)
def delete_ubicacion(
    ubicacion_id: UUID,
    user=Depends(require_roles("admin", "supervisor")),
    service: UbicacionService = Depends(get_ubicacion_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    service.delete_ubicacion(ubicacion_id)
    auth_service.audit(
        user_id=user.id,
        action="ubicacion.delete",
        entity_type="ubicacion",
        entity_id=str(ubicacion_id),
        detail=f"Ubicación {ubicacion_id} desactivada",
    )
