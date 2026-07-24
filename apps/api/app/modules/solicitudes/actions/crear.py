"""
Accion: crear solicitud de recarga (N productos, Fase 3).

Reglas (ADR-0002):
- origen ∈ {auxiliar, mecanico_box con parent_warehouse_id}
- destino = principal
- origen != destino
- cada producto debe existir y estar activo
- no se permiten productos duplicados
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.core.errors import (
    InvalidTransferQuantityError,
    ProductNotActiveError,
    ProductNotFoundError,
    WarehouseNotFoundError,
)
from app.core.logging import get_logger
from app.db.models.notificaciones import NotificationType
from app.db.models.products import Product
from app.db.models.users import UserRole
from app.db.models.warehouses import Warehouse
from app.modules.observability.metrics import SOLICITUDES_CREADAS
from app.modules.solicitudes.actions._common import (
    SolicitudView,
    to_view,
    validate_direction,
)
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.solicitudes.schemas import SolicitudCreate


log = get_logger(__name__)


async def create_solicitud(
    session: AsyncSession,
    repo,
    notif,
    *,
    id_bodega_origen: uuid.UUID,
    id_bodega_destino: uuid.UUID,
    lineas: list[dict],
    prioridad: str | None = None,
    notas: str | None = None,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Crea una solicitud de recarga (N productos) con codigo unico.

    Args:
        session: sesion async de SQLAlchemy.
        repo: SolicitudRepository.
        notif: NotificacionesService (inyectado para tests).
        id_bodega_origen: bodega auxiliar o box.
        id_bodega_destino: bodega principal.
        lineas: lista de `{"id_producto": UUID, "cantidad_solicitada": Decimal}`.
        prioridad: "normal" | "alta" | "urgente" (o None).
        notas: notas libres.
        user_id: usuario que crea (para audit_log).

    Returns:
        ``SolicitudView`` con la solicitud creada (estado PENDING).
    """
    # 1. Validar input basico
    if not lineas:
        raise InvalidTransferQuantityError("La solicitud debe tener al menos 1 linea")

    product_ids = [line["id_producto"] for line in lineas]
    if len(product_ids) != len(set(product_ids)):
        raise InvalidTransferQuantityError("Productos duplicados en la solicitud")

    # 2. Validar bodegas y direccion (ADR-0002)
    wh_origen = await session.get(Warehouse, id_bodega_origen)
    if wh_origen is None:
        raise WarehouseNotFoundError(str(id_bodega_origen))
    wh_destino = await session.get(Warehouse, id_bodega_destino)
    if wh_destino is None:
        raise WarehouseNotFoundError(str(id_bodega_destino))
    validate_direction(wh_origen, wh_destino)

    # 3. Validar productos (existencia + activos).
    # P0 (roadmap Big-O): 1 sola query batch con WHERE id IN (...).
    # Antes: 1 query por producto = N+1.
    from sqlalchemy import select
    productos_by_id: dict[uuid.UUID, Product] = {}
    if product_ids:
        stmt_p = select(Product).where(Product.id.in_(product_ids))
        productos_by_id = {
            p.id: p for p in (await session.execute(stmt_p)).scalars().all()
        }
    for pid in product_ids:
        p = productos_by_id.get(pid)
        if p is None:
            raise ProductNotFoundError(str(pid))
        if not p.is_active:
            raise ProductNotActiveError(str(pid), p.sku)

    # 4. Generar codigo unico
    codigo = await repo.generate_unique_codigo(prefix="SOL")

    # 5. Crear solicitud (estado PENDING)
    solicitud = await repo.create_solicitud(
        codigo=codigo,
        id_bodega_origen=id_bodega_origen,
        id_bodega_destino=id_bodega_destino,
        prioridad=prioridad,
        notas=notas,
    )
    for linea in lineas:
        await repo.add_linea(
            id_solicitud=solicitud.id,
            id_producto=linea["id_producto"],
            cantidad_solicitada=linea["cantidad_solicitada"],
        )

    await session.commit()
    await session.refresh(solicitud)

    # Metricas Fase 9: incrementar contador de solicitudes creadas
    # con labels de tipo de bodega origen y prioridad. Cardinalidad
    # baja (3 tipos x 3 prioridades = 9 max).
    prioridad_label = (prioridad or "none").lower()
    origen_tipo_label = wh_origen.warehouse_type or "unknown"
    SOLICITUDES_CREADAS.labels(
        bodega_origen_tipo=origen_tipo_label,
        prioridad=prioridad_label,
    ).inc()

    log.info(
        "solicitud.created",
        solicitud_id=str(solicitud.id),
        codigo=solicitud.codigo,
        origen=wh_origen.code,
        origen_tipo=wh_origen.warehouse_type,
        destino=wh_destino.code,
        total_productos=len(lineas),
        user_id=str(user_id) if user_id else None,
    )

    # Notificar a admin+supervisor (excluyendo al actor).
    await notif.notify_role_except_actor(
        actor_id=user_id,
        roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
        tipo=NotificationType.SOLICITUD_CREATED.value,
        titulo=f"Nueva solicitud {solicitud.codigo}",
        mensaje=(f"{wh_origen.code} -> {wh_destino.code}: {len(lineas)} producto(s)"),
        payload=(
            f'{{"solicitud_id": "{solicitud.id}", '
            f'"codigo": "{solicitud.codigo}", '
            f'"origen": "{wh_origen.code}", '
            f'"destino": "{wh_destino.code}"}}'
        ),
    )

    return await to_view(session, repo, solicitud.id)


async def create(
    session: AsyncSession,
    repo,
    notif,
    payload: SolicitudCreate,
    user_id: uuid.UUID | None = None,
) -> SolicitudView:
    """Sobrecarga: acepta un ``SolicitudCreate`` Pydantic."""
    return await create_solicitud(
        session,
        repo,
        notif,
        id_bodega_origen=payload.bodega_origen_id,
        id_bodega_destino=payload.bodega_destino_id,
        lineas=[
            {"id_producto": line.producto_id, "cantidad_solicitada": line.cantidad_solicitada}
            for line in payload.lineas
        ],
        prioridad=payload.prioridad,
        notas=payload.notas,
        user_id=user_id,
    )
