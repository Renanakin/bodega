"""
Repository de ubicaciones físicas (Fase 2).

Operaciones CRUD sobre ``ubicaciones_estanteria`` usando el
``SQLiteDatabase`` legacy (Fase 0/1 compat).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.db.session import SQLiteDatabase


@dataclass(slots=True)
class UbicacionRecord:
    id: uuid.UUID
    id_bodega: uuid.UUID
    pasillo: int
    estanteria: int
    altura: int
    descripcion: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


def _to_ubicacion(row: Any) -> UbicacionRecord:
    return UbicacionRecord(
        id=uuid.UUID(row["id"]),
        id_bodega=uuid.UUID(row["id_bodega"]),
        pasillo=int(row["pasillo"]),
        estanteria=int(row["estanteria"]),
        altura=int(row["altura"]),
        descripcion=row["descripcion"],
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class UbicacionRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def list_by_bodega(self, id_bodega: uuid.UUID) -> list[UbicacionRecord]:
        rows = self._db.query_all(
            """
            SELECT * FROM ubicaciones_estanteria
            WHERE id_bodega = ?
            ORDER BY pasillo, estanteria, altura
            """,
            (str(id_bodega),),
        )
        return [_to_ubicacion(row) for row in rows]

    def get_by_id(self, ubicacion_id: uuid.UUID) -> UbicacionRecord | None:
        row = self._db.query_one(
            "SELECT * FROM ubicaciones_estanteria WHERE id = ?",
            (str(ubicacion_id),),
        )
        return _to_ubicacion(row) if row is not None else None

    def find_by_slot(
        self,
        id_bodega: uuid.UUID,
        pasillo: int,
        estanteria: int,
        altura: int,
    ) -> UbicacionRecord | None:
        row = self._db.query_one(
            """
            SELECT * FROM ubicaciones_estanteria
            WHERE id_bodega = ? AND pasillo = ? AND estanteria = ? AND altura = ?
            """,
            (str(id_bodega), pasillo, estanteria, altura),
        )
        return _to_ubicacion(row) if row is not None else None

    def add(self, ubicacion: UbicacionRecord) -> UbicacionRecord:
        self._db.execute(
            """
            INSERT INTO ubicaciones_estanteria (
                id, id_bodega, pasillo, estanteria, altura,
                descripcion, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ubicacion.id),
                str(ubicacion.id_bodega),
                ubicacion.pasillo,
                ubicacion.estanteria,
                ubicacion.altura,
                ubicacion.descripcion,
                int(ubicacion.is_active),
                ubicacion.created_at.isoformat(),
                ubicacion.updated_at.isoformat(),
            ),
        )
        return ubicacion

    def update(
        self,
        ubicacion_id: uuid.UUID,
        *,
        descripcion: str | None = None,
        is_active: bool | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if descripcion is not None:
            sets.append("descripcion = ?")
            params.append(descripcion)
        if is_active is not None:
            sets.append("is_active = ?")
            params.append(int(is_active))
        if updated_at is not None:
            sets.append("updated_at = ?")
            params.append(updated_at.isoformat())
        if not sets:
            return
        params.append(str(ubicacion_id))
        self._db.execute(
            f"UPDATE ubicaciones_estanteria SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )

    def soft_delete(self, ubicacion_id: uuid.UUID, updated_at: datetime) -> None:
        self._db.execute(
            """
            UPDATE ubicaciones_estanteria
            SET is_active = 0, updated_at = ?
            WHERE id = ?
            """,
            (updated_at.isoformat(), str(ubicacion_id)),
        )
