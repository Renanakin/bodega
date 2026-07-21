from datetime import datetime
from uuid import UUID

from app.db.session import SQLiteDatabase, get_database
from app.modules.auth.dependencies import require_roles
from app.modules.auth.repository import AuthRepository
from app.modules.auth.router import get_current_user
from app.modules.auth.service import AuthService
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    InventoryMovementCreate,
    InventoryMovementResponse,
    InventorySummaryResponse,
    MovementType,
    StockLevelResponse,
    StockParametersResponse,
    StockParametersUpsert,
)
from app.modules.inventory.service import InventoryService
from app.modules.products.repository import ProductRepository
from app.modules.warehouses.repository import WarehouseRepository
from fastapi import APIRouter, Depends, Query, status

router = APIRouter()


def get_inventory_service(db: SQLiteDatabase = Depends(get_database)) -> InventoryService:
    return InventoryService(
        inventory_repository=InventoryRepository(db),
        warehouse_repository=WarehouseRepository(db),
        product_repository=ProductRepository(db),
    )


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


@router.get("/stock", response_model=list[StockLevelResponse])
def list_stock_levels(
    warehouse_id: UUID | None = None,
    product_id: UUID | None = None,
    sku: str | None = Query(default=None, max_length=80),
    _: object = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> list[StockLevelResponse]:
    return service.list_stock(warehouse_id=warehouse_id, product_id=product_id, sku=sku)


@router.get("/movements", response_model=list[InventoryMovementResponse])
def list_movements(
    warehouse_id: UUID | None = None,
    product_id: UUID | None = None,
    sku: str | None = Query(default=None, max_length=80),
    movement_type: MovementType | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    _: object = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> list[InventoryMovementResponse]:
    return service.list_movements(
        warehouse_id=warehouse_id,
        product_id=product_id,
        sku=sku,
        movement_type=movement_type,
        created_from=created_from,
        created_to=created_to,
    )


@router.post(
    "/movements", response_model=InventoryMovementResponse, status_code=status.HTTP_201_CREATED
)
def register_movement(
    payload: InventoryMovementCreate,
    user=Depends(require_roles("admin", "supervisor", "origin_operator", "destination_operator")),
    service: InventoryService = Depends(get_inventory_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> InventoryMovementResponse:
    movement = service.register_movement(payload)
    auth_service.audit(
        user_id=user.id,
        action="inventory.movement.create",
        entity_type="inventory_movement",
        entity_id=str(movement.id),
        detail=f"Movimiento {movement.movement_type} de {movement.product_sku}",
    )
    return movement


@router.get("/summary", response_model=InventorySummaryResponse)
def inventory_summary(
    _: object = Depends(get_current_user),
    service: InventoryService = Depends(get_inventory_service),
) -> InventorySummaryResponse:
    return service.get_summary()


# --- Fase 8: parametrizacion por bodega x producto ---


@router.put(
    "/parametros/{producto_id}/{bodega_id}",
    response_model=StockParametersResponse,
)
def upsert_stock_parameters(
    producto_id: UUID,
    bodega_id: UUID,
    payload: StockParametersUpsert,
    user=Depends(require_roles("admin", "supervisor")),
    service: InventoryService = Depends(get_inventory_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> StockParametersResponse:
    """Crea o actualiza los parametros ``(min, max)`` de un (producto, bodega).

    Usado por ``ReplenishmentRuleForm`` (Fase 8) para que el bodeguero central
    pueda parametrizar las reglas de reabastecimiento desde la UI sin tocar
    la BD.

    Restricciones:
    - max >= min (422 invalid_stock_parameter).
    - warehouse/product deben existir (404).
    """
    view = service.upsert_stock_parameters(
        warehouse_id=bodega_id,
        product_id=producto_id,
        min_quantity=payload.stock_minimo,
        max_quantity=payload.stock_maximo,
    )
    auth_service.audit(
        user_id=user.id,
        action="inventory.parameters.upsert",
        entity_type="stock_level",
        entity_id=str(view.id),
        detail=(
            f"Parametros actualizados para {view.product_sku} en bodega "
            f"{view.warehouse_code}: min={payload.stock_minimo}, max={payload.stock_maximo}"
        ),
    )
    return StockParametersResponse(
        id=view.id,
        warehouse_id=view.warehouse_id,
        warehouse_code=view.warehouse_code,
        product_id=view.product_id,
        product_sku=view.product_sku,
        quantity=view.quantity,
        min_quantity=view.min_quantity,
        max_quantity=view.max_quantity,
        updated_at=view.updated_at,
    )
