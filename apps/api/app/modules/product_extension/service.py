"""
Service del sub-recurso ``detalles_neumaticos`` (Fase 2).

Garantiza que el producto asociado existe antes de crear/modificar el
detalle (FK ya valida en el INSERT, pero verificamos antes para devolver
404 limpio en vez de 500 por IntegrityError).
"""

from __future__ import annotations

import uuid

from app.core.errors import DetalleNeumaticoNotFoundError, ProductNotFoundError
from app.modules.product_extension.repository import (
    DetalleNeumaticoRecord,
    DetalleNeumaticoRepository,
)
from app.modules.product_extension.schemas import DetalleNeumaticoUpsert
from app.modules.products.repository import ProductRepository


class DetalleNeumaticoService:
    def __init__(
        self,
        repository: DetalleNeumaticoRepository,
        product_repository: ProductRepository,
    ) -> None:
        self._repository = repository
        self._products = product_repository

    def get(self, producto_id: uuid.UUID) -> DetalleNeumaticoRecord:
        if self._products.get_by_id(producto_id) is None:
            raise ProductNotFoundError(str(producto_id))
        record = self._repository.get_by_producto(producto_id)
        if record is None:
            raise DetalleNeumaticoNotFoundError(str(producto_id))
        return record

    def upsert(
        self, producto_id: uuid.UUID, payload: DetalleNeumaticoUpsert
    ) -> DetalleNeumaticoRecord:
        if self._products.get_by_id(producto_id) is None:
            raise ProductNotFoundError(str(producto_id))
        record = DetalleNeumaticoRecord(
            producto_id=producto_id,
            ancho=payload.ancho,
            perfil=payload.perfil,
            aro=payload.aro,
            indice_carga=payload.indice_carga,
            indice_velocidad=payload.indice_velocidad,
            dot=payload.dot,
        )
        self._repository.upsert(record)
        return record

    def delete(self, producto_id: uuid.UUID) -> None:
        if self._products.get_by_id(producto_id) is None:
            raise ProductNotFoundError(str(producto_id))
        deleted = self._repository.delete(producto_id)
        if deleted == 0:
            raise DetalleNeumaticoNotFoundError(str(producto_id))
