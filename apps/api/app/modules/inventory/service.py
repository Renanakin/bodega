from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.core.errors import ProductNotFoundError, WarehouseNotFoundError
from app.modules.inventory.movement_engine import MovementEngine, MovementResult
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schemas import (
    InventoryMovementCreate,
    InventorySummaryResponse,
    MovementType,
)
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
    max_quantity: Decimal | None
    updated_at: datetime


@dataclass(slots=True)
class StockParametersView:
    """Vista de los parametros de un (producto, bodega) especifico (Fase 8)."""

    id: UUID
    warehouse_id: UUID
    warehouse_code: str
    product_id: UUID
    product_sku: str
    quantity: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
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
        # El motor de movimientos opera sobre la misma BD legacy. Cualquier
        # escritura de stock (cambios en quantity) pasa por acá (Regla R4).
        self._movement_engine = MovementEngine(inventory_repository._db)  # noqa: SLF001

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
                    max_quantity=item.max_quantity,
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
        """Registra un movimiento delegando en ``MovementEngine``.

        La API pública no cambia: misma firma, misma ``InventoryMovementView``
        de salida, mismos errores (``WarehouseNotFoundError``,
        ``ProductNotFoundError``, ``InsufficientStockError``).
        """
        try:
            result: MovementResult = self._movement_engine.register(
                warehouse_id=payload.warehouse_id,
                product_id=payload.product_id,
                movement_type=payload.movement_type,
                quantity=payload.quantity,
                reference_type=payload.reference_type,
                reference_id=payload.reference_id,
                notes=payload.notes,
            )
        except (WarehouseNotFoundError, ProductNotFoundError):
            # El service los deja propagar tal cual; el handler de dominio
            # los traduce a 404/409.
            raise

        return InventoryMovementView(
            id=result.movement.id,
            warehouse_id=result.movement.warehouse_id,
            warehouse_code=result.warehouse_code,
            product_id=result.movement.product_id,
            product_sku=result.product_sku,
            movement_type=payload.movement_type,
            quantity=result.movement.quantity,
            reference_type=result.movement.reference_type,
            reference_id=result.movement.reference_id,
            notes=result.movement.notes,
            created_at=result.movement.created_at,
        )

    def get_summary(self) -> InventorySummaryResponse:
        return InventorySummaryResponse(
            warehouses=self._warehouse_repository.count(),
            products=self._product_repository.count(),
            stock_records=self._inventory_repository.count_stock_records(),
            movements=self._inventory_repository.count_movements(),
            low_stock_alerts=self._inventory_repository.count_low_stock_alerts(),
        )

    # -------------------------------------------------------- Fase 8: params

    def upsert_stock_parameters(
        self,
        warehouse_id: UUID,
        product_id: UUID,
        min_quantity: Decimal,
        max_quantity: Decimal | None,
    ) -> StockParametersView:
        """Crea o actualiza los parametros (min, max) de un (producto, bodega).

        Validaciones:
        - warehouse existe.
        - product existe.
        - max_quantity >= min_quantity (si max viene).

        Returns:
            ``StockParametersView`` con los datos resultantes.
        """
        if self._warehouse_repository.get_by_id(warehouse_id) is None:
            raise WarehouseNotFoundError(str(warehouse_id))
        if self._product_repository.get_by_id(product_id) is None:
            raise ProductNotFoundError(str(product_id))
        if max_quantity is not None and max_quantity < min_quantity:
            from app.core.errors import InvalidStockParameterError  # noqa: PLC0415

            raise InvalidStockParameterError(
                f"max_quantity ({max_quantity}) debe ser >= min_quantity ({min_quantity})"
            )

        self._inventory_repository.upsert_stock_parameters(
            warehouse_id=warehouse_id,
            product_id=product_id,
            min_quantity=min_quantity,
            max_quantity=max_quantity,
        )
        # Re-leer para devolver la vista fresca (incluye updated_at).
        stock = self._inventory_repository.get_stock_level(warehouse_id, product_id)
        warehouse = self._warehouse_repository.get_by_id(warehouse_id)
        product = self._product_repository.get_by_id(product_id)
        if stock is None or warehouse is None or product is None:
            # No deberia pasar, pero defensivo.
            raise ProductNotFoundError(str(product_id))

        return StockParametersView(
            id=stock.id,
            warehouse_id=stock.warehouse_id,
            warehouse_code=warehouse.code,
            product_id=stock.product_id,
            product_sku=product.sku,
            quantity=stock.quantity,
            min_quantity=stock.min_quantity,
            max_quantity=max_quantity,
            updated_at=stock.updated_at,
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
