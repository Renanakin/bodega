"""
Repository de stock por ubicación (Fase 2).

Operaciones sobre ``inventario_stock_real`` (Nivel 2 — granularidad
por ubicación) usando el ``SQLiteDatabase`` legacy.

R3/R4: este repository NO escribe ``stock_levels`` (Nivel 1). El
``MovementEngine`` es el único que mantiene ambos sincronizados.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.db.session import SQLiteDatabase


@dataclass(slots=True)
class StockRealRecord:
    id_producto: uuid.UUID
    id_ubicacion: uuid.UUID
    cantidad: Decimal
    updated_at: datetime


def _to_stock_real(row: Any) -> StockRealRecord:
    return StockRealRecord(
        id_producto=uuid.UUID(row["id_producto"]),
        id_ubicacion=uuid.UUID(row["id_ubicacion"]),
        cantidad=Decimal(str(row["cantidad"])),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class StockRealRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def list(
        self,
        *,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[StockRealRecord]:
        """Consulta granular; JOIN a ubicaciones cuando se filtra por bodega."""
        clauses: list[str] = []
        params: list[Any] = []
        join = ""
        if warehouse_id is not None:
            join = " JOIN ubicaciones_estanteria u ON u.id = sr.id_ubicacion "
            clauses.append("u.id_bodega = ?")
            params.append(str(warehouse_id))
        if product_id is not None:
            clauses.append("sr.id_producto = ?")
            params.append(str(product_id))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query_all(
            f"SELECT sr.* FROM inventario_stock_real sr{join}{where}",
            tuple(params),
        )
        return [_to_stock_real(row) for row in rows]

    def get(
        self, id_producto: uuid.UUID, id_ubicacion: uuid.UUID
    ) -> StockRealRecord | None:
        row = self._db.query_one(
            """
            SELECT * FROM inventario_stock_real
            WHERE id_producto = ? AND id_ubicacion = ?
            """,
            (str(id_producto), str(id_ubicacion)),
        )
        return _to_stock_real(row) if row is not None else None

    def upsert(
        self,
        id_producto: uuid.UUID,
        id_ubicacion: uuid.UUID,
        cantidad: Decimal,
        updated_at: datetime,
    ) -> None:
        self._db.execute(
            """
            INSERT INTO inventario_stock_real (
                id_producto, id_ubicacion, cantidad, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(id_producto, id_ubicacion) DO UPDATE SET
                cantidad = excluded.cantidad,
                updated_at = excluded.updated_at
            """,
            (
                str(id_producto),
                str(id_ubicacion),
                str(cantidad),
                updated_at.isoformat(),
            ),
        )
