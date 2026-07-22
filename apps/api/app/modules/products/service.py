"""
Service de products (async).

Reglas de negocio:
- ``sku`` único.
- ``codigo_barras`` único (si está presente).
- ``id_categoria`` debe apuntar a una categoría existente.

Convenciones:
- Métodos ``async def``.
- ``await session.commit()`` + ``refresh()`` después de mutaciones.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.core.errors import (
    CategoryNotFoundError,
    DuplicateSkuError,
    ProductNotFoundError,
)
from app.db.models.products import Product
from app.modules.categories.repository import CategoryRepository
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreate, ProductUpdate
from sqlalchemy.ext.asyncio import AsyncSession


def _now_utc() -> datetime:
    return datetime.now(UTC)


class ProductService:
    def __init__(
        self,
        session: AsyncSession,
        repository: ProductRepository | None = None,
        category_repository: CategoryRepository | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or ProductRepository(session)
        self._category_repository = category_repository or CategoryRepository(session)

    # --------------------------------------------------------------- READ

    async def list_products(self) -> list[Product]:
        return await self._repository.list()

    async def get_product(self, product_id: uuid.UUID) -> Product:
        product = await self._repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))
        return product

    async def get_by_sku(self, sku: str) -> Product | None:
        return await self._repository.get_by_sku(sku)

    # --------------------------------------------------------------- WRITE

    async def create_product(self, payload: ProductCreate) -> Product:
        if await self._repository.get_by_sku(payload.sku) is not None:
            raise DuplicateSkuError(payload.sku)
        if (
            payload.codigo_barras is not None
            and await self._repository.get_by_codigo_barras(payload.codigo_barras)
            is not None
        ):
            raise DuplicateSkuError(f"codigo_barras={payload.codigo_barras}")
        if payload.id_categoria is not None:
            await self._validate_categoria(payload.id_categoria)

        now = _now_utc()
        product = Product(
            id=uuid.uuid4(),
            sku=payload.sku,
            name=payload.name,
            unit=payload.unit,
            is_active=True,
            created_at=now,
            updated_at=now,
            codigo_barras=payload.codigo_barras,
            precio_costo=(
                payload.precio_costo
                if payload.precio_costo is not None
                else Decimal("0")
            ),
            precio_venta=(
                payload.precio_venta
                if payload.precio_venta is not None
                else Decimal("0")
            ),
            id_categoria=payload.id_categoria,
        )
        await self._repository.add(product)
        await self._session.commit()
        await self._session.refresh(product)
        return product

    async def update_product(
        self, product_id: uuid.UUID, payload: ProductUpdate
    ) -> Product:
        product = await self.get_product(product_id)  # 404 si no existe

        if payload.id_categoria is not None:
            await self._validate_categoria(payload.id_categoria)

        await self._repository.update(
            product,
            name=payload.name,
            unit=payload.unit,
            is_active=payload.is_active,
            codigo_barras=payload.codigo_barras,
            precio_costo=payload.precio_costo,
            precio_venta=payload.precio_venta,
            id_categoria=payload.id_categoria,
        )
        await self._session.commit()
        await self._session.refresh(product)
        return product

    # ----------------------------------------------------------- helpers

    async def _validate_categoria(self, categoria_id: uuid.UUID) -> None:
        if await self._category_repository.get_by_id(categoria_id) is None:
            raise CategoryNotFoundError(str(categoria_id))


__all__ = ["ProductService"]
