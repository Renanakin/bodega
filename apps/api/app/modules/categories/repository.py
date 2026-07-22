"""
Repository de categorías (async, SQLAlchemy 2.0).

Acceso a datos sobre la tabla ``categories`` usando ``AsyncSession`` y
el modelo ORM ``Category``. Es la versión async del repository legacy
(que usaba ``SQLiteDatabase`` + SQL crudo).

Convenciones:
- Todos los métodos son ``async def`` (await required).
- Retornan el modelo ORM ``Category`` directamente (no un ``*Record``).
- El caller (``CategoryService``) hace ``await session.commit()`` cuando
  modifica datos.
- La cláusula ``lower()`` para case-insensitive se mantiene via
  ``func.lower()`` (compatible con Postgres + SQLite).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from app.db.models.categorias import Category
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----------------------------------------------------------------- READ

    async def list(
        self,
        *,
        is_active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> list[Category]:
        stmt = select(Category)
        if is_active is not None:
            stmt = stmt.where(Category.is_active == is_active)
        if parent_id is not None:
            stmt = stmt.where(Category.parent_id == parent_id)
        stmt = stmt.order_by(Category.nombre)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, category_id: uuid.UUID) -> Category | None:
        return await self._session.get(Category, category_id)

    async def get_by_nombre(self, nombre: str) -> Category | None:
        """Búsqueda case-insensitive (mismo nombre en otro case = duplicado)."""
        stmt = select(Category).where(
            func.lower(Category.nombre) == func.lower(nombre.strip())
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Category]:
        """Lista TODAS las categorías (activas e inactivas).

        Usado por ``CategoryService.get_arbol`` que filtra por activo en
        memoria. Es importante traer las inactivas para que ``parent_id``
        siga apuntando a un nodo visible en la jerarquía.
        """
        stmt = select(Category).order_by(Category.nombre)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # --------------------------------------------------------------- COUNTS

    async def count_subcategorias(self, parent_id: uuid.UUID) -> int:
        """Cuenta hijos directos (no recursivos) de un parent_id."""
        from sqlalchemy import func as sa_func

        stmt = select(sa_func.count(Category.id)).where(
            Category.parent_id == parent_id
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_productos(self, category_id: uuid.UUID) -> int:
        """Cuenta productos asignados a esta categoría.

        La columna real en ``products`` es ``id_categoria``. Si la tabla
        no tiene la columna (BD pre-Fase 2), retorna 0 sin explotar.
        """
        try:
            from sqlalchemy import func as sa_func
            from app.db.models.products import Product

            stmt = select(sa_func.count(Product.id)).where(
                Product.id_categoria == category_id
            )
            result = await self._session.execute(stmt)
            return int(result.scalar_one() or 0)
        except Exception:  # noqa: BLE001
            # La tabla products no tiene id_categoria (BD pre-Fase 2).
            return 0

    # --------------------------------------------------------------- WRITE

    async def add(self, category: Category) -> Category:
        self._session.add(category)
        await self._session.flush()
        return category

    async def update(
        self,
        category: Category,
        *,
        nombre: str | None = None,
        descripcion: str | None = None,
        parent_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> Category:
        """Aplica cambios parciales al modelo ORM. NO hace commit."""
        if nombre is not None:
            category.nombre = nombre
        if descripcion is not None:
            category.descripcion = descripcion
        if parent_id is not None:
            category.parent_id = parent_id
        if is_active is not None:
            category.is_active = is_active
        await self._session.flush()
        return category

    async def soft_delete(self, category: Category) -> None:
        category.is_active = False
        await self._session.flush()


__all__ = ["CategoryRepository"]
