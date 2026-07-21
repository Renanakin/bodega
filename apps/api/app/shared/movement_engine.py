"""
MovementEngine: el ÚNICO punto de escritura de stock (Regla de Oro R4).

Reglas:
- Toda escritura de stock (cambio de quantity) pasa por este motor.
- Usa SELECT FOR UPDATE (con `.with_for_update()`) sobre stock_levels
  para evitar race conditions en concurrencia.
- Registra un InventoryMovement en el ledger auditable.
- Emite log estructurado `movement.applied` (R8) o `movement.rejected`.

Aplica a Fase 3; en Fases 4-5 se conectan inventory y transfers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.errors import InsufficientStockError, ProductNotFoundError, WarehouseNotFoundError
from app.core.logging import get_logger
from app.db.models.inventory import InventoryMovement, MovementType, StockLevel
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    pass


log = get_logger(__name__)


@dataclass(slots=True)
class MovementRequest:
    """Petición inmutable de un movimiento de stock."""

    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    movement_type: MovementType
    quantity: Decimal
    reference_type: str | None = None
    reference_id: str | None = None
    notes: str | None = None
    user_id: uuid.UUID | None = None


@dataclass(slots=True)
class MovementResult:
    """Resultado de un movimiento aplicado."""

    movement_id: uuid.UUID
    warehouse_id: uuid.UUID
    product_id: uuid.UUID
    previous_quantity: Decimal
    new_quantity: Decimal
    delta: Decimal


class MovementEngine:
    """
    Motor único de movimientos de stock.

    Uso:
        engine = MovementEngine(session)
        result = await engine.apply(MovementRequest(...))
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply(self, request: MovementRequest) -> MovementResult:
        """
        Aplica un movimiento de stock con lock pesimista.

        1. SELECT FOR UPDATE sobre stock_levels (fila bloqueada hasta commit).
        2. Calcula delta según movement_type (in/out/adjustment_*).
        3. Valida que new_quantity >= 0; si no, rollback + InsufficientStockError.
        4. UPDATE stock_levels.
        5. INSERT inventory_movements.
        6. Commit al salir del context manager.
        7. Log estructurado.

        Raises:
            WarehouseNotFoundError: si la bodega no existe.
            ProductNotFoundError: si el producto no existe.
            InsufficientStockError: si new_quantity < 0.
        """
        delta = self._compute_delta(request.movement_type, request.quantity)
        if delta == 0:
            raise ValueError(f"Quantity must be > 0 (got {request.quantity})")

        # 1. Verificar warehouse y product existen
        wh = await self._session.get(Warehouse, request.warehouse_id)
        if wh is None:
            raise WarehouseNotFoundError(str(request.warehouse_id))
        prod = await self._session.get(Product, request.product_id)
        if prod is None:
            raise ProductNotFoundError(str(request.product_id))

        # 2. SELECT FOR UPDATE sobre stock_levels
        stmt = (
            select(StockLevel)
            .where(
                StockLevel.warehouse_id == request.warehouse_id,
                StockLevel.product_id == request.product_id,
            )
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        stock = result.scalar_one_or_none()

        previous_quantity: Decimal = stock.quantity if stock is not None else Decimal("0")
        new_quantity = previous_quantity + delta

        # 3. Validar no oversell
        if new_quantity < 0:
            log.warning(
                "movement.rejected",
                warehouse_id=str(request.warehouse_id),
                product_id=str(request.product_id),
                movement_type=request.movement_type.value,
                requested=str(request.quantity),
                current=str(previous_quantity),
                reason="insufficient_stock",
            )
            raise InsufficientStockError(
                product_id=str(request.product_id),
                warehouse_id=str(request.warehouse_id),
            )

        # 4. UPSERT stock_levels
        if stock is None:
            stock = StockLevel(
                warehouse_id=request.warehouse_id,
                product_id=request.product_id,
                quantity=new_quantity,
                min_quantity=Decimal("0"),
            )
            self._session.add(stock)
        else:
            stock.quantity = new_quantity
            stock.updated_at = _utcnow_naive()

        # 5. INSERT inventory_movements (ledger inmutable)
        movement = InventoryMovement(
            id=uuid.uuid4(),
            warehouse_id=request.warehouse_id,
            product_id=request.product_id,
            movement_type=request.movement_type,
            quantity=request.quantity,
            reference_type=request.reference_type,
            reference_id=request.reference_id,
            notes=request.notes,
        )
        self._session.add(movement)

        # 6. R8: log estructurado
        log.info(
            "movement.applied",
            movement_id=str(movement.id),
            user_id=str(request.user_id) if request.user_id else None,
            warehouse_id=str(request.warehouse_id),
            warehouse_code=wh.code,
            product_id=str(request.product_id),
            product_sku=prod.sku,
            movement_type=request.movement_type.value,
            quantity=str(request.quantity),
            delta=str(delta),
            previous_quantity=str(previous_quantity),
            new_quantity=str(new_quantity),
            reference_type=request.reference_type,
            reference_id=request.reference_id,
        )

        return MovementResult(
            movement_id=movement.id,
            warehouse_id=request.warehouse_id,
            product_id=request.product_id,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            delta=delta,
        )

    @staticmethod
    def _compute_delta(movement_type: MovementType, quantity: Decimal) -> Decimal:
        """Calcula el delta (positivo = entrada, negativo = salida)."""
        if movement_type in (MovementType.IN, MovementType.ADJUSTMENT_IN):
            return quantity
        if movement_type in (MovementType.OUT, MovementType.ADJUSTMENT_OUT):
            return -quantity
        raise ValueError(f"Unknown movement_type: {movement_type}")


def _utcnow_naive() -> object:
    """Devuelve un datetime naive para columnas sin timezone.

    En Postgres usamos DateTime(timezone=True) y SQLAlchemy gestiona
    el timezone. Para SQLite (tests) acepta naive o aware.
    """
    from datetime import UTC, datetime

    return datetime.now(UTC)
