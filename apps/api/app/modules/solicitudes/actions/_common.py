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

    IMPORTANTE (P0 del roadmap Big-O): esta funcion hace 4 queries
    (1 solicitud + 2 bodegas + 1 detalles + 1 productos batch). NO es
    N+1 por si misma, pero cuando se llama N veces (caso de listar)
    se convierte en 4N queries. Para listados usar to_views_batch().
    """
    solicitud = await repo.get_by_id(solicitud_id)
    if solicitud is None:
        raise SolicitudNotFoundError(str(solicitud_id))
    views = await to_views_batch(session, repo, [solicitud])
    return views[0]


async def to_views_batch(
    session: AsyncSession, repo, solicitudes: list[SolicitudRecarga]
) -> list[SolicitudView]:
    """Convierte N solicitudes a views en 4 queries fijas totales (no N+1).

    Queries (cuando N >= 1):
      1. Detalles de TODAS las solicitudes: WHERE id_solicitud IN (...)
      2. Productos en batch: WHERE id IN (product_ids unicos)
      3. Bodegas origen en batch: WHERE id IN (origen_ids unicos)
      4. Bodegas destino en batch: WHERE id IN (destino_ids unicos)

    Si N == 0, retorna lista vacia sin queries.

    Antes del fix (P0): N solicitudes -> 4N queries.
    Despues: 4 queries fijas independiente de N.

    Performance: O(1) en queries independiente de n.
    """
    if not solicitudes:
        return []

    sol_ids = [s.id for s in solicitudes]
    origen_ids = list({s.id_bodega_origen for s in solicitudes})
    destino_ids = list({s.id_bodega_destino for s in solicitudes})

    # Query 1: detalles en batch
    # Usamos SELECT directo en DetalleSolicitudRecarga para evitar acoplar
    # al repo (que tiene su propia logica de orden). En sqlite/aiosqlite
    # in_(sol_ids) funciona con la PK compuesta.
    from app.db.models.solicitudes import DetalleSolicitudRecarga

    stmt_detalles = select(DetalleSolicitudRecarga).where(
        DetalleSolicitudRecarga.id_solicitud.in_(sol_ids)
    )
    detalles = list((await session.execute(stmt_detalles)).scalars().all())
    detalles_by_sol: dict[uuid.UUID, list] = {}
    for d in detalles:
        detalles_by_sol.setdefault(d.id_solicitud, []).append(d)

    # Query 2: productos (solo los que aparecen en los detalles)
    product_ids = list({d.id_producto for d in detalles})
    productos_by_id: dict[uuid.UUID, Product] = {}
    if product_ids:
        stmt_p = select(Product).where(Product.id.in_(product_ids))
        productos_by_id = {
            p.id: p for p in (await session.execute(stmt_p)).scalars().all()
        }

    # Query 3: bodegas origen en batch
    origen_by_id: dict[uuid.UUID, Warehouse] = {}
    if origen_ids:
        stmt_wo = select(Warehouse).where(Warehouse.id.in_(origen_ids))
        origen_by_id = {
            w.id: w for w in (await session.execute(stmt_wo)).scalars().all()
        }

    # Query 4: bodegas destino en batch
    destino_by_id: dict[uuid.UUID, Warehouse] = {}
    if destino_ids:
        stmt_wd = select(Warehouse).where(Warehouse.id.in_(destino_ids))
        destino_by_id = {
            w.id: w for w in (await session.execute(stmt_wd)).scalars().all()
        }

    # Construccion en memoria (O(n) sin queries adicionales)
    views: list[SolicitudView] = []
    for solicitud in solicitudes:
        wh_origen = origen_by_id.get(solicitud.id_bodega_origen)
        wh_destino = destino_by_id.get(solicitud.id_bodega_destino)
        dets = detalles_by_sol.get(solicitud.id, [])
        detalles_view: list[dict] = []
        total_unidades = Decimal("0")
        for d in dets:
            prod = productos_by_id.get(d.id_producto)
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
        views.append(
            SolicitudView(
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
                total_productos=len(dets),
                total_unidades=total_unidades,
            )
        )
    return views
