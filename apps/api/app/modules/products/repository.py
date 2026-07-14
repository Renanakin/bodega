from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.db.session import ProductRecord, SQLiteDatabase


def _to_product(row) -> ProductRecord:
    return ProductRecord(
        id=UUID(row["id"]),
        sku=row["sku"],
        name=row["name"],
        unit=row["unit"],
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class ProductRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def list(self) -> list[ProductRecord]:
        rows = self._db.query_all("SELECT * FROM products ORDER BY sku")
        return [_to_product(row) for row in rows]

    def count(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS total FROM products")
        return int(row["total"]) if row is not None else 0

    def get_by_id(self, product_id: UUID) -> ProductRecord | None:
        row = self._db.query_one("SELECT * FROM products WHERE id = ?", (str(product_id),))
        return _to_product(row) if row is not None else None

    def get_by_sku(self, sku: str) -> ProductRecord | None:
        row = self._db.query_one("SELECT * FROM products WHERE sku = ?", (sku,))
        return _to_product(row) if row is not None else None

    def add(self, product: ProductRecord) -> ProductRecord:
        self._db.execute(
            """
            INSERT INTO products (
                id, sku, name, unit, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(product.id),
                product.sku,
                product.name,
                product.unit,
                int(product.is_active),
                product.created_at.isoformat(),
                product.updated_at.isoformat(),
            ),
        )
        return product
