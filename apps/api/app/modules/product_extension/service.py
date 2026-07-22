"""
Service del sub-recurso ``detalles_neumaticos`` (async).

Garantiza que el producto asociado existe antes de crear/modificar el
detalle (FK ya valida en el INSERT, pero verificamos antes para devolver
404 limpio en vez de 500 por IntegrityError).

Convenciones:
- Métodos ``async def``.
- ``await session.commit()`` + ``refresh()`` después de mutaciones.
"""

from __future__ import annotations

import uuid

from app.core.errors import DetalleNeumaticoNotFoundError, ProductNotFoundError
from app.db.models.product_extension import DetalleNeumatico
from app.modules.product_extension.repository import DetalleNeumaticoRepository
from app.modules.product_extension.schemas import DetalleNeumaticoUpsert
from app.modules.products.repository import ProductRepository
from sqlalchemy.ext.asyncio import AsyncSession


class DetalleNeumaticoService:
    def __init__(
        self,
        session: AsyncSession,
        repository: DetalleNeumaticoRepository | None = None,
        product_repository: ProductRepository | None = None,
    ) -> None:
        self._session = session
        self._repository = repository or DetalleNeumaticoRepository(session)
        self._products = product_repository or ProductRepository(session)

    async def get(self, producto_id: uuid.UUID) -> DetalleNeumatico:
        if await self._products.get_by_id(producto_id) is None:
            raise ProductNotFoundError(str(producto_id))
        record = await self._repository.get_by_producto(producto_id)
        if record is None:
            raise DetalleNeumaticoNotFoundError(str(producto_id))
        return record

    async def upsert(
        self, producto_id: uuid.UUID, payload: DetalleNeumaticoUpsert
    ) -> DetalleNeumatico:
        if await self._products.get_by_id(producto_id) is None:
            raise ProductNotFoundError(str(producto_id))
        detalle = DetalleNeumatico(
            producto_id=producto_id,
            ancho=payload.ancho,
            perfil=payload.perfil,
            aro=payload.aro,
            indice_carga=payload.indice_carga,
            indice_velocidad=payload.indice_velocidad,
            dot=payload.dot,
        )
        await self._repository.upsert(detalle)
        await self._session.commit()
        # Refrescar para obtener el estado final (por si merge hizo UPDATE).
        refreshed = await self._repository.get_by_producto(producto_id)
        if refreshed is None:
            # No debería pasar, pero defensivo.
            raise DetalleNeumaticoNotFoundError(str(producto_id))
        return refreshed

    async def delete(self, producto_id: uuid.UUID) -> None:
        if await self._products.get_by_id(producto_id) is None:
            raise ProductNotFoundError(str(producto_id))
        deleted = await self._repository.delete(producto_id)
        await self._session.commit()
        if deleted == 0:
            raise DetalleNeumaticoNotFoundError(str(producto_id))


__all__ = ["DetalleNeumaticoService"]
