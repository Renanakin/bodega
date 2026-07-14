from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from app.core.errors import InsufficientStockError, ProductNotFoundError, WarehouseNotFoundError
from app.db.session import InventoryMovementRecord, StockLevelRecord, utcnow
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import InventoryMovementCreate, InventorySummaryResponse, MovementType
from app.modules.products.repository import ProductRepository
from app.modules.warehouses.repository import WarehouseRepository


@dataclass(slots=True)
class InventoryMovementView:
    id: UUID
    warehouse_id: UUID
    warehouse_code: str
    product_id: UUID
    product_sku: str
    movement_type: MovementType
    quantity: Decimal
    reference_type: str | None
    reference_id: str | None
    notes: str | None
    created_at: datetime


@dataclass(slots=True)
class StockLevelView:
    warehouse_id: UUID
    warehouse_code: str
    warehouse_name: str
    product_id: UUID
    product_sku: str
    product_name: str
    quantity: Decimal
    min_quantity: Decimal
    updated_at: datetime


class InventoryService:
    def __init__(
        self,
        inventory_repository: InventoryRepository,
        warehouse_repository: WarehouseRepository,
        product_repository: ProductRepository,
    ) -> None:
        self._inventory_repository = inventory_repository
        self._warehouse_repository = warehouse_repository
        self._product_repository = product_repository

    def list_stock(
        self,
        warehouse_id: UUID | None = None,
        product_id: UUID | None = None,
        sku: str | None = None,
    ) -> list[StockLevelView]:
        resolved_product_id, filter_matches = self._resolve_product_filter(
            product_id=product_id,
            sku=sku,
        )
        if not filter_matches:
            return []
        stock_levels = self._inventory_repository.list_stock_levels(
            warehouse_id=warehouse_id,
            product_id=resolved_product_id,
        )
        views: list[StockLevelView] = []
        for item in stock_levels:
            warehouse = self._warehouse_repository.get_by_id(item.warehouse_id)
            product = self._product_repository.get_by_id(item.product_id)
            if warehouse is None or product is None:
                continue
            views.append(
                StockLevelView(
                    warehouse_id=item.warehouse_id,
                    warehouse_code=warehouse.code,
                    warehouse_name=warehouse.name,
                    product_id=item.product_id,
                    product_sku=product.sku,
                    product_name=product.name,
                    quantity=item.quantity,
                    min_quantity=item.min_quantity,
                    updated_at=item.updated_at,
                )
            )
        return sorted(views, key=lambda item: (item.warehouse_code, item.product_sku))

    def list_movements(
        self,
        warehouse_id: UUID | None = None,
        product_id: UUID | None = None,
        sku: str | None = None,
        movement_type: MovementType | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[InventoryMovementView]:
        resolved_product_id, filter_matches = self._resolve_product_filter(
            product_id=product_id,
            sku=sku,
        )
        if not filter_matches:
            return []
        movements = self._inventory_repository.list_movements(
            warehouse_id=warehouse_id,
            product_id=resolved_product_id,
            movement_type=movement_type,
            created_from=created_from,
            created_to=created_to,
        )
        views: list[InventoryMovementView] = []
        for item in movements:
            warehouse = self._warehouse_repository.get_by_id(item.warehouse_id)
            product = self._product_repository.get_by_id(item.product_id)
            if warehouse is None or product is None:
                continue
            views.append(
                InventoryMovementView(
                    id=item.id,
                    warehouse_id=item.warehouse_id,
                    warehouse_code=warehouse.code,
                    product_id=item.product_id,
                    product_sku=product.sku,
                    movement_type=MovementType(item.movement_type),
                    quantity=item.quantity,
                    reference_type=item.reference_type,
                    reference_id=item.reference_id,
                    notes=item.notes,
                    created_at=item.created_at,
                )
            )
        return views

    def register_movement(self, payload: InventoryMovementCreate) -> InventoryMovementView:
        with self._inventory_repository.transaction():
            warehouse = self._warehouse_repository.get_by_id(payload.warehouse_id)
            if warehouse is None:
                raise WarehouseNotFoundError(str(payload.warehouse_id))

            product = self._product_repository.get_by_id(payload.product_id)
            if product is None:
                raise ProductNotFoundError(str(payload.product_id))

            current_stock = self._inventory_repository.get_stock_level(
                payload.warehouse_id,
                payload.product_id,
            )
            current_quantity = current_stock.quantity if current_stock is not None else Decimal("0")
            delta = self._movement_delta(payload.movement_type, payload.quantity)
            new_quantity = current_quantity + delta

            if new_quantity < 0:
                raise InsufficientStockError(
                    product_id=str(payload.product_id),
                    warehouse_id=str(payload.warehouse_id),
                )

            now = utcnow()
            movement = InventoryMovementRecord(
                id=uuid4(),
                warehouse_id=payload.warehouse_id,
                product_id=payload.product_id,
                movement_type=payload.movement_type.value,
                quantity=payload.quantity,
                reference_type=payload.reference_type,
                reference_id=payload.reference_id,
                notes=payload.notes,
                created_at=now,
            )
            self._inventory_repository.add_movement(movement)

            stock_level = StockLevelRecord(
                id=current_stock.id if current_stock is not None else uuid4(),
                warehouse_id=payload.warehouse_id,
                product_id=payload.product_id,
                quantity=new_quantity,
                min_quantity=current_stock.min_quantity if current_stock is not None else Decimal("0"),
                updated_at=now,
            )
            self._inventory_repository.upsert_stock_level(stock_level)

            return InventoryMovementView(
                id=movement.id,
                warehouse_id=movement.warehouse_id,
                warehouse_code=warehouse.code,
                product_id=movement.product_id,
                product_sku=product.sku,
                movement_type=payload.movement_type,
                quantity=movement.quantity,
                reference_type=movement.reference_type,
                reference_id=movement.reference_id,
                notes=movement.notes,
                created_at=movement.created_at,
            )

    def get_summary(self) -> InventorySummaryResponse:
        return InventorySummaryResponse(
            warehouses=self._warehouse_repository.count(),
            products=self._product_repository.count(),
            stock_records=self._inventory_repository.count_stock_records(),
            movements=self._inventory_repository.count_movements(),
            low_stock_alerts=self._inventory_repository.count_low_stock_alerts(),
        )

    def _resolve_product_filter(
        self,
        *,
        product_id: UUID | None,
        sku: str | None,
    ) -> tuple[UUID | None, bool]:
        if product_id is not None:
            return product_id, True
        if sku is None:
            return None, True
        product = self._product_repository.get_by_sku(sku.strip().upper())
        if product is None:
            return None, False
        return product.id, True

    @staticmethod
    def _movement_delta(movement_type: MovementType, quantity: Decimal) -> Decimal:
        if movement_type in (MovementType.IN, MovementType.ADJUSTMENT_IN):
            return quantity
        return -quantity
