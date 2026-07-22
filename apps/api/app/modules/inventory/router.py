"""
Router de inventory (async, FastAPI Depends(get_session)).

Endpoints:
- ``GET    /api/v1/inventory/stock``                  — lista stock_levels
- ``GET    /api/v1/inventory/movements``              — lista inventory_movements
- ``POST   /api/v1/inventory/movements``              — registra un movimiento (MovementEngine)
- ``GET    /api/v1/inventory/summary``                — counts agregados
- ``PUT    /api/v1/inventory/parametros/{producto_id}/{bodega_id}``  — upsert min/max

Convenciones:
- ``session: AsyncSession = Depends(get_session)``.
- Funciones ``async def``.
- Audit via ``app.core.audit.record_audit`` (best-effort).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.audit import record_audit
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.inventory.async_service import InventoryServiceAsync
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
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_inventory_service(
    session: AsyncSession = Depends(get_session),
) -> InventoryServiceAsync:
    return InventoryServiceAsync(session, InventoryRepository(session))


@router.get("/stock", response_model=list[StockLevelResponse])
async def list_stock_levels(
    warehouse_id: UUID | None = None,
    product_id: UUID | None = None,
    sku: str | None = Query(default=None, max_length=80),
    _: object = Depends(get_current_user),
    service: InventoryServiceAsync = Depends(get_inventory_service),
) -> list[StockLevelResponse]:
    views = await service.list_stock(
        warehouse_id=warehouse_id, product_id=product_id, sku=sku
    )
    return [
        StockLevelResponse(
            warehouse_id=v.warehouse_id,
            warehouse_code=v.warehouse_code,
            warehouse_name=v.warehouse_name,
            product_id=v.product_id,
            product_sku=v.product_sku,
            product_name=v.product_name,
            quantity=v.quantity,
            min_quantity=v.min_quantity,
            max_quantity=v.max_quantity,
            updated_at=v.updated_at,
        )
        for v in views
    ]


@router.get("/movements", response_model=list[InventoryMovementResponse])
async def list_movements(
    warehouse_id: UUID | None = None,
    product_id: UUID | None = None,
    sku: str | None = Query(default=None, max_length=80),
    movement_type: MovementType | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    _: object = Depends(get_current_user),
    service: InventoryServiceAsync = Depends(get_inventory_service),
) -> list[InventoryMovementResponse]:
    views = await service.list_movements(
        warehouse_id=warehouse_id,
        product_id=product_id,
        sku=sku,
        movement_type=movement_type,
        created_from=created_from,
        created_to=created_to,
    )
    return [
        InventoryMovementResponse(
            id=v.id,
            warehouse_id=v.warehouse_id,
            warehouse_code=v.warehouse_code,
            product_id=v.product_id,
            product_sku=v.product_sku,
            movement_type=v.movement_type,
            quantity=v.quantity,
            reference_type=v.reference_type,
            reference_id=v.reference_id,
            notes=v.notes,
            created_at=v.created_at,
        )
        for v in views
    ]


@router.post(
    "/movements",
    response_model=InventoryMovementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_movement(
    payload: InventoryMovementCreate,
    user=Depends(require_roles("admin", "supervisor", "origin_operator", "destination_operator")),
    service: InventoryServiceAsync = Depends(get_inventory_service),
) -> InventoryMovementResponse:
    """Registra un movimiento via MovementEngine.

    Devuelve la vista del movimiento creado (con su warehouse_code y
    product_sku) para que el cliente no necesite un GET adicional.
    """
    result = await service.register_movement(
        warehouse_id=payload.warehouse_id,
        product_id=payload.product_id,
        movement_type=payload.movement_type,
        quantity=payload.quantity,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        notes=payload.notes,
        user_id=user.id,
    )
    # Construir la vista a partir del result + el último movement registrado.
    # MovementEngine no retorna la vista completa; consultamos la lista
    # actualizada (1 sola fila con el id que devolvió el engine).
    movements = await service.list_movements(product_id=payload.product_id)
    matching = next((m for m in movements if m.id == result.movement_id), None)
    if matching is None:
        # Fallback: si no lo encontramos, construimos con los datos disponibles.
        from app.db.models.products import Product
        from app.db.models.warehouses import Warehouse
        from app.modules.products.repository import ProductRepository
        from app.modules.warehouses.repository import WarehouseRepository

        wh = await WarehouseRepository(service._session).get_by_id(result.warehouse_id)
        pr = await ProductRepository(service._session).get_by_id(result.product_id)
        wh_code = wh.code if wh else ""
        pr_sku = pr.sku if pr else ""
    else:
        wh_code = matching.warehouse_code
        pr_sku = matching.product_sku
    await record_audit(
        user_id=user.id,
        action="inventory.movement.create",
        entity_type="inventory_movement",
        entity_id=str(result.movement_id),
        detail=f"Movimiento {payload.movement_type.value} de {pr_sku}",
    )
    return InventoryMovementResponse(
        id=result.movement_id,
        warehouse_id=result.warehouse_id,
        warehouse_code=wh_code,
        product_id=result.product_id,
        product_sku=pr_sku,
        movement_type=payload.movement_type,
        quantity=result.delta,  # delta es el cambio aplicado (puede ser negativo)
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        notes=payload.notes,
        created_at=datetime.now(UTC),
    )


@router.get("/summary", response_model=InventorySummaryResponse)
async def inventory_summary(
    _: object = Depends(get_current_user),
    service: InventoryServiceAsync = Depends(get_inventory_service),
) -> InventorySummaryResponse:
    view = await service.get_summary()
    return InventorySummaryResponse(
        warehouses=view.warehouses,
        products=view.products,
        stock_records=view.stock_records,
        movements=view.movements,
        low_stock_alerts=view.low_stock_alerts,
    )


# --- Fase 8: parametrización por bodega x producto ---


@router.put(
    "/parametros/{producto_id}/{bodega_id}",
    response_model=StockParametersResponse,
)
async def upsert_stock_parameters(
    producto_id: UUID,
    bodega_id: UUID,
    payload: StockParametersUpsert,
    user=Depends(require_roles("admin", "supervisor")),
    service: InventoryServiceAsync = Depends(get_inventory_service),
) -> StockParametersResponse:
    """Crea o actualiza los parámetros ``(min, max)`` de un (producto, bodega).

    Restricciones:
    - max >= min (422 invalid_stock_parameter).
    - warehouse/product deben existir (404).
    """
    view = await service.upsert_stock_parameters(
        warehouse_id=bodega_id,
        product_id=producto_id,
        min_quantity=payload.stock_minimo,
        max_quantity=payload.stock_maximo,
    )
    await record_audit(
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
