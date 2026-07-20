"""
Helpers compartidos por acciones y queries de ordenes de compra.

Regla R3: este archivo solo tiene utilidades, no logica de negocio.
Regla R5: nombres descriptivos del rol (require_oc, to_view).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import OrdenCompraNotFoundError
from app.db.models.ordenes_compra import (
    DetalleOrdenCompra,
    OrdenCompra,
    OrdenCompraEstado,
)
from app.db.models.products import Product
from app.db.models.supervisores import Supervisor


# Estado terminal: una OC en estos estados NO acepta nuevas transiciones.
ESTADOS_TERMINALES = frozenset({
    OrdenCompraEstado.RECHAZADO,
    OrdenCompraEstado.COMPRADO,
})


@dataclass(slots=True)
class OrdenCompraView:
    """Vista agregada que el router expone como JSON."""

    id: uuid.UUID
    codigo: str
    id_bodega_principal: uuid.UUID
    id_supervisor: uuid.UUID
    supervisor_nombre: str | None
    supervisor_email: str | None
    proveedor_nombre: str
    proveedor_contacto: str | None
    estado: str
    total_estimado: Decimal
    notas: str | None
    motivo_rechazo: str | None
    email_enviado_at: datetime | None
    email_token_jti: str | None
    aprobado_at: datetime | None
    comprado_at: datetime | None
    created_at: datetime
    updated_at: datetime | None
    detalles: list[dict] = field(default_factory=list)


async def require_oc(
    session: AsyncSession, oc_id: uuid.UUID
) -> OrdenCompra:
    """Obtiene la OC por ID o lanza 404."""
    oc = await session.get(OrdenCompra, oc_id)
    if oc is None:
        raise OrdenCompraNotFoundError(str(oc_id))
    return oc


async def to_view(
    session: AsyncSession, oc: OrdenCompra
) -> OrdenCompraView:
    """Construye la vista agregada a partir del modelo OC."""
    detalles_stmt = select(DetalleOrdenCompra).where(
        DetalleOrdenCompra.id_orden_compra == oc.id
    )
    detalles = list((await session.execute(detalles_stmt)).scalars().all())
    detalles_view: list[dict] = []
    for d in detalles:
        p = await session.get(Product, d.id_producto)
        detalles_view.append({
            "id_orden_compra": d.id_orden_compra,
            "id_producto": d.id_producto,
            "product_sku": p.sku if p else None,
            "product_name": p.name if p else None,
            "cantidad_pedida": d.cantidad_pedida,
            "costo_unitario_pactado": d.costo_unitario_pactado,
        })

    sup = await session.get(Supervisor, oc.id_supervisor)
    return OrdenCompraView(
        id=oc.id,
        codigo=oc.codigo,
        id_bodega_principal=oc.id_bodega_principal,
        id_supervisor=oc.id_supervisor,
        supervisor_nombre=sup.nombre if sup else None,
        supervisor_email=sup.email if sup else None,
        proveedor_nombre=oc.proveedor_nombre,
        proveedor_contacto=oc.proveedor_contacto,
        estado=oc.estado.value,
        total_estimado=oc.total_estimado,
        notas=oc.notas,
        motivo_rechazo=oc.motivo_rechazo,
        email_enviado_at=oc.email_enviado_at,
        email_token_jti=oc.email_token_jti,
        aprobado_at=oc.aprobado_at,
        comprado_at=oc.comprado_at,
        created_at=oc.created_at,
        updated_at=oc.created_at,  # modelo reusa created_at para updated_at
        detalles=detalles_view,
    )
