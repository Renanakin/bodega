from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.core.errors import (
    CategoryNotFoundError,
    DuplicateSkuError,
    ProductNotFoundError,
)
from app.db.session import ProductRecord, utcnow
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreate, ProductUpdate

if TYPE_CHECKING:
    from app.modules.categories.repository import CategoryRepository


class ProductService:
    def __init__(
        self,
        repository: ProductRepository,
        category_repository: "CategoryRepository | None" = None,
    ) -> None:
        # ``category_repository`` es opcional para mantener compat con los
        # tests existentes que instancian ``ProductService(ProductRepository(db))``.
        # Cuando se inyecta (desde el router), se valida ``id_categoria``.
        self._repository = repository
        self._category_repository = category_repository

    def list_products(self) -> list[ProductRecord]:
        return self._repository.list()

    def get_product(self, product_id: UUID) -> ProductRecord:
        product = self._repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))
        return product

    def create_product(self, payload: ProductCreate) -> ProductRecord:
        if self._repository.get_by_sku(payload.sku) is not None:
            raise DuplicateSkuError(payload.sku)
        if (
            payload.codigo_barras is not None
            and self._repository.get_by_codigo_barras(payload.codigo_barras) is not None
        ):
            raise DuplicateSkuError(f"codigo_barras={payload.codigo_barras}")
        if payload.id_categoria is not None:
            self._validate_categoria(payload.id_categoria)

        now = utcnow()
        product = ProductRecord(
            id=uuid4(),
            sku=payload.sku,
            name=payload.name,
            unit=payload.unit,
            is_active=True,
            created_at=now,
            updated_at=now,
            codigo_barras=payload.codigo_barras,
            precio_costo=payload.precio_costo
            if payload.precio_costo is not None
            else Decimal("0"),
            precio_venta=payload.precio_venta
            if payload.precio_venta is not None
            else Decimal("0"),
            id_categoria=payload.id_categoria,
        )
        return self._repository.add(product)

    def update_product(
        self, product_id: UUID, payload: ProductUpdate
    ) -> ProductRecord:
        self.get_product(product_id)  # 404 si no existe

        if payload.id_categoria is not None:
            self._validate_categoria(payload.id_categoria)

        self._repository.update(
            product_id,
            name=payload.name,
            unit=payload.unit,
            is_active=payload.is_active,
            codigo_barras=payload.codigo_barras,
            precio_costo=payload.precio_costo,
            precio_venta=payload.precio_venta,
            id_categoria=payload.id_categoria,
            updated_at=utcnow(),
        )
        return self.get_product(product_id)

    def _validate_categoria(self, categoria_id: UUID) -> None:
        if self._category_repository is None:
            # Compat con tests que no inyectan el repository de categorías.
            # En el router siempre se inyecta, así que en prod nunca llega acá.
            return
        if self._category_repository.get_by_id(categoria_id) is None:
            raise CategoryNotFoundError(str(categoria_id))
