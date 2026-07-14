from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.db.session import SQLiteDatabase, get_database
from app.modules.auth.dependencies import require_roles
from app.modules.auth.repository import AuthRepository
from app.modules.auth.router import get_current_user
from app.modules.auth.service import AuthService
from app.modules.warehouses.repository import WarehouseRepository
from app.modules.warehouses.schemas import WarehouseCreate, WarehouseResponse
from app.modules.warehouses.service import WarehouseService

router = APIRouter()


def get_warehouse_service(db: SQLiteDatabase = Depends(get_database)) -> WarehouseService:
    return WarehouseService(WarehouseRepository(db))


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


@router.get("", response_model=list[WarehouseResponse])
def list_warehouses(
    _: object = Depends(get_current_user),
    service: WarehouseService = Depends(get_warehouse_service),
) -> list[WarehouseResponse]:
    return service.list_warehouses()


@router.post("", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    user=Depends(require_roles("admin")),
    service: WarehouseService = Depends(get_warehouse_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> WarehouseResponse:
    warehouse = service.create_warehouse(payload)
    auth_service.audit(
        user_id=user.id,
        action="warehouse.create",
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        detail=f"Bodega {warehouse.code} creada",
    )
    return warehouse


@router.get("/{warehouse_id}", response_model=WarehouseResponse)
def get_warehouse(
    warehouse_id: UUID,
    _: object = Depends(get_current_user),
    service: WarehouseService = Depends(get_warehouse_service),
) -> WarehouseResponse:
    return service.get_warehouse(warehouse_id)
