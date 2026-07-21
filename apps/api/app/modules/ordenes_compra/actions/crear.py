"""
Accion: crear orden de compra (estado BORRADOR).

Crea OC con lineas, valida bodega principal, supervisor activo y
productos existentes. Genera codigo OC-NNNN secuencial.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.core.errors import (
    InvalidOrdenCompraStatusError,
    OrdenCompraNotFoundError,
    ProductNotFoundError,
    WarehouseNotFoundError,
)
from app.core.logging import get_logger
from app.db.models.ordenes_compra import DetalleOrdenCompra, OrdenCompra, OrdenCompraEstado
from app.db.models.products import Product
from app.db.models.supervisores import Supervisor
from app.db.models.warehouses import Warehouse
from app.modules.ordenes_compra.actions._common import OrdenCompraView, to_view
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


async def create_orden(
    session: AsyncSession,
    *,
    id_bodega_principal: uuid.UUID,
    id_supervisor: uuid.UUID,
    proveedor_nombre: str,
    lineas: list[dict[str, Any]],
    proveedor_contacto: str | None = None,
    notas: str | None = None,
) -> OrdenCompraView:
    """Crea una OC en estado BORRADOR.

    Args:
        id_bodega_principal: FK a warehouses (debe ser tipo=principal).
        id_supervisor: FK a supervisores (debe estar activo).
        proveedor_nombre: nombre libre del proveedor externo.
        lineas: lista de dicts con `id_producto`, `cantidad_pedida`,
            `costo_unitario_pactado`.
        proveedor_contacto: opcional, telefono/email del proveedor.
        notas: opcional, notas libres.

    Returns:
        `OrdenCompraView` con la OC recien creada.

    Raises:
        WarehouseNotFoundError: si la bodega no existe o no es principal.
        ProductNotFoundError: si algun producto no existe.
        OrdenCompraNotFoundError: si el supervisor no existe o esta inactivo.
        InvalidOrdenCompraStatusError: si no hay lineas.
    """
    # Validar bodega principal
    wh = await session.get(Warehouse, id_bodega_principal)
    if wh is None:
        raise WarehouseNotFoundError(str(id_bodega_principal))
    if wh.warehouse_type != "principal":
        raise InvalidOrdenCompraStatusError(
            current=wh.warehouse_type,
            expected="principal (bodega)",
        )

    # Validar supervisor
    sup = await session.get(Supervisor, id_supervisor)
    if sup is None or not sup.activo:
        raise OrdenCompraNotFoundError(str(id_supervisor))

    if not lineas:
        raise InvalidOrdenCompraStatusError(current="empty", expected=">=1 linea")

    # Validar productos y calcular total en una sola query (evita N+1).
    # Antes: 1 query por linea -> N+1. Ahora: 1 query con WHERE id IN (...).
    product_ids = [line["id_producto"] for line in lineas]
    stmt_productos = select(Product).where(Product.id.in_(product_ids))
    productos = (await session.execute(stmt_productos)).scalars().all()
    productos_by_id = {p.id: p for p in productos}
    missing = [pid for pid in product_ids if pid not in productos_by_id]
    if missing:
        raise ProductNotFoundError(str(missing[0]))
    total = Decimal("0")
    for linea in lineas:
        total += linea["cantidad_pedida"] * linea["costo_unitario_pactado"]

    # Generar codigo OC-NNNN (secuencial, con prefijo zero-padded)
    count_stmt = select(OrdenCompra)
    result = await session.execute(count_stmt)
    next_code = f"OC-{len(result.scalars().all()) + 1:04d}"

    oc = OrdenCompra(
        id=uuid.uuid4(),
        codigo=next_code,
        id_bodega_principal=id_bodega_principal,
        id_supervisor=id_supervisor,
        proveedor_nombre=proveedor_nombre.strip(),
        proveedor_contacto=proveedor_contacto,
        estado=OrdenCompraEstado.BORRADOR,
        total_estimado=total,
        notas=notas,
    )
    session.add(oc)
    # Flush para que `oc.id` exista antes de crear los detalles
    # (la PK compuesta del detalle referencia `id_orden_compra`).
    await session.flush()
    for linea in lineas:
        detalle = DetalleOrdenCompra(
            id_orden_compra=oc.id,
            id_producto=linea["id_producto"],
            cantidad_pedida=linea["cantidad_pedida"],
            costo_unitario_pactado=linea["costo_unitario_pactado"],
        )
        session.add(detalle)
    await session.commit()
    await session.refresh(oc)
    log.info(
        "orden_compra.created",
        oc_id=str(oc.id),
        codigo=oc.codigo,
        total=str(total),
        lineas=len(lineas),
    )
    return await to_view(session, oc)
