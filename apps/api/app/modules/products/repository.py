from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
        codigo_barras=row["codigo_barras"] if "codigo_barras" in row.keys() else None,
        precio_costo=(
            Decimal(str(row["precio_costo"]))
            if "precio_costo" in row.keys() and row["precio_costo"] is not None
            else Decimal("0")
        ),
        precio_venta=(
            Decimal(str(row["precio_venta"]))
            if "precio_venta" in row.keys() and row["precio_venta"] is not None
            else Decimal("0")
        ),
        id_categoria=(
            UUID(row["id_categoria"])
            if "id_categoria" in row.keys() and row["id_categoria"]
            else None
        ),
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

    def get_by_codigo_barras(self, codigo_barras: str) -> ProductRecord | None:
        row = self._db.query_one(
            "SELECT * FROM products WHERE codigo_barras = ?", (codigo_barras,)
        )
        return _to_product(row) if row is not None else None

    def add(self, product: ProductRecord) -> ProductRecord:
        self._db.execute(
            """
            INSERT INTO products (
                id, sku, name, unit, is_active, created_at, updated_at,
                codigo_barras, precio_costo, precio_venta, id_categoria
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(product.id),
                product.sku,
                product.name,
                product.unit,
                int(product.is_active),
                product.created_at.isoformat(),
                product.updated_at.isoformat(),
                product.codigo_barras,
                str(product.precio_costo),
                str(product.precio_venta),
                str(product.id_categoria) if product.id_categoria else None,
            ),
        )
        return product

    def update(
        self,
        product_id: UUID,
        *,
        name: str | None = None,
        unit: str | None = None,
        is_active: bool | None = None,
        codigo_barras: str | None = None,
        precio_costo: Decimal | None = None,
        precio_venta: Decimal | None = None,
        id_categoria: UUID | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        """PATCH parcial.

        ``id_categoria`` se persiste con el valor recibido; pasar ``None``
        explícito desvincula la categoría. Para no tocar el campo, no
        pasar el kwarg.
        """
        sets: list[str] = []
        params: list[object] = []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if unit is not None:
            sets.append("unit = ?")
            params.append(unit)
        if is_active is not None:
            sets.append("is_active = ?")
            params.append(int(is_active))
        if codigo_barras is not None:
            sets.append("codigo_barras = ?")
            params.append(codigo_barras)
        if precio_costo is not None:
            sets.append("precio_costo = ?")
            params.append(str(precio_costo))
        if precio_venta is not None:
            sets.append("precio_venta = ?")
            params.append(str(precio_venta))
        if id_categoria is not None:
            sets.append("id_categoria = ?")
            params.append(str(id_categoria))
        if updated_at is not None:
            sets.append("updated_at = ?")
            params.append(updated_at.isoformat())
        if not sets:
            return
        params.append(str(product_id))
        self._db.execute(
            f"UPDATE products SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )
