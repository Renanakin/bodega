from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.db.session import SQLiteDatabase, WarehouseRecord


def _to_warehouse(row) -> WarehouseRecord:
    return WarehouseRecord(
        id=UUID(row["id"]),
        code=row["code"],
        name=row["name"],
        warehouse_type=row["warehouse_type"],
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class WarehouseRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def list(self) -> list[WarehouseRecord]:
        rows = self._db.query_all("SELECT * FROM warehouses ORDER BY code")
        return [_to_warehouse(row) for row in rows]

    def count(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS total FROM warehouses")
        return int(row["total"]) if row is not None else 0

    def get_by_id(self, warehouse_id: UUID) -> WarehouseRecord | None:
        row = self._db.query_one("SELECT * FROM warehouses WHERE id = ?", (str(warehouse_id),))
        return _to_warehouse(row) if row is not None else None

    def get_by_code(self, code: str) -> WarehouseRecord | None:
        row = self._db.query_one("SELECT * FROM warehouses WHERE code = ?", (code,))
        return _to_warehouse(row) if row is not None else None

    def add(self, warehouse: WarehouseRecord) -> WarehouseRecord:
        self._db.execute(
            """
            INSERT INTO warehouses (
                id, code, name, warehouse_type, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(warehouse.id),
                warehouse.code,
                warehouse.name,
                warehouse.warehouse_type,
                int(warehouse.is_active),
                warehouse.created_at.isoformat(),
                warehouse.updated_at.isoformat(),
            ),
        )
        return warehouse
