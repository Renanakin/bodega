"""
Repository de categorías (Fase 2).

Acceso a datos sobre la tabla ``categories`` usando el ``SQLiteDatabase``
legacy. Mantiene la convención de los módulos existentes (warehouses,
products): dataclass ``CategoryRecord`` + métodos CRUD.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.db.session import SQLiteDatabase


@dataclass(slots=True)
class CategoryRecord:
    id: uuid.UUID
    nombre: str
    descripcion: str | None
    parent_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


def _to_category(row: Any) -> CategoryRecord:
    return CategoryRecord(
        id=uuid.UUID(row["id"]),
        nombre=row["nombre"],
        descripcion=row["descripcion"],
        parent_id=uuid.UUID(row["parent_id"]) if row["parent_id"] else None,
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class CategoryRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def list(
        self,
        *,
        is_active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> list[CategoryRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if is_active is not None:
            clauses.append("is_active = ?")
            params.append(int(is_active))
        if parent_id is not None:
            clauses.append("parent_id = ?")
            params.append(str(parent_id))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.query_all(
            f"SELECT * FROM categories {where} ORDER BY nombre",  # noqa: S608
            tuple(params),
        )
        return [_to_category(row) for row in rows]

    def get_by_id(self, category_id: uuid.UUID) -> CategoryRecord | None:
        row = self._db.query_one("SELECT * FROM categories WHERE id = ?", (str(category_id),))
        return _to_category(row) if row is not None else None

    def get_by_nombre(self, nombre: str) -> CategoryRecord | None:
        """Busqueda case-insensitive (mismo nombre en otro case = duplicado)."""
        row = self._db.query_one(
            "SELECT * FROM categories WHERE lower(nombre) = lower(?)",
            (nombre.strip(),),
        )
        return _to_category(row) if row is not None else None

    def add(self, category: CategoryRecord) -> CategoryRecord:
        self._db.execute(
            """
            INSERT INTO categories (
                id, nombre, descripcion, parent_id, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(category.id),
                category.nombre,
                category.descripcion,
                str(category.parent_id) if category.parent_id else None,
                int(category.is_active),
                category.created_at.isoformat(),
                category.updated_at.isoformat(),
            ),
        )
        return category

    def update(
        self,
        category_id: uuid.UUID,
        *,
        nombre: str | None = None,
        descripcion: str | None = None,
        parent_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if nombre is not None:
            sets.append("nombre = ?")
            params.append(nombre)
        if descripcion is not None:
            sets.append("descripcion = ?")
            params.append(descripcion)
        if parent_id is not None:
            sets.append("parent_id = ?")
            params.append(str(parent_id))
        if is_active is not None:
            sets.append("is_active = ?")
            params.append(int(is_active))
        if updated_at is not None:
            sets.append("updated_at = ?")
            params.append(updated_at.isoformat())
        if not sets:
            return
        params.append(str(category_id))
        self._db.execute(
            f"UPDATE categories SET {', '.join(sets)} WHERE id = ?",  # noqa: S608
            tuple(params),
        )

    def soft_delete(self, category_id: uuid.UUID, updated_at: datetime) -> None:
        self._db.execute(
            "UPDATE categories SET is_active = 0, updated_at = ? WHERE id = ?",
            (updated_at.isoformat(), str(category_id)),
        )

    # -------------------------------------------------------- Fase 8: arbol

    def list_all(self) -> list[CategoryRecord]:
        """Lista TODAS las categorias (activas e inactivas).

        Usado por ``CategoryService.get_arbol`` que filtra por activo en
        memoria. Es importante traer las inactivas para que ``parent_id``
        siga apuntando a un nodo visible en la jerarquia (la UI muestra
        el padre inactivo en gris, no lo oculta del todo).
        """
        rows = self._db.query_all(
            "SELECT * FROM categories ORDER BY nombre",
        )
        return [_to_category(row) for row in rows]

    def count_subcategorias(self, parent_id: uuid.UUID) -> int:
        """Cuenta hijos directos (no recursivos) de un parent_id."""
        row = self._db.query_one(
            "SELECT COUNT(*) AS c FROM categories WHERE parent_id = ?",
            (str(parent_id),),
        )
        return int(row["c"]) if row is not None else 0

    def count_productos(self, category_id: uuid.UUID) -> int:
        """Cuenta productos asignados a esta categoria.

        La columna real en ``products`` es ``id_categoria`` (migracion
        0005_products_extension.sql). Si la tabla no tiene la columna
        (BD legacy pre-Fase 2), retorna 0 sin explotar.
        """
        try:
            row = self._db.query_one(
                "SELECT COUNT(*) AS c FROM products WHERE id_categoria = ?",
                (str(category_id),),
            )
            return int(row["c"]) if row is not None else 0
        except Exception:  # noqa: BLE001
            # La tabla products no tiene id_categoria (BD pre-Fase 2).
            # No es nuestro bug; retornar 0 es la salida razonable.
            return 0
