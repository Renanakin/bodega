from __future__ import annotations

import uuid  # noqa: F401  (usado en raw SQL via uuid.uuid4())
from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.db.session import InventoryMovementRecord, SQLiteDatabase, StockLevelRecord
from app.modules.inventory.schemas import MovementType


def _to_stock_level(row) -> StockLevelRecord:
    return StockLevelRecord(
        id=UUID(row["id"]),
        warehouse_id=UUID(row["warehouse_id"]),
        product_id=UUID(row["product_id"]),
        quantity=Decimal(str(row["quantity"])),
        min_quantity=Decimal(str(row["min_quantity"])),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _to_movement(row) -> InventoryMovementRecord:
    return InventoryMovementRecord(
        id=UUID(row["id"]),
        warehouse_id=UUID(row["warehouse_id"]),
        product_id=UUID(row["product_id"]),
        movement_type=row["movement_type"],
        quantity=Decimal(str(row["quantity"])),
        reference_type=row["reference_type"],
        reference_id=row["reference_id"],
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class InventoryRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def transaction(self) -> AbstractContextManager[SQLiteDatabase]:
        return self._db.transaction()

    def get_stock_level(self, warehouse_id: UUID, product_id: UUID) -> StockLevelRecord | None:
        row = self._db.query_one(
            "SELECT * FROM stock_levels WHERE warehouse_id = ? AND product_id = ?",
            (str(warehouse_id), str(product_id)),
        )
        return _to_stock_level(row) if row is not None else None

    def upsert_stock_level(self, stock_level: StockLevelRecord) -> StockLevelRecord:
        self._db.execute(
            """
            INSERT INTO stock_levels (
                id, warehouse_id, product_id, quantity, min_quantity, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(warehouse_id, product_id) DO UPDATE SET
                id = excluded.id,
                quantity = excluded.quantity,
                min_quantity = excluded.min_quantity,
                updated_at = excluded.updated_at
            """,
            (
                str(stock_level.id),
                str(stock_level.warehouse_id),
                str(stock_level.product_id),
                str(stock_level.quantity),
                str(stock_level.min_quantity),
                stock_level.updated_at.isoformat(),
            ),
        )
        return stock_level

    def list_stock_levels(
        self,
        warehouse_id: UUID | None = None,
        product_id: UUID | None = None,
    ) -> list[StockLevelRecord]:
        clauses = []
        params: list[str] = []
        if warehouse_id is not None:
            clauses.append("warehouse_id = ?")
            params.append(str(warehouse_id))
        if product_id is not None:
            clauses.append("product_id = ?")
            params.append(str(product_id))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query_all(f"SELECT * FROM stock_levels {where}", tuple(params))  # noqa: S608
        return [_to_stock_level(row) for row in rows]

    def add_movement(self, movement: InventoryMovementRecord) -> InventoryMovementRecord:
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
        return movement

    def list_movements(
        self,
        warehouse_id: UUID | None = None,
        product_id: UUID | None = None,
        movement_type: MovementType | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[InventoryMovementRecord]:
        clauses = []
        params: list[str] = []
        if warehouse_id is not None:
            clauses.append("warehouse_id = ?")
            params.append(str(warehouse_id))
        if product_id is not None:
            clauses.append("product_id = ?")
            params.append(str(product_id))
        if movement_type is not None:
            clauses.append("movement_type = ?")
            params.append(movement_type.value)
        if created_from is not None:
            clauses.append("created_at >= ?")
            params.append(created_from.isoformat())
        if created_to is not None:
            clauses.append("created_at <= ?")
            params.append(created_to.isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query_all(
            f"SELECT * FROM inventory_movements {where} ORDER BY created_at DESC",  # noqa: S608
            tuple(params),
        )
        return [_to_movement(row) for row in rows]

    def count_stock_records(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS total FROM stock_levels")
        return int(row["total"]) if row is not None else 0

    def count_movements(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS total FROM inventory_movements")
        return int(row["total"]) if row is not None else 0

    def count_low_stock_alerts(self) -> int:
        row = self._db.query_one(
            """
            SELECT COUNT(*) AS total
            FROM stock_levels
            WHERE min_quantity > 0 AND quantity <= min_quantity
            """
        )
        return int(row["total"]) if row is not None else 0

    # -------------------------------------------------------- Fase 8: params

    def upsert_stock_parameters(
        self,
        warehouse_id: UUID,
        product_id: UUID,
        min_quantity: Decimal,
        max_quantity: Decimal | None,
    ) -> None:
        """Crea o actualiza la tupla ``(min, max)`` de un stock_level.

        - Si la fila existe, actualiza ``min_quantity``, ``max_quantity`` y
          ``updated_at``.
        - Si NO existe, crea la fila con ``quantity=0``.

        No verifica existencia de warehouse/product: eso es responsabilidad
        del service (que ya tiene el contexto de error de dominio).
        """
        from app.db.session import utcnow  # noqa: PLC0415

        now = utcnow().isoformat()
        self._db.execute(
            """
            INSERT INTO stock_levels (
                id, warehouse_id, product_id, quantity, min_quantity, max_quantity, updated_at
            ) VALUES (?, ?, ?, 0, ?, ?, ?)
            ON CONFLICT(warehouse_id, product_id) DO UPDATE SET
                min_quantity = excluded.min_quantity,
                max_quantity = excluded.max_quantity,
                updated_at = excluded.updated_at
            """,
            (
                str(uuid.uuid4()),
                str(warehouse_id),
                str(product_id),
                str(min_quantity),
                str(max_quantity) if max_quantity is not None else None,
                now,
            ),
        )
