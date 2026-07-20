"""
Accion: actualizar orden de compra (solo si esta en BORRADOR).

Permite cambiar supervisor, proveedor_nombre, proveedor_contacto, notas.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    InvalidOrdenCompraStatusError,
    OrdenCompraNotFoundError,
)
from app.core.logging import get_logger
from app.db.models.ordenes_compra import OrdenCompraEstado
from app.db.models.supervisores import Supervisor

from app.modules.ordenes_compra.actions._common import OrdenCompraView, require_oc, to_view


log = get_logger(__name__)


async def update_orden(
    session: AsyncSession,
    oc_id: uuid.UUID,
    *,
    proveedor_nombre: str | None = None,
    proveedor_contacto: str | None = None,
    notas: str | None = None,
    id_supervisor: uuid.UUID | None = None,
) -> OrdenCompraView:
    """Actualiza una OC SOLO si esta en estado BORRADOR.

    Raises:
        InvalidOrdenCompraStatusError: si la OC no esta en BORRADOR.
        OrdenCompraNotFoundError: si se cambia el supervisor a uno inexistente.
    """
    oc = await require_oc(session, oc_id)
    if oc.estado != OrdenCompraEstado.BORRADOR:
        raise InvalidOrdenCompraStatusError(
            current=oc.estado.value,
            expected=OrdenCompraEstado.BORRADOR.value,
        )

    if id_supervisor is not None and id_supervisor != oc.id_supervisor:
        sup = await session.get(Supervisor, id_supervisor)
        if sup is None or not sup.activo:
            raise OrdenCompraNotFoundError(str(id_supervisor))
        oc.id_supervisor = id_supervisor

    if proveedor_nombre is not None:
        oc.proveedor_nombre = proveedor_nombre.strip()
    if proveedor_contacto is not None:
        oc.proveedor_contacto = proveedor_contacto
    if notas is not None:
        oc.notas = notas

    await session.commit()
    await session.refresh(oc)
    log.info("orden_compra.updated", oc_id=str(oc.id))
    return await to_view(session, oc)
