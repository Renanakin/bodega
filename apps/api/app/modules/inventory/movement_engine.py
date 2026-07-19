"""
MovementEngine — el ÚNICO punto de escritura de stock (Regla de Oro R4, ADR-0001).

Este módulo expone dos implementaciones del mismo contrato:

- ``MovementEngine`` (sync) opera sobre el ``SQLiteDatabase`` legacy
  (routers actuales de Fase 0/1). Usa ``BEGIN IMMEDIATE`` como analogo
  de ``SELECT ... FOR UPDATE`` en SQLite. Es la implementación que
  consume ``InventoryService.register_movement`` para mantener la
  API publica del router.

- ``MovementEngineAsync`` opera sobre ``AsyncSession`` y usa
  ``with_for_update()`` (Postgres). Re-exportado desde
  ``app.shared.movement_engine`` para callers que ya migraron al
  stack async (Fase 3+).

Reglas:
- Toda escritura de stock (cambio de quantity) pasa por este motor.
- Registra un ``InventoryMovement`` en el ledger auditable.
- Emite log estructurado ``movement.applied`` (R8) o ``movement.rejected``.
- Si la BD no soporta ``FOR UPDATE`` (SQLite) se hace fallback a
  ``BEGIN IMMEDIATE`` y se loguea un warning (una sola vez por proceso).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from app.core.errors import (
    InsufficientStockError,
    ProductNotFoundError,
    WarehouseNotFoundError,
)
from app.core.logging import get_logger
from app.db.session import (
    InventoryMovementRecord,
    SQLiteDatabase,
    StockLevelRecord,
    utcnow,
)
from app.modules.products.repository import ProductRepository
from app.modules.warehouses.repository import WarehouseRepository

# Re-exports del motor async para callers que ya usan AsyncSession.
from app.shared.movement_engine import (  # noqa: F401
    MovementEngine as AsyncMovementEngine,
    MovementRequest as AsyncMovementRequest,
    MovementResult as AsyncMovementResult,
)

if TYPE_CHECKING:
    from app.modules.inventory.schemas import MovementType


log = get_logger(__name__)


_VALID_MOVEMENT_TYPES: frozenset[str] = frozenset(
    {"in", "out", "adjustment_in", "adjustment_out"}
)


@dataclass(slots=True)
class MovementResult:
    """Resultado de un movimiento aplicado (sync facade)."""

    movement: InventoryMovementRecord
    warehouse_code: str
    product_sku: str
    product_name: str
    previous_quantity: Decimal
    new_quantity: Decimal
    delta: Decimal


class MovementEngine:
    """Motor único de movimientos de stock (sync, sobre ``SQLiteDatabase``).

    Reemplaza la lógica que vivía directamente en
    ``InventoryService.register_movement``. Ahora ese service delega
    acá, manteniendo intacta la API pública del router.

    Locking:
    - SQLite: el wrapper ``SQLiteDatabase.transaction()`` usa ``BEGIN``
      (deferred) por default. Para evitar race conditions entre
      procesos sync, esta clase fuerza ``BEGIN IMMEDIATE`` (writer
      lock) y loguea un warning la primera vez que lo hace.
    - El fallback documentado en el spec (sección 1 del prompt Fase 2).
    """

    _immediate_warned: ClassVar[bool] = False

    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db
        self._warehouses = WarehouseRepository(db)
        self._products = ProductRepository(db)

    def register(
        self,
        warehouse_id: uuid.UUID,
        product_id: uuid.UUID,
        movement_type: "MovementType",
        quantity: Decimal,
        reference_type: str | None = None,
        reference_id: str | None = None,
        notes: str | None = None,
    ) -> MovementResult:
        """Registra un movimiento de stock de forma transaccional.

        Pasos:
        1. Valida inputs (movement_type válido, quantity > 0).
        2. Verifica warehouse + product existen.
        3. ``BEGIN IMMEDIATE`` (writer lock en SQLite).
        4. Lee ``stock_levels`` actual; calcula delta.
        5. Si salida y new_quantity < 0 -> rollback + ``InsufficientStockError``.
        6. UPSERT ``stock_levels`` con la nueva cantidad.
        7. INSERT ``inventory_movements`` (ledger inmutable).
        8. Commit. Emite log ``movement.applied``.

        Returns:
            ``MovementResult`` con previous/new quantity y delta.

        Raises:
            ``ValueError`` si inputs invalidos.
            ``WarehouseNotFoundError`` si la bodega no existe.
            ``ProductNotFoundError`` si el producto no existe.
            ``InsufficientStockError`` si la salida dejaria stock negativo.
        """
        # 1. Validaciones de input
        if movement_type.value not in _VALID_MOVEMENT_TYPES:
            raise ValueError(
                f"movement_type invalido: {movement_type.value!r}. "
                f"Validos: {sorted(_VALID_MOVEMENT_TYPES)}"
            )
        if quantity <= 0:
            raise ValueError(f"quantity debe ser > 0 (recibido: {quantity})")

        # 2-7. Toda la operacion bajo el writer lock (RLock recursivo).
        # FIX Deuda #3: las lecturas de warehouse/product ANTES estaban
        # fuera del lock, lo que permitia que en SQLite in-memory multi-thread
        # dos requests vieran el mismo stock y produjeran oversell. Ahora
        # TODO (lectura + escritura) esta bajo el RLock que serializa los
        # threads. El RLock es re-entrante (varios begin_immediate_transaction
        # anidados funcionan), asi que las llamadas a query_one() que hace
        # el repositorio internamente pasan por el mismo lock.
        with self._immediate_transaction():
            # 2. Warehouse y product (DENTRO del lock)
            warehouse = self._warehouses.get_by_id(warehouse_id)
            if warehouse is None:
                raise WarehouseNotFoundError(str(warehouse_id))
            product = self._products.get_by_id(product_id)
            if product is None:
                raise ProductNotFoundError(str(product_id))

            # 3. Stock actual (tambien bajo el lock)
            current = self._get_stock_level(warehouse_id, product_id)
            previous_quantity: Decimal = (
                current.quantity if current is not None else Decimal("0")
            )
            delta = self._compute_delta(movement_type, quantity)
            new_quantity = previous_quantity + delta

            if new_quantity < 0:
                log.warning(
                    "movement.rejected",
                    warehouse_id=str(warehouse_id),
                    warehouse_code=warehouse.code,
                    product_id=str(product_id),
                    product_sku=product.sku,
                    movement_type=movement_type.value,
                    requested=str(quantity),
                    current=str(previous_quantity),
                    reason="insufficient_stock",
                )
                raise InsufficientStockError(
                    product_id=str(product_id),
                    warehouse_id=str(warehouse_id),
                )

            now: datetime = utcnow()
            movement = InventoryMovementRecord(
                id=uuid.uuid4(),
                warehouse_id=warehouse_id,
                product_id=product_id,
                movement_type=movement_type.value,
                quantity=quantity,
                reference_type=reference_type,
                reference_id=reference_id,
                notes=notes,
                created_at=now,
            )
            self._db.execute(
                """
                INSERT INTO inventory_movements (
                    id, warehouse_id, product_id, movement_type, quantity,
                    reference_type, reference_id, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(movement.id),
                    str(movement.warehouse_id),
                    str(movement.product_id),
                    movement.movement_type,
                    str(movement.quantity),
                    movement.reference_type,
                    movement.reference_id,
                    movement.notes,
                    movement.created_at.isoformat(),
                ),
            )

            stock_level = StockLevelRecord(
                id=current.id if current is not None else uuid.uuid4(),
                warehouse_id=warehouse_id,
                product_id=product_id,
                quantity=new_quantity,
                min_quantity=current.min_quantity if current is not None else Decimal("0"),
                max_quantity=current.max_quantity if current is not None else None,
                updated_at=now,
            )
            self._db.execute(
                """
                INSERT INTO stock_levels (
                    id, warehouse_id, product_id, quantity, min_quantity, max_quantity, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(warehouse_id, product_id) DO UPDATE SET
                    id = excluded.id,
                    quantity = excluded.quantity,
                    min_quantity = excluded.min_quantity,
                    max_quantity = excluded.max_quantity,
                    updated_at = excluded.updated_at
                """,
                (
                    str(stock_level.id),
                    str(stock_level.warehouse_id),
                    str(stock_level.product_id),
                    str(stock_level.quantity),
                    str(stock_level.min_quantity),
                    (
                        str(stock_level.max_quantity)
                        if stock_level.max_quantity is not None
                        else None
                    ),
                    stock_level.updated_at.isoformat(),
                ),
            )

        # 8. Log emitido fuera del lock para no inflar el tiempo bajo lock
        log.info(
            "movement.applied",
            movement_id=str(movement.id),
            warehouse_id=str(warehouse_id),
            warehouse_code=warehouse.code,
            product_id=str(product_id),
            product_sku=product.sku,
            movement_type=movement_type.value,
            quantity=str(quantity),
            delta=str(delta),
            previous_quantity=str(previous_quantity),
            new_quantity=str(new_quantity),
            reference_type=reference_type,
            reference_id=reference_id,
        )
        return MovementResult(
            movement=movement,
            warehouse_code=warehouse.code,
            product_sku=product.sku,
            product_name=product.name,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            delta=delta,
        )

    def _get_stock_level(
        self, warehouse_id: uuid.UUID, product_id: uuid.UUID
    ) -> StockLevelRecord | None:
        row = self._db.query_one(
            "SELECT * FROM stock_levels WHERE warehouse_id = ? AND product_id = ?",
            (str(warehouse_id), str(product_id)),
        )
        if row is None:
            return None
        return StockLevelRecord(
            id=uuid.UUID(row["id"]),
            warehouse_id=uuid.UUID(row["warehouse_id"]),
            product_id=uuid.UUID(row["product_id"]),
            quantity=Decimal(str(row["quantity"])),
            min_quantity=Decimal(str(row["min_quantity"])),
            max_quantity=(
                Decimal(str(row["max_quantity"]))
                if row["max_quantity"] is not None
                else None
            ),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _immediate_transaction(self):  # type: ignore[no-untyped-def]
        """Context manager que hace ``BEGIN IMMEDIATE`` para writer lock.

        SQLite sin ``SELECT FOR UPDATE``: el analogo más cercano es
        ``BEGIN IMMEDIATE`` que adquiere un ``RESERVED`` lock al
        inicio de la transacción, evitando que otros writers entren
        concurrentemente. Los readers (otro proceso SQLite) siguen
        funcionando, lo cual es consistente con la semántica del
        ``SELECT FOR UPDATE`` de Postgres a nivel de aislamiento
        ``READ COMMITTED`` (Fase 1 default).

        FIX [T-1 auditoria-fase-1-2-2026-07-14]: delega en
        ``SQLiteDatabase.begin_immediate_transaction()`` que es el API
        publico que SI adquiere el ``RLock``. Antes se accedía a
        ``self._db._connection`` directamente, lo que bypaseaba el
        lock y producía race conditions entre writers sync.
        """
        if not MovementEngine._immediate_warned:
            log.warning(
                "movement_engine.using_begin_immediate",
                detail=(
                    "SQLite no soporta SELECT FOR UPDATE; usando "
                    "BEGIN IMMEDIATE como analogo. Migrar a Postgres "
                    "para FOR UPDATE real (ver ADR-0001)."
                ),
            )
            MovementEngine._immediate_warned = True

        return self._db.begin_immediate_transaction()

    @staticmethod
    def _compute_delta(movement_type: "MovementType", quantity: Decimal) -> Decimal:
        """Delta (positivo = entrada, negativo = salida)."""
        if movement_type.value in ("in", "adjustment_in"):
            return quantity
        return -quantity
