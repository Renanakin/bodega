"""
Service de categorías (async).

Reglas de negocio:
- Nombre único (case-insensitive).
- ``parent_id`` debe apuntar a una categoría existente.
- No se permite referencia circular (incluye caso directo: id == parent_id).
- Soft delete: ``DELETE`` marca ``is_active=False`` (no borra fila).

Convenciones:
- Métodos ``async def``; ``await`` sobre el repository.
- ``await session.commit()`` después de mutaciones para que la
  transacción sea durable antes de retornar.
- ``await session.refresh(obj)`` después de inserts para refrescar
  campos auto-generados (created_at, updated_at).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.errors import (
    CategoryCircularReferenceError,
    CategoryNotFoundError,
    DuplicateCategoryNameError,
)
from app.db.models.categorias import Category
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schemas import CategoryCreate, CategoryNode, CategoryUpdate
from sqlalchemy.ext.asyncio import AsyncSession


def _now_utc() -> datetime:
    return datetime.now(UTC)


class CategoryService:
    def __init__(self, session: AsyncSession, repository: CategoryRepository | None = None) -> None:
        self._session = session
        self._repository = repository or CategoryRepository(session)

    # --------------------------------------------------------------- READ

    async def list_categories(
        self,
        *,
        is_active: bool | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> list[Category]:
        return await self._repository.list(is_active=is_active, parent_id=parent_id)

    async def get_category(self, category_id: uuid.UUID) -> Category:
        category = await self._repository.get_by_id(category_id)
        if category is None:
            raise CategoryNotFoundError(str(category_id))
        return category

    # --------------------------------------------------------------- WRITE

    async def create_category(self, payload: CategoryCreate) -> Category:
        nombre = payload.nombre
        if await self._repository.get_by_nombre(nombre) is not None:
            raise DuplicateCategoryNameError(nombre)
        if payload.parent_id is not None:
            parent = await self._repository.get_by_id(payload.parent_id)
            if parent is None:
                raise CategoryNotFoundError(str(payload.parent_id))

        now = _now_utc()
        category = Category(
            id=uuid.uuid4(),
            nombre=nombre,
            descripcion=payload.descripcion,
            parent_id=payload.parent_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        await self._repository.add(category)
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def update_category(
        self, category_id: uuid.UUID, payload: CategoryUpdate
    ) -> Category:
        category = await self.get_category(category_id)

        if payload.nombre is not None and payload.nombre != category.nombre:
            existing = await self._repository.get_by_nombre(payload.nombre)
            if existing is not None and existing.id != category_id:
                raise DuplicateCategoryNameError(payload.nombre)

        if payload.parent_id is not None:
            if payload.parent_id == category_id:
                raise CategoryCircularReferenceError()
            parent = await self._repository.get_by_id(payload.parent_id)
            if parent is None:
                raise CategoryNotFoundError(str(payload.parent_id))
            # Detecta ciclo transitivo: subimos por la jerarquía del parent
            # y nos aseguramos de no volver a la categoría actual.
            if await self._would_create_cycle(category_id, payload.parent_id):
                raise CategoryCircularReferenceError()

        await self._repository.update(
            category,
            nombre=payload.nombre,
            descripcion=payload.descripcion,
            parent_id=payload.parent_id,
            is_active=payload.is_active,
        )
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def delete_category(self, category_id: uuid.UUID) -> None:
        category = await self.get_category(category_id)  # 404 si no existe
        await self._repository.soft_delete(category)
        await self._session.commit()

    # -------------------------------------------------------- Fase 8: árbol

    async def get_arbol(self, *, solo_activos: bool = True) -> list[CategoryNode]:
        """Devuelve la jerarquía completa como lista de nodos raíz.

        - Carga TODAS las categorías en una sola query (``list_all``).
        - En memoria, arma el dict ``id -> CategoryNode`` y enlaza hijos.
        - Enriquece cada nodo con ``subcategorias_count`` y
          ``productos_count`` (counts separados para no hacer N+1).
        - Filtra por ``is_active`` al final si ``solo_activos=True``.

        Returns:
            Lista de nodos raíz (parent_id is None). Cada nodo trae sus
            ``children`` recursivos.
        """
        all_records = await self._repository.list_all()
        # Conteo batch de hijos directos y productos por categoría.
        sub_counts: dict[uuid.UUID, int] = {}
        prod_counts: dict[uuid.UUID, int] = {}
        for r in all_records:
            sub_counts[r.id] = await self._repository.count_subcategorias(r.id)
            prod_counts[r.id] = await self._repository.count_productos(r.id)

        nodes: dict[uuid.UUID, CategoryNode] = {}
        for r in all_records:
            if solo_activos and not r.is_active:
                # No crear el nodo, pero conservamos su id en `nodes`
                # para que los hijos (que referencian al padre) lo salten.
                continue
            nodes[r.id] = CategoryNode(
                id=r.id,
                nombre=r.nombre,
                descripcion=r.descripcion,
                parent_id=r.parent_id,
                is_active=r.is_active,
                subcategorias_count=sub_counts.get(r.id, 0),
                productos_count=prod_counts.get(r.id, 0),
                children=[],
            )

        roots: list[CategoryNode] = []
        for r in all_records:
            if r.id not in nodes:
                continue
            node = nodes[r.id]
            if r.parent_id is None or r.parent_id not in nodes:
                # Raíz: parent_id nulo o padre inactivo (filtrado).
                roots.append(node)
            else:
                nodes[r.parent_id].children.append(node)
        return roots

    # ----------------------------------------------------------- helpers

    async def _would_create_cycle(
        self, target_id: uuid.UUID, new_parent_id: uuid.UUID
    ) -> bool:
        """Sube por la jerarquía desde new_parent_id; si llega a target_id, hay ciclo."""
        current: uuid.UUID | None = new_parent_id
        seen: set[uuid.UUID] = {new_parent_id}
        while current is not None:
            cat = await self._repository.get_by_id(current)
            if cat is None or cat.parent_id is None:
                return False
            if cat.parent_id == target_id:
                return True
            if cat.parent_id in seen:
                # Ciclo pre-existente en los datos; lo dejamos pasar, no es nuestro bug.
                return False
            seen.add(cat.parent_id)
            current = cat.parent_id
        return False


__all__ = ["CategoryService"]
