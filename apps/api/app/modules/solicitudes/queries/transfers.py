"""Query: vista derivada de solicitud como Transfer (compat legacy).

Mapea el modelo SolicitudRecarga al namespace legacy de Transfer
(usado por los endpoints antiguos que conviven con solicitudes
durante la ventana de migracion de 6 meses, ADR-0003).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.products import Product
from app.db.models.solicitudes import SolicitudEstado
from app.db.models.warehouses import Warehouse


if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import (
        TransferDerivedLinea,
        TransferDerivedResponse,
    )


# Mapeo: estado SolicitudRecarga -> estado legacy Transfer
_STATUS_MAP = {
    SolicitudEstado.PENDING.value: "requested",
    SolicitudEstado.APPROVED.value: "approved",
    SolicitudEstado.IN_TRANSIT.value: "dispatched",
    SolicitudEstado.PARTIALLY_RECEIVED.value: "partially_received",
    SolicitudEstado.RECEIVED.value: "received",
    SolicitudEstado.REJECTED.value: "cancelled",
    SolicitudEstado.CANCELLED.value: "cancelled",
}


async def get_derived_transfer(
    session: AsyncSession, repo, codigo_legacy: str
) -> "TransferDerivedResponse | None":
    """Vista derivada de una solicitud como Transfer (compat legacy)."""
    from app.modules.solicitudes.schemas import (
        TransferDerivedLinea,
        TransferDerivedResponse,
    )

    solicitud = await repo.get_by_codigo(codigo_legacy)
    if solicitud is None:
        return None
    wh_origen = await session.get(Warehouse, solicitud.id_bodega_origen)
    wh_destino = await session.get(Warehouse, solicitud.id_bodega_destino)
    detalles = list(await repo.list_detalles(solicitud.id))

    transfer_status = _STATUS_MAP.get(solicitud.estado.value, "requested")

    # Construir lineas
    lineas: list[TransferDerivedLinea] = []
    first_product_id = detalles[0].id_producto if detalles else uuid.uuid4()
    first_product_sku = ""
    first_product_name = ""
    first_quantity = Decimal("0")
    for d in detalles:
        prod = await session.get(Product, d.id_producto)
        lineas.append(
            TransferDerivedLinea(
                producto_id=d.id_producto,
                producto_sku=prod.sku if prod else "",
                producto_nombre=prod.name if prod else "",
                cantidad_solicitada=d.cantidad_solicitada,
                cantidad_despachada=d.cantidad_despachada,
                cantidad_recibida=d.cantidad_recibida,
            )
        )
        if prod and not first_product_sku:
            first_product_sku = prod.sku
            first_product_name = prod.name
        if not first_quantity:
            first_quantity = d.cantidad_solicitada

    return TransferDerivedResponse(
        id=solicitud.id,
        code=solicitud.codigo,
        from_warehouse_id=solicitud.id_bodega_origen,
        from_warehouse_code=wh_origen.code if wh_origen else "",
        to_warehouse_id=solicitud.id_bodega_destino,
        to_warehouse_code=wh_destino.code if wh_destino else "",
        product_id=first_product_id,
        product_sku=first_product_sku,
        product_name=first_product_name,
        quantity=first_quantity,
        received_quantity=detalles[0].cantidad_recibida if detalles else Decimal("0"),
        status=transfer_status,
        priority=solicitud.prioridad,
        notes=solicitud.notas,
        created_at=solicitud.created_at,
        approved_at=solicitud.approved_at,
        dispatched_at=solicitud.dispatched_at,
        received_at=solicitud.received_at,
        lineas=lineas,
    )
