"""
ReplenishmentEvaluator: detecta stock bajo minimo y crea solicitudes automaticas (Fase 4).

Reglas:
- Solo bodegas auxiliares disparan evaluacion (NO principal, NO mecanico_box).
  Las boxes consumen del auxiliar padre via suma recursiva (ADR-0002 IMP-005),
  pero en esta fase la alerta se genera solo en el nivel auxiliar.
- Si stock <= minimo, crea solicitud de reposicion por la diferencia a max_quantity.
- Si no hay max_quantity definido, usa un default de 2 * min_quantity.
- Solo procesa productos activos (Product.is_active == True).
- Idempotencia (R6): si ya hay solicitud PENDING para la bodega, NO crea otra.
- Prioridad automatica: 'alta' si quantity < min_quantity/2, 'normal' en caso contrario.
- Cada ejecucion emite log estructurado `replenishment.evaluated`.
- Soporta `dry_run=True` para no persistir solicitudes (testing, preview UI).
- `evaluate_one(warehouse_id)` para trigger manual selectivo (endpoint).

Arquitectura:
- R3: la logica vive en esta clase; el router solo la invoca y serializa
  la respuesta. El cron de Arq la consume via `apps/api/app/worker.py`.
- R4: el Evaluator NO escribe SQL directo; usa el AsyncSession inyectado
  y delega la creacion de solicitudes a `SolicitudService`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.db.models.inventory import StockLevel
from app.db.models.products import Product
from app.db.models.solicitudes import SolicitudEstado, SolicitudRecarga
from app.db.models.warehouses import Warehouse
from app.modules.solicitudes.service import SolicitudService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    pass


log = get_logger(__name__)


# Umbral para prioridad 'alta': si quantity esta bajo el 50% del minimo.
ALTA_PRIORIDAD_UMBRAL = Decimal("0.5")


@dataclass(slots=True)
class ReplenishmentReport:
    """Resultado de una evaluacion de reposicion.

    Attributes:
        bodegas_evaluadas: cantidad de bodegas auxiliares procesadas.
        skus_bajo_minimo: total de combinaciones (bodega, producto) bajo minimo.
        solicitudes_creadas: cantidad de solicitudes nuevas generadas.
        solicitudes_omitidas_pendientes: bodegas que se omitieron porque ya
            tenian una solicitud PENDING (idempotencia R6).
        errores: lista de mensajes de error por bodega (no rompe la corrida).
        dry_run: True si la corrida no persistio cambios.
    """

    bodegas_evaluadas: int = 0
    skus_bajo_minimo: int = 0
    solicitudes_creadas: int = 0
    solicitudes_omitidas_pendientes: int = 0
    errores: list[str] = field(default_factory=list)
    dry_run: bool = False


def _calcular_cantidad(stock: StockLevel) -> Decimal:
    """Cantidad sugerida para reponer un SKU bajo minimo.

    Regla:
        - Si `max_quantity` esta definido: `max_quantity - quantity`.
        - Si NO esta definido: `min_quantity * 2 - quantity` (fallback).

    Garantiza que el resultado sea > 0; si por algun motivo la cuenta da
    <=0, retorna 0 y el caller debe skipear la linea.
    """
    target = stock.max_quantity if stock.max_quantity is not None else stock.min_quantity * 2
    cantidad = target - stock.quantity
    return cantidad if cantidad > 0 else Decimal("0")


def _calcular_prioridad(stock: StockLevel) -> str:
    """Prioridad automatica segun el ratio quantity / min_quantity.

    - quantity < min_quantity * 0.5  → 'alta' (critico)
    - en caso contrario              → 'normal'
    """
    if stock.min_quantity <= 0:
        return "normal"
    ratio = stock.quantity / stock.min_quantity
    if ratio < ALTA_PRIORIDAD_UMBRAL:
        return "alta"
    return "normal"


class ReplenishmentEvaluator:
    """Evalua el stock de bodegas auxiliares y crea solicitudes automaticas.

    Uso tipico (worker Arq):
        async with session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_all()
            await session.commit()

    Uso manual (endpoint /auto-generar):
        async with session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_one(bodega_id)
            await session.commit()
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._solicitud_service = SolicitudService(session)

    # ============================================================== PUBLIC API

    async def evaluate_all(self, *, dry_run: bool = False) -> ReplenishmentReport:
        """Evalua todas las bodegas auxiliares.

        Por cada combinacion (auxiliar, producto) con quantity <= min_quantity:
        - Si ya hay solicitud PENDING para esa bodega, omite (idempotencia R6).
        - Si no, crea una solicitud automatica a la principal.

        Args:
            dry_run: si True, evalua y arma el reporte pero NO crea
                solicitudes. Util para preview desde el endpoint.

        Returns:
            ``ReplenishmentReport`` con metricas de la corrida.
        """
        report = ReplenishmentReport(dry_run=dry_run)

        # 1. Listar auxiliares activas
        wh_stmt = select(Warehouse).where(
            Warehouse.warehouse_type == "auxiliar",
            Warehouse.is_active.is_(True),
        )
        result = await self._session.execute(wh_stmt)
        auxiliares = list(result.scalars().all())
        report.bodegas_evaluadas = len(auxiliares)

        # 2. Por cada auxiliar, escanear stock bajo minimo
        for wh in auxiliares:
            try:
                await self.evaluate_warehouse(wh, dry_run=dry_run, report=report)
            except Exception as exc:  # noqa: BLE001
                # No rompemos la corrida por una bodega problematic; el
                # reporte lista el error para triage posterior (R8).
                report.errores.append(f"{wh.code}: {exc!s}")
                log.warning(
                    "replenishment.warehouse_error",
                    bodega=wh.code,
                    error=str(exc),
                )

        log.info(
            "replenishment.evaluated",
            bodegas=report.bodegas_evaluadas,
            skus_bajo_minimo=report.skus_bajo_minimo,
            solicitudes_creadas=report.solicitudes_creadas,
            solicitudes_omitidas=report.solicitudes_omitidas_pendientes,
            errores=len(report.errores),
            dry_run=dry_run,
        )
        return report

    async def evaluate_warehouse(
        self,
        wh: Warehouse,
        *,
        dry_run: bool = False,
        report: ReplenishmentReport | None = None,
    ) -> ReplenishmentReport:
        """Evalua una bodega especifica (puede ser auxiliar o no).

        Si el caller ya tiene un ``ReplenishmentReport`` (caso de
        ``evaluate_all``), se muta in-place. Si no, se crea uno nuevo
        con `bodegas_evaluadas=1` y se retorna.

        Reglas:
        - La bodega debe estar activa y ser tipo 'auxiliar'.
          Si no, se registra como error y no se procesa.
        - Solo se procesan productos activos.
        - Si ya hay solicitud PENDING desde esta bodega, se omite.
        """
        own_report = report is None
        if own_report:
            report = ReplenishmentReport(dry_run=dry_run)
        if own_report:
            report.bodegas_evaluadas = 1

        # Validar tipo
        if wh.warehouse_type != "auxiliar":
            report.errores.append(
                f"{wh.code}: solo bodegas 'auxiliar' disparan replenishment "
                f"(recibido '{wh.warehouse_type}')"
            )
            return report
        if not wh.is_active:
            report.errores.append(f"{wh.code}: bodega inactiva")
            return report

        # Encontrar la principal
        princ_stmt = select(Warehouse).where(
            Warehouse.warehouse_type == "principal",
            Warehouse.is_active.is_(True),
        )
        principal = (await self._session.execute(princ_stmt)).scalars().first()
        if principal is None:
            report.errores.append(f"No hay bodega principal para atender a {wh.code}")
            return report

        # Idempotencia (R6): si ya hay solicitud PENDING desde esta bodega, omitir
        pendiente_stmt = select(SolicitudRecarga).where(
            SolicitudRecarga.id_bodega_origen == wh.id,
            SolicitudRecarga.estado == SolicitudEstado.PENDING.value,
        )
        if (await self._session.execute(pendiente_stmt)).scalars().first() is not None:
            report.solicitudes_omitidas_pendientes += 1
            log.info(
                "replenishment.skipped_pending",
                bodega=wh.code,
                motivo="solicitud PENDING existente",
            )
            return report

        # Stock bajo minimo
        stock_stmt = select(StockLevel).where(
            StockLevel.warehouse_id == wh.id,
            StockLevel.min_quantity > 0,
            StockLevel.quantity <= StockLevel.min_quantity,
        )
        stocks = list((await self._session.execute(stock_stmt)).scalars().all())
        report.skus_bajo_minimo += len(stocks)

        if not stocks:
            return report

        # Construir lineas. Agrupamos por prioridad para no generar
        # 1 solicitud por SKU (eso seria ruido): una sola solicitud
        # por bodega con todas las lineas necesarias.
        lineas: list[dict] = []
        prioridades: set[str] = set()
        for stock in stocks:
            cantidad = _calcular_cantidad(stock)
            if cantidad <= 0:
                continue
            # Validar que el producto existe y esta activo
            prod = await self._session.get(Product, stock.product_id)
            if prod is None or not prod.is_active:
                log.info(
                    "replenishment.product_skipped",
                    bodega=wh.code,
                    product_id=str(stock.product_id),
                    motivo="producto inactivo o inexistente",
                )
                continue
            prioridad = _calcular_prioridad(stock)
            prioridades.add(prioridad)
            lineas.append(
                {
                    "id_producto": stock.product_id,
                    "cantidad_solicitada": cantidad,
                }
            )

        if not lineas:
            return report

        # Si hay mezcla, gana 'alta' (caso critico manda)
        prioridad_final = "alta" if "alta" in prioridades else "normal"

        if dry_run:
            # En dry_run contamos como "hubiera creado" para que el reporte
            # muestre el impacto esperado, pero no persistimos nada.
            report.solicitudes_creadas += 1
            log.info(
                "replenishment.dry_run_would_create",
                bodega=wh.code,
                lineas=len(lineas),
                prioridad=prioridad_final,
            )
            return report

        # Crear solicitud via SolicitudService (regla de oro R4: el
        # service es el unico que puede crear solicitudes; el Evaluator
        # solo orquesta).
        view = await self._solicitud_service.create_solicitud(
            id_bodega_origen=wh.id,
            id_bodega_destino=principal.id,
            lineas=lineas,
            prioridad=prioridad_final,
            notas="Reposicion automatica generada por ReplenishmentEvaluator",
        )
        report.solicitudes_creadas += 1
        log.info(
            "replenishment.solicitud_created",
            solicitud_id=str(view.id),
            codigo=view.codigo,
            bodega_origen=wh.code,
            total_lineas=len(lineas),
            prioridad=prioridad_final,
        )
        return report

    async def evaluate_one(
        self,
        warehouse_id: uuid.UUID,
        *,
        dry_run: bool = False,
    ) -> ReplenishmentReport:
        """Evalua una sola bodega por UUID (trigger manual desde UI).

        Args:
            warehouse_id: UUID de la bodega a evaluar.
            dry_run: si True, no persiste solicitudes.

        Returns:
            ``ReplenishmentReport`` con metricas (siempre bodegas_evaluadas=1).
        """
        wh = await self._session.get(Warehouse, warehouse_id)
        if wh is None:
            report = ReplenishmentReport(dry_run=dry_run)
            report.errores.append(f"Bodega '{warehouse_id}' no encontrada")
            return report
        return await self.evaluate_warehouse(wh, dry_run=dry_run)
