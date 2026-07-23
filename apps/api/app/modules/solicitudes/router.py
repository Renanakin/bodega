"""
Router FastAPI para solicitudes de recarga (Fase 3, ADR-0003 + Fase 4).

Endpoints:
- POST   /solicitudes                              - Crear (N productos)
- GET    /solicitudes                              - Listar con filtros
- GET    /solicitudes/distribucion/multibodega     - Vista spec §4.1
- GET    /solicitudes/bajo-minimo                  - Catalogo de productos bajo minimo (Fase 4)
- POST   /solicitudes/auto-generar                 - Trigger manual del ReplenishmentEvaluator (Fase 4)
- GET    /solicitudes/{id}                         - Obtener
- POST   /solicitudes/{id}/approve                 - Aprobar (no descuenta)
- POST   /solicitudes/{id}/dispatch                - Despachar (descuenta origen)
- POST   /solicitudes/{id}/receive                 - Recibir (incrementa origen)
- POST   /solicitudes/{id}/reject                  - Rechazar con motivo
- POST   /solicitudes/{id}/cancel                  - Cancelar (solo PENDING)

Reglas:
- R3: este archivo es HTTP puro; la logica esta en SolicitudService /
     ReplenishmentEvaluator.
- R6: cada accion es auditada via auth_service.
- ADR-0003: namespace unificado de estados.
- ADR-0004: el replenishment corre como cron Arq (ver apps/api/app/worker.py);
     este router expone el trigger manual.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.db.models.inventory import StockLevel
from app.db.models.products import Product
from app.db.models.solicitudes import DetalleSolicitudRecarga, SolicitudEstado, SolicitudRecarga
from app.db.models.warehouses import Warehouse
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.solicitudes.replenishment import (
    ReplenishmentEvaluator,
    _calcular_cantidad,
    _calcular_prioridad,
)
from app.modules.solicitudes.schemas import (
    DistribucionMultibodegaResponse,
    ReplenishmentReportResponse,
    SolicitudAprobacion,
    SolicitudCancelacion,
    SolicitudCreate,
    SolicitudDespacho,
    SolicitudLineaResponse,
    SolicitudRecepcion,
    SolicitudRechazo,
    SolicitudResponse,
    StockBajoMinimoResponse,
    TransferDerivedResponse,
)
from app.modules.solicitudes.service import SolicitudService
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_solicitud_service(session: AsyncSession = Depends(get_session)) -> SolicitudService:
    """Inyecta el service con su sesion async."""
    return SolicitudService(session)


def _view_to_response(view: Any) -> SolicitudResponse:
    """Convierte SolicitudView (dataclass) a SolicitudResponse (Pydantic)."""
    detalles_response: list[SolicitudLineaResponse] = []
    for d in view.detalles:
        detalles_response.append(
            SolicitudLineaResponse(
                id=d["id_producto"],
                producto_id=d["id_producto"],
                producto_sku=d.get("product_sku") or "",
                producto_nombre=d.get("product_name") or "",
                cantidad_solicitada=d["cantidad_solicitada"],
                cantidad_despachada=d["cantidad_despachada"],
                cantidad_recibida=d["cantidad_recibida"],
                barcode_validado=d.get("barcode_validado"),
                notas=d.get("notas"),
            )
        )
    return SolicitudResponse(
        id=view.id,
        codigo=view.codigo,
        bodega_origen_id=view.id_bodega_origen,
        bodega_origen_codigo=view.id_bodega_origen_codigo,
        bodega_origen_nombre=view.id_bodega_origen_nombre,
        bodega_origen_tipo=view.id_bodega_origen_tipo,
        bodega_destino_id=view.id_bodega_destino,
        bodega_destino_codigo=view.id_bodega_destino_codigo,
        bodega_destino_nombre=view.id_bodega_destino_nombre,
        estado=view.estado,
        prioridad=view.prioridad or "normal",
        notas=view.notas,
        motivo_rechazo=view.motivo_rechazo,
        created_at=view.created_at,
        approved_at=view.approved_at,
        dispatched_at=view.dispatched_at,
        received_at=view.received_at,
        lineas=detalles_response,
        total_productos=view.total_productos,
        total_unidades=view.total_unidades,
    )


# ===================================================================== CREATE


@router.post("", response_model=SolicitudResponse, status_code=status.HTTP_201_CREATED)
async def create_solicitud(
    payload: SolicitudCreate,
    current_user=Depends(require_roles("admin", "supervisor", "origin_operator")),
    service: SolicitudService = Depends(get_solicitud_service),
) -> SolicitudResponse:
    """Crea una solicitud de recarga (N productos)."""
    view = await service.create_solicitud(
        id_bodega_origen=payload.bodega_origen_id,
        id_bodega_destino=payload.bodega_destino_id,
        lineas=[
            {"id_producto": line.producto_id, "cantidad_solicitada": line.cantidad_solicitada}
            for line in payload.lineas
        ],
        prioridad=payload.prioridad,
        notas=payload.notas,
        user_id=current_user.id,
    )
    return _view_to_response(view)


# ======================================================================= LIST


@router.get("", response_model=list[SolicitudResponse])
async def list_solicitudes(
    # BUG 6 (fix 2026-07-22): estado acepta lista para que el
    # Consolidador pueda pedir ?estado=pending&estado=approved&estado=in_transit
    # en un solo GET. Antes la firma era ``str | None`` y FastAPI solo
    # respetaba el primer valor, dejando el resto silenciosamente
    # ignorado (asi el consolidador veia 0 solicitudes aunque hubiera
    # pendientes, aprobadas o in_transit).
    estado: list[str] | None = Query(default=None),
    bodega_origen_id: uuid.UUID | None = Query(default=None),
    bodega_destino_id: uuid.UUID | None = Query(default=None),
    fecha_desde: datetime | None = Query(default=None),
    fecha_hasta: datetime | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(
        default=50,
        ge=1,
        # Subido a 1000 para soportar el Consolidador de Quiebres, que
        # necesita agregar TODAS las solicitudes activas (pending,
        # approved, in_transit) en una sola vista. El default se mantiene
        # en 50 para el uso normal de la bandeja.
        le=1000,
    ),
    _=Depends(get_current_user),
    service: SolicitudService = Depends(get_solicitud_service),
) -> list[SolicitudResponse]:
    """Lista solicitudes con filtros opcionales."""
    # FastAPI entrega una lista vacia cuando el param no aparece; lo
    # normalizamos a None para que el service aplique la semantica
    # "sin filtro" en lugar de "estado IN ()" que devolveria vacio.
    estados = estado if estado else None
    views = await service.list(
        estado=estados,
        id_bodega_origen=bodega_origen_id,
        id_bodega_destino=bodega_destino_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        skip=skip,
        limit=limit,
    )
    return [_view_to_response(v) for v in views]


# =========================================================== DISTRIBUCION (spec §4.1)
# NOTA: las definiciones se movieron mas arriba (antes de /{solicitud_id})
# para que FastAPI las matchee antes que la ruta dinamica UUID.


# =========================================================== DISTRIBUCION (spec §4.1)
# IMPORTANTE: estas rutas estaticas deben declararse ANTES de /{solicitud_id}
# porque FastAPI matchea en orden y 'bajo-minimo' / 'distribucion/multibodega'
# sino caen en el parseador UUID y devuelven 422.


@router.get(
    "/distribucion/multibodega",
    response_model=DistribucionMultibodegaResponse,
)
async def get_distribucion_multibodega(
    sku: str = Query(..., min_length=1, max_length=80),
    _=Depends(get_current_user),
    service: SolicitudService = Depends(get_solicitud_service),
) -> DistribucionMultibodegaResponse:
    """Distribucion de un producto por bodega (spec §4.1).

    Formato: {bodega_code, bodega_tipo, total_quantity,
    ubicacion_principal, estado}.
    """
    from app.core.errors import ProductNotFoundError

    result = await service.get_distribucion_multibodega(sku=sku)
    if result is None:
        raise ProductNotFoundError(f"sku={sku}")
    return result


@router.get(
    "/bajo-minimo",
    response_model=list[StockBajoMinimoResponse],
)
async def get_productos_bajo_minimo(
    bodega_id: uuid.UUID | None = Query(
        default=None,
        description=(
            "Si se pasa, filtra a una sola bodega. Si no, lista todas "
            "las bodegas auxiliares con SKUs bajo minimo."
        ),
    ),
    _=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[StockBajoMinimoResponse]:
    """Lista SKUs bajo minimo de stock, opcionalmente filtrado por bodega.

    Consumido por la UI ``ReplenishmentPage`` para mostrar al bodeguero
    que productos necesitan reponerse y cuanto. La cantidad sugerida
    sigue la misma regla que el ``ReplenishmentEvaluator``.
    """
    # 1. Determinar bodegas a evaluar (auxiliares activas, opcionalmente 1)
    wh_stmt = select(Warehouse).where(
        Warehouse.warehouse_type == "auxiliar",
        Warehouse.is_active.is_(True),
    )
    if bodega_id is not None:
        wh_stmt = wh_stmt.where(Warehouse.id == bodega_id)
    whs = list((await session.execute(wh_stmt)).scalars().all())
    if not whs:
        return []

    # 2. Cargar todos los stock_levels bajo minimo de esas bodegas en 1 query
    wh_ids = [wh.id for wh in whs]
    stock_stmt = select(StockLevel).where(
        StockLevel.warehouse_id.in_(wh_ids),
        StockLevel.min_quantity > 0,
        StockLevel.quantity <= StockLevel.min_quantity,
    )
    stocks = list((await session.execute(stock_stmt)).scalars().all())
    if not stocks:
        return []

    # 3. Cachear bodegas y productos
    bodegas_by_id: dict[uuid.UUID, Warehouse] = {wh.id: wh for wh in whs}
    product_ids = {s.product_id for s in stocks}
    prod_stmt = select(Product).where(Product.id.in_(product_ids))
    productos: dict[uuid.UUID, Product] = {
        p.id: p for p in (await session.execute(prod_stmt)).scalars().all()
    }

    # 4. Armar la respuesta
    # BUG 9 (fix 2026-07-23): excluir SKUs que ya tienen linea en una
    # solicitud PENDING desde la misma bodega. Sin este filtro, la UI
    # mostraba filas inactivas que el Evaluator iba a omitir al disparar
    # (porque R6 = idempotencia por (bodega, producto)). El usuario
    # veia la fila, hacia click en 'Generar solicitudes' y el reporte
    # decia '0 creadas, 1 omitida' sin entender por que.
    product_ids = list({s.product_id for s in stocks})
    pendiente_lineas_stmt = (
        select(DetalleSolicitudRecarga.id_producto, SolicitudRecarga.id_bodega_origen)
        .join(SolicitudRecarga, DetalleSolicitudRecarga.id_solicitud == SolicitudRecarga.id)
        .where(
            SolicitudRecarga.id_bodega_origen.in_(wh_ids),
            SolicitudRecarga.estado == SolicitudEstado.PENDING.value,
            DetalleSolicitudRecarga.id_producto.in_(product_ids),
        )
    )
    productos_pendientes: set[tuple[uuid.UUID, uuid.UUID]] = {
        (row[0], row[1]) for row in (await session.execute(pendiente_lineas_stmt)).all()
    }
    items: list[StockBajoMinimoResponse] = []
    for stock in stocks:
        prod = productos.get(stock.product_id)
        if prod is None or not prod.is_active:
            continue
        wh = bodegas_by_id.get(stock.warehouse_id)
        if wh is None:
            continue
        # Omitir si (bodega, producto) ya tiene linea PENDING.
        if (stock.product_id, stock.warehouse_id) in productos_pendientes:
            continue
        items.append(
            StockBajoMinimoResponse(
                bodega_id=wh.id,
                bodega_codigo=wh.code,
                bodega_nombre=wh.name,
                producto_id=prod.id,
                producto_sku=prod.sku,
                producto_nombre=prod.name,
                stock_actual=stock.quantity,
                stock_minimo=stock.min_quantity,
                stock_maximo=stock.max_quantity,
                cantidad_sugerida=_calcular_cantidad(stock),
                # Mapeo explicito: 'alta' / 'normal' → "alta"/"normal" (no 'urgente' en v1).
                prioridad=("alta" if _calcular_prioridad(stock) == "alta" else "normal"),
            )
        )
    return items


# ===================================================================== GET ONE


@router.get("/{solicitud_id}", response_model=SolicitudResponse)
async def get_solicitud(
    solicitud_id: uuid.UUID,
    _=Depends(get_current_user),
    service: SolicitudService = Depends(get_solicitud_service),
) -> SolicitudResponse:
    view = await service.get_solicitud(solicitud_id)
    return _view_to_response(view)


# =============================================================== TRANSFERS LEGACY


@router.get(
    "/{solicitud_id}/derived",
    response_model=TransferDerivedResponse,
)
async def get_derived_transfer(
    solicitud_id: uuid.UUID,
    _=Depends(get_current_user),
    service: SolicitudService = Depends(get_solicitud_service),
) -> TransferDerivedResponse:
    """Vista derivada de una solicitud (compat 6 meses con /api/v1/transfers).

    Retorna la solicitud mapeada al schema de Transfer (1 producto, estados
    legacy). La primera linea de la solicitud se usa como product_id.
    """
    from app.core.errors import SolicitudNotFoundError

    view = await service.get_solicitud(solicitud_id)
    derived = await service.get_derived_transfer(view.codigo)
    if derived is None:
        raise SolicitudNotFoundError(str(solicitud_id))
    return derived


# ===================================================================== APPROVE


@router.post("/{solicitud_id}/approve", response_model=SolicitudResponse)
async def approve_solicitud(
    solicitud_id: uuid.UUID,
    _payload: SolicitudAprobacion = SolicitudAprobacion(),
    current_user=Depends(require_roles("admin", "supervisor")),
    service: SolicitudService = Depends(get_solicitud_service),
) -> SolicitudResponse:
    """Aprueba la solicitud (PENDING → APPROVED). NO descuenta stock."""
    view = await service.approve_solicitud(solicitud_id, user_id=current_user.id)
    return _view_to_response(view)


# ===================================================================== DISPATCH


@router.post("/{solicitud_id}/dispatch", response_model=SolicitudResponse)
async def dispatch_solicitud(
    solicitud_id: uuid.UUID,
    payload: SolicitudDespacho,
    current_user=Depends(require_roles("admin", "supervisor", "origin_operator")),
    service: SolicitudService = Depends(get_solicitud_service),
) -> SolicitudResponse:
    """Despacha con payload por linea (despacho parcial permitido).

    Body:
        {
            "lineas": [{"producto_id": "...", "cantidad_despachada": 5, "barcode": "..."}],
            "notas": "opcional"
        }
    """
    view = await service.dispatch(solicitud_id, payload, user_id=current_user.id)
    return _view_to_response(view)


# ===================================================================== RECEIVE


@router.post("/{solicitud_id}/receive", response_model=SolicitudResponse)
async def receive_solicitud(
    solicitud_id: uuid.UUID,
    payload: SolicitudRecepcion,
    current_user=Depends(require_roles("admin", "supervisor", "destination_operator")),
    service: SolicitudService = Depends(get_solicitud_service),
) -> SolicitudResponse:
    """Recibe una o mas lineas (parcial o completo, con barcode opcional)."""
    view = await service.receive(solicitud_id, payload, user_id=current_user.id)
    return _view_to_response(view)


# ===================================================================== REJECT


@router.post("/{solicitud_id}/reject", response_model=SolicitudResponse)
async def reject_solicitud(
    solicitud_id: uuid.UUID,
    payload: SolicitudRechazo,
    current_user=Depends(require_roles("admin", "supervisor")),
    service: SolicitudService = Depends(get_solicitud_service),
) -> SolicitudResponse:
    """Rechaza la solicitud (PENDING o APPROVED)."""
    view = await service.reject(solicitud_id, payload, user_id=current_user.id)
    return _view_to_response(view)


# ===================================================================== CANCEL


@router.post("/{solicitud_id}/cancel", response_model=SolicitudResponse)
async def cancel_solicitud(
    solicitud_id: uuid.UUID,
    _payload: SolicitudCancelacion = SolicitudCancelacion(),
    current_user=Depends(require_roles("admin", "supervisor", "origin_operator")),
    service: SolicitudService = Depends(get_solicitud_service),
) -> SolicitudResponse:
    """Cancela la solicitud (solo PENDING)."""
    view = await service.cancel_solicitud(solicitud_id, user_id=current_user.id)
    return _view_to_response(view)


# ============================================================== REPLENISHMENT (Fase 4)


@router.post(
    "/auto-generar",
    response_model=ReplenishmentReportResponse,
)
async def auto_generar_solicitudes(
    bodega_id: uuid.UUID | None = Query(
        default=None,
        description=(
            "Si se pasa, evalua solo esa bodega. Si no, evalua todas las auxiliares activas."
        ),
    ),
    dry_run: bool = Query(
        default=False,
        description="Si True, evalua y reporta pero NO crea solicitudes.",
    ),
    _current_user=Depends(require_roles("admin", "supervisor")),
    session: AsyncSession = Depends(get_session),
) -> ReplenishmentReportResponse:
    """Trigger manual del ReplenishmentEvaluator (Fase 4).

    Dispara la misma logica que el cron de Arq (cada 5 min) pero
    on-demand. Pensado para que el bodeguero central fuerce la corrida
    despues de un inventario manual o para ``dry_run=True`` (preview).

    Roles permitidos: admin, supervisor.
    """
    evaluator = ReplenishmentEvaluator(session)
    if bodega_id is not None:
        report = await evaluator.evaluate_one(bodega_id, dry_run=dry_run)
    else:
        report = await evaluator.evaluate_all(dry_run=dry_run)
    await session.commit()
    return ReplenishmentReportResponse(
        bodegas_evaluadas=report.bodegas_evaluadas,
        skus_bajo_minimo=report.skus_bajo_minimo,
        solicitudes_creadas=report.solicitudes_creadas,
        solicitudes_omitidas_pendientes=report.solicitudes_omitidas_pendientes,
        errores=report.errores,
        dry_run=report.dry_run,
        timestamp=datetime.now(UTC),
    )
