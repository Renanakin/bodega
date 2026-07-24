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

from app.core.errors import OrdenCompraNotFoundError
from app.db.models.ordenes_compra import (
    DetalleOrdenCompra,
    OrdenCompra,
    OrdenCompraEstado,
)
from app.db.models.products import Product
from app.db.models.supervisores import Supervisor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Estado terminal: una OC en estos estados NO acepta nuevas transiciones.
ESTADOS_TERMINALES = frozenset(
    {
        OrdenCompraEstado.RECHAZADO,
        OrdenCompraEstado.COMPRADO,
    }
)


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


async def require_oc(session: AsyncSession, oc_id: uuid.UUID) -> OrdenCompra:
    """Obtiene la OC por ID o lanza 404."""
    oc = await session.get(OrdenCompra, oc_id)
    if oc is None:
        raise OrdenCompraNotFoundError(str(oc_id))
    return oc


async def to_view(session: AsyncSession, oc: OrdenCompra) -> OrdenCompraView:
    """Construye la vista agregada a partir del modelo OC.

    IMPORTANTE (P0 del roadmap Big-O): esta funcion hace 3 queries (1
    detalles + 1 productos batch + 1 supervisor). NO es N+1 dentro de
    si misma, pero cuando se llama N veces (caso de list_ordenes),
    se convierte en N*3 queries. Para listados usar to_views_batch().
    """
    views = await to_views_batch(session, [oc])
    return views[0]


async def to_views_batch(
    session: AsyncSession, ocs: list[OrdenCompra]
) -> list[OrdenCompraView]:
    """Convierte N OCs a views en 3 queries fijas totales (no N+1).

    Queries (cuando N >= 1):
      1. Detalles de TODAS las OCs en una sola query: WHERE id_orden_compra IN (...)
      2. Productos en batch: WHERE id IN (product_ids unicos de los detalles)
      3. Supervisores en batch: WHERE id IN (id_supervisor unicos)

    Si N == 0, retorna lista vacia sin queries.

    Antes del fix (P0): N OCs -> 3N queries (1 supervisor + 1 detalles
    + 1 productos por cada OC). Con 1000 OCs = 3000 queries.
    Despues: N OCs -> 3 queries fijas.

    Performance: O(1) en queries independiente de n.
    """
    if not ocs:
        return []

    oc_ids = [oc.id for oc in ocs]
    sup_ids = list({oc.id_supervisor for oc in ocs})

    # Query 1: detalles de TODAS las OCs en una sola pasada
    stmt_detalles = select(DetalleOrdenCompra).where(
        DetalleOrdenCompra.id_orden_compra.in_(oc_ids)
    )
    detalles = list((await session.execute(stmt_detalles)).scalars().all())
    detalles_by_oc: dict[uuid.UUID, list[DetalleOrdenCompra]] = {}
    for d in detalles:
        detalles_by_oc.setdefault(d.id_orden_compra, []).append(d)

    # Query 2: productos (solo los que aparecen en los detalles)
    product_ids = list({d.id_producto for d in detalles})
    productos_by_id: dict[uuid.UUID, Product] = {}
    if product_ids:
        stmt_productos = select(Product).where(Product.id.in_(product_ids))
        productos_by_id = {
            p.id: p for p in (await session.execute(stmt_productos)).scalars().all()
        }

    # Query 3: supervisores en batch
    sups_by_id: dict[uuid.UUID, Supervisor] = {}
    if sup_ids:
        stmt_sups = select(Supervisor).where(Supervisor.id.in_(sup_ids))
        sups_by_id = {
            s.id: s for s in (await session.execute(stmt_sups)).scalars().all()
        }

    # Construccion en memoria (O(n) pero sin queries adicionales)
    views: list[OrdenCompraView] = []
    for oc in ocs:
        sup = sups_by_id.get(oc.id_supervisor)
        dets = detalles_by_oc.get(oc.id, [])
        detalles_view: list[dict] = []
        for d in dets:
            p = productos_by_id.get(d.id_producto)
            detalles_view.append(
                {
                    "id_orden_compra": d.id_orden_compra,
                    "id_producto": d.id_producto,
                    "product_sku": p.sku if p else None,
                    "product_name": p.name if p else None,
                    "cantidad_pedida": d.cantidad_pedida,
                    "costo_unitario_pactado": d.costo_unitario_pactado,
                }
            )
        views.append(
            OrdenCompraView(
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
        )
    return views
