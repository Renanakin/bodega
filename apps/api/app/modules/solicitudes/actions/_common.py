"""
Helpers compartidos por las acciones y queries de solicitudes.

Regla R3: este archivo solo tiene utilidades, no logica de negocio.
Regla R5: nombres descriptivos del rol (validate_direction, lock_or_404, to_view).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from app.core.errors import (
    InvalidSolicitudDirectionError,
    SolicitudNotFoundError,
)
from app.db.models.products import Product
from app.db.models.solicitudes import SolicitudEstado, SolicitudRecarga
from app.db.models.warehouses import Warehouse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------
# Helpers de tiempo y mapeos
# ---------------------------------------------------------------------


def utcnow() -> datetime:
    """Retorna el momento actual en UTC. Wrapper para testear facilmente."""
    return datetime.now(UTC)


def api_estado(estado: SolicitudEstado) -> str:
    """Mapea estado del modelo a estado de API (alias)."""
    return estado.value


# ---------------------------------------------------------------------
# Vista interna
# ---------------------------------------------------------------------


@dataclass(slots=True)
class SolicitudView:
    """Vista interna de la solicitud (el router la convierte a Pydantic)."""

    id: uuid.UUID
    codigo: str
    id_bodega_origen: uuid.UUID
    id_bodega_origen_codigo: str
    id_bodega_origen_nombre: str
    id_bodega_origen_tipo: str
    id_bodega_destino: uuid.UUID
    id_bodega_destino_codigo: str
    id_bodega_destino_nombre: str
    estado: str  # ya mapeado a API (partial en lugar de partially_received)
    prioridad: str | None
    notas: str | None
    motivo_rechazo: str | None
    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    received_at: datetime | None
    detalles: list[dict] = field(default_factory=list)
    total_productos: int = 0
    total_unidades: Decimal = Decimal("0")


# ---------------------------------------------------------------------
# Validaciones y lookups
# ---------------------------------------------------------------------


def validate_direction(origen: Warehouse, destino: Warehouse) -> None:
    """Valida la regla de direccion (ADR-0002).

    Reglas:
    - origen y destino no pueden ser la misma bodega.
    - Si origen es box, debe tener parent_warehouse_id.
    - destino NO puede ser box (los boxes no reciben recargas).
    - origen NO puede ser principal (las recargas se originan en aux/box).
    - destino DEBE ser principal.
    """
    if origen.id == destino.id:
        raise InvalidSolicitudDirectionError("Origen y destino no pueden ser la misma bodega.")
    if origen.warehouse_type == "mecanico_box" and not origen.parent_warehouse_id:
        raise InvalidSolicitudDirectionError(
            f"Bodega origen '{origen.code}' es box sin auxiliar padre asignado."
        )
    if destino.warehouse_type == "mecanico_box":
        raise InvalidSolicitudDirectionError(
            f"Bodega destino '{destino.code}' es box de mecanico; no recibe solicitudes de recarga."
        )
    if origen.warehouse_type == "principal":
        raise InvalidSolicitudDirectionError(
            f"Bodega origen '{origen.code}' es principal; "
            "las recargas se originan en auxiliares o boxes."
        )
    if destino.warehouse_type != "principal":
        raise InvalidSolicitudDirectionError(
            f"Bodega destino '{destino.code}' debe ser 'principal'; "
            f"recibio '{destino.warehouse_type}'."
        )


async def lock_or_404(repo, solicitud_id: uuid.UUID) -> SolicitudRecarga:
    """Obtiene la solicitud con lock pesimista o lanza 404."""
    solicitud = await repo.get_by_id_with_lock(solicitud_id)
    if solicitud is None:
        raise SolicitudNotFoundError(str(solicitud_id))
    return solicitud


async def to_view(session: AsyncSession, repo, solicitud_id: uuid.UUID) -> SolicitudView:
    """Construye la vista interna (dataclass) a partir del modelo.

    Cachea bodegas y productos en la sesion actual para evitar N+1
    al expandir todas las lineas.
    """
    solicitud = await repo.get_by_id(solicitud_id)
    if solicitud is None:
        raise SolicitudNotFoundError(str(solicitud_id))

    # Cache de bodegas y productos en esta sesion
    wh_origen = await session.get(Warehouse, solicitud.id_bodega_origen)
    wh_destino = await session.get(Warehouse, solicitud.id_bodega_destino)

    detalles = list(await repo.list_detalles(solicitud.id))
    detalles_view: list[dict] = []
    total_unidades = Decimal("0")
    product_ids = [d.id_producto for d in detalles]
    productos: dict[uuid.UUID, Product] = {}
    if product_ids:
        stmt = select(Product).where(Product.id.in_(product_ids))
        result = await session.execute(stmt)
        for p in result.scalars().all():
            productos[p.id] = p

    for d in detalles:
        prod = productos.get(d.id_producto)
        detalles_view.append(
            {
                "id_solicitud": d.id_solicitud,
                "id_producto": d.id_producto,
                "product_sku": prod.sku if prod else None,
                "product_name": prod.name if prod else None,
                "cantidad_solicitada": d.cantidad_solicitada,
                "cantidad_despachada": d.cantidad_despachada,
                "cantidad_recibida": d.cantidad_recibida,
                "barcode_validado": d.barcode_validado,
                "notas": d.notas,
            }
        )
        total_unidades += d.cantidad_solicitada

    return SolicitudView(
        id=solicitud.id,
        codigo=solicitud.codigo,
        id_bodega_origen=solicitud.id_bodega_origen,
        id_bodega_origen_codigo=wh_origen.code if wh_origen else "",
        id_bodega_origen_nombre=wh_origen.name if wh_origen else "",
        id_bodega_origen_tipo=wh_origen.warehouse_type if wh_origen else "",
        id_bodega_destino=solicitud.id_bodega_destino,
        id_bodega_destino_codigo=wh_destino.code if wh_destino else "",
        id_bodega_destino_nombre=wh_destino.name if wh_destino else "",
        estado=api_estado(solicitud.estado),
        prioridad=solicitud.prioridad,
        notas=solicitud.notas,
        motivo_rechazo=solicitud.motivo_rechazo,
        created_at=solicitud.created_at,
        approved_at=solicitud.approved_at,
        dispatched_at=solicitud.dispatched_at,
        received_at=solicitud.received_at,
        detalles=detalles_view,
        total_productos=len(detalles),
        total_unidades=total_unidades,
    )
