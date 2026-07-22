"""
Repository de products (async, SQLAlchemy 2.0).

Acceso a datos sobre la tabla ``products`` usando ``AsyncSession`` y
el modelo ORM ``Product``. Versión async del repository legacy
(que usaba ``SQLiteDatabase`` + SQL crudo).

Convenciones:
- Métodos ``async def``.
- Retornan el modelo ORM ``Product`` directamente.
- ``update`` aplica cambios parciales al modelo (no hay PATCH-SQL con
  ``UPDATE ... WHERE id = ?``); el service hace commit después.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.db.models.products import Product
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----------------------------------------------------------------- READ

    async def list(self) -> list[Product]:
        stmt = select(Product).order_by(Product.sku)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        stmt = select(func.count(Product.id))
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_by_id(self, product_id: uuid.UUID) -> Product | None:
        return await self._session.get(Product, product_id)

    async def get_by_sku(self, sku: str) -> Product | None:
        stmt = select(Product).where(Product.sku == sku)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_codigo_barras(self, codigo_barras: str) -> Product | None:
        stmt = select(Product).where(Product.codigo_barras == codigo_barras)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # --------------------------------------------------------------- WRITE

    async def add(self, product: Product) -> Product:
        self._session.add(product)
        await self._session.flush()
        return product

    async def update(
        self,
        product: Product,
        *,
        name: str | None = None,
        unit: str | None = None,
        is_active: bool | None = None,
        codigo_barras: str | None = None,
        precio_costo: Decimal | None = None,
        precio_venta: Decimal | None = None,
        id_categoria: uuid.UUID | None = None,
    ) -> Product:
        """PATCH parcial. ``id_categoria`` se persiste con el valor recibido;
        pasar ``None`` explícito desvincula la categoría. Para no tocar el
        campo, no pasar el kwarg.
        """
        if name is not None:
            product.name = name
        if unit is not None:
            product.unit = unit
        if is_active is not None:
            product.is_active = is_active
        if codigo_barras is not None:
            product.codigo_barras = codigo_barras
        if precio_costo is not None:
            product.precio_costo = precio_costo
        if precio_venta is not None:
            product.precio_venta = precio_venta
        if id_categoria is not None:
            product.id_categoria = id_categoria
        await self._session.flush()
        return product


__all__ = ["ProductRepository"]
