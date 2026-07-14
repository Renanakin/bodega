from __future__ import annotations

from uuid import UUID, uuid4

from app.core.errors import DuplicateSkuError, ProductNotFoundError
from app.db.session import ProductRecord, utcnow
from app.modules.products.repository import ProductRepository
from app.modules.products.schemas import ProductCreate


class ProductService:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

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

        now = utcnow()
        product = ProductRecord(
            id=uuid4(),
            sku=payload.sku,
            name=payload.name,
            unit=payload.unit,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        return self._repository.add(product)
