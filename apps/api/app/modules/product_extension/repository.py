"""
Repository del sub-recurso ``detalles_neumaticos`` (Fase 2).

Acceso a datos sobre la tabla ``detalles_neumaticos`` (PK = ``producto_id``,
relación 1:1 opt-in con ``products``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.db.session import SQLiteDatabase


@dataclass(slots=True)
class DetalleNeumaticoRecord:
    producto_id: uuid.UUID
    ancho: int
    perfil: int
    aro: int
    indice_carga: int | None
    indice_velocidad: str | None
    dot: str | None


def _to_record(row: Any) -> DetalleNeumaticoRecord:
    return DetalleNeumaticoRecord(
        producto_id=uuid.UUID(row["producto_id"]),
        ancho=int(row["ancho"]),
        perfil=int(row["perfil"]),
        aro=int(row["aro"]),
        indice_carga=int(row["indice_carga"]) if row["indice_carga"] is not None else None,
        indice_velocidad=row["indice_velocidad"],
        dot=row["dot"],
    )


class DetalleNeumaticoRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def get_by_producto(self, producto_id: uuid.UUID) -> DetalleNeumaticoRecord | None:
        row = self._db.query_one(
            "SELECT * FROM detalles_neumaticos WHERE producto_id = ?",
            (str(producto_id),),
        )
        return _to_record(row) if row is not None else None

    def upsert(self, record: DetalleNeumaticoRecord) -> None:
        """Idempotente: si ya existe fila para producto_id, actualiza; si no, inserta."""
        self._db.execute(
            """
            INSERT INTO detalles_neumaticos (
                producto_id, ancho, perfil, aro,
                indice_carga, indice_velocidad, dot
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(producto_id) DO UPDATE SET
                ancho = excluded.ancho,
                perfil = excluded.perfil,
                aro = excluded.aro,
                indice_carga = excluded.indice_carga,
                indice_velocidad = excluded.indice_velocidad,
                dot = excluded.dot
            """,
            (
                str(record.producto_id),
                record.ancho,
                record.perfil,
                record.aro,
                record.indice_carga,
                record.indice_velocidad,
                record.dot,
            ),
        )

    def delete(self, producto_id: uuid.UUID) -> int:
        """Devuelve la cantidad de filas borradas (0 o 1)."""
        cursor = self._db.execute(
            "DELETE FROM detalles_neumaticos WHERE producto_id = ?",
            (str(producto_id),),
        )
        return cursor.rowcount
