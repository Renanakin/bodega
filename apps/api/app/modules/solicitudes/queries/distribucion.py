"""Query: distribucion multibodega de un SKU."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.modules.inventory.multibodega import StockMultibodegaService
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import (
        DistribucionMultibodegaResponse,
    )


async def get_distribucion_multibodega(
    session: AsyncSession, sku: str
) -> DistribucionMultibodegaResponse | None:
    """Vista de distribucion de un SKU por bodega (spec 4.1).

    Delega en ``StockMultibodegaService`` para mantener una sola
    implementacion. Retorna None si el SKU no existe.
    """
    from app.modules.solicitudes.schemas import (
        DistribucionBodegaItem,
        DistribucionMultibodegaResponse,
    )

    svc = StockMultibodegaService(session)
    dist = await svc.distribucion_por_sku(sku)
    if dist is None:
        return None
    items = [
        DistribucionBodegaItem(
            bodega_id=b.bodega_id,
            bodega_codigo=b.bodega_code,
            bodega_nombre=b.bodega_name,
            bodega_tipo=b.bodega_type,
            total_quantity=b.total_quantity,
            min_quantity=b.min_quantity,
            max_quantity=b.max_quantity,
            estado=b.estado,
            ubicacion_principal=None,  # F5+: completar con ubicaciones
        )
        for b in dist.bodegas
    ]
    return DistribucionMultibodegaResponse(
        producto_id=dist.producto_id,
        sku=dist.sku,
        nombre=dist.name,
        total_global=dist.total_global,
        bodegas=items,
    )
