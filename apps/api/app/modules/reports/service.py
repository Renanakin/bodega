"""Reportes service (Fase 8).

Calcula el snapshot ejecutivo a partir de las tablas de dominio.
Las queries son agregaciones SQL (no iteran filas en Python) para
mantener latencia < 100ms con hasta ~100k stock_levels y ~500k
inventory_movements (dimensionamiento ADR-0001).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.inventory import InventoryMovement, MovementType, StockLevel
from app.db.models.products import Product
from app.db.models.solicitudes import SolicitudEstado, SolicitudRecarga
from app.db.models.warehouses import Warehouse
from app.modules.reports.schemas import (
    EjecutivoSnapshot,
    TopProducto,
    ValorPorBodega,
)

log = get_logger(__name__)

TOP_N_DEFAULT = 5


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_ejecutivo_snapshot(self, top_n: int = TOP_N_DEFAULT) -> EjecutivoSnapshot:
        """Calcula todos los KPIs en una sola llamada.

        Args:
            top_n: cuantos items en los rankings (default 5).

        Returns:
            ``EjecutivoSnapshot`` con todos los KPIs.
        """
        now = datetime.now(UTC)

        # -------------------------------------------------------------------
        # 1) Stock total activo valorizado: sum(quantity * precio_costo) sobre
        #    stock_levels joined con products (solo productos activos).
        # -------------------------------------------------------------------
        valor_total_query = (
            select(func.coalesce(func.sum(StockLevel.quantity * Product.precio_costo), 0))
            .join(Product, Product.id == StockLevel.product_id)
            .where(StockLevel.quantity > 0)
            .where(Product.is_active == True)  # noqa: E712
        )
        valor_total = (await self._session.execute(valor_total_query)).scalar_one()

        # -------------------------------------------------------------------
        # 2) Alertas criticas: count de stock_levels bajo minimo.
        # -------------------------------------------------------------------
        alertas_query = select(func.count(StockLevel.id)).where(
            StockLevel.min_quantity > 0,
            StockLevel.quantity <= StockLevel.min_quantity,
        )
        alertas_count = (await self._session.execute(alertas_query)).scalar_one()

        # -------------------------------------------------------------------
        # 3) Transferencias en ruta: count de solicitudes in_transit o
        #    partially_received.
        # -------------------------------------------------------------------
        en_ruta_query = select(func.count(SolicitudRecarga.id)).where(
            SolicitudRecarga.estado.in_(
                [SolicitudEstado.IN_TRANSIT, SolicitudEstado.PARTIALLY_RECEIVED]
            )
        )
        en_ruta_count = (await self._session.execute(en_ruta_query)).scalar_one()

        # -------------------------------------------------------------------
        # 4) Solicitudes por estado: GROUP BY estado, count.
        # -------------------------------------------------------------------
        por_estado_query = select(
            SolicitudRecarga.estado, func.count(SolicitudRecarga.id)
        ).group_by(SolicitudRecarga.estado)
        por_estado_rows = (await self._session.execute(por_estado_query)).all()
        solicitudes_por_estado = {str(estado.value): int(count) for estado, count in por_estado_rows}

        # -------------------------------------------------------------------
        # 5) Top productos mas movidos: sum |quantity| por producto en
        #    inventory_movements, top N.
        # -------------------------------------------------------------------
        # Usamos ABS(quantity) para que IN (+) y OUT (-) tengan mismo peso
        # en el ranking. Si solo los OUT contaran, daria un ranking distinto
        # (productos que mas salen vs que mas rotan).
        mas_mov = await self._mas_menos_movidos(top_n=top_n, asc=False)
        menos_mov = await self._mas_menos_movidos(top_n=top_n, asc=True)

        # -------------------------------------------------------------------
        # 6) Valor por bodega.
        # -------------------------------------------------------------------
        valor_por_bodega = await self._valor_por_bodega()

        # -------------------------------------------------------------------
        # 7) Conteos globales.
        # -------------------------------------------------------------------
        total_productos = (
            await self._session.execute(
                select(func.count(Product.id)).where(Product.is_active == True)  # noqa: E712
            )
        ).scalar_one()
        total_bodegas = (
            await self._session.execute(
                select(func.count(Warehouse.id)).where(Warehouse.is_active == True)  # noqa: E712
            )
        ).scalar_one()

        return EjecutivoSnapshot(
            generado_en=now,
            stock_total_activo_valorizado=Decimal(str(valor_total or 0)),
            alertas_criticas_count=int(alertas_count or 0),
            transferencias_en_ruta_count=int(en_ruta_count or 0),
            solicitudes_por_estado=solicitudes_por_estado,
            top_productos_mas_movidos=mas_mov,
            top_productos_menos_movidos=menos_mov,
            valor_por_bodega=valor_por_bodega,
            total_productos_activos=int(total_productos or 0),
            total_bodegas=int(total_bodegas or 0),
            config={"top_n": top_n},
        )

    # ----------------------------------------------------------- helpers

    async def _mas_menos_movidos(
        self, top_n: int, asc: bool
    ) -> list[TopProducto]:
        """Ranking de productos por ``sum |quantity|`` de movimientos.

        Args:
            top_n: limite del ranking.
            asc: True => menos movidos (ORDER BY ... ASC), False => mas movidos.

        Returns:
            Lista de ``TopProducto`` con `unidades_movidas` y `movimientos_count`.
        """
        # Las dos metricas se computan en el mismo GROUP BY (un solo round-trip).
        # Usamos func.abs(quantity) para neutralizar signo IN/OUT.
        agg = (
            select(
                InventoryMovement.product_id,
                Product.sku,
                Product.name,
                func.coalesce(func.sum(func.abs(InventoryMovement.quantity)), 0).label(
                    "unidades"
                ),
                func.count(InventoryMovement.id).label("movs"),
            )
            .join(Product, Product.id == InventoryMovement.product_id)
            .group_by(
                InventoryMovement.product_id, Product.sku, Product.name
            )
            .order_by(
                func.coalesce(func.sum(func.abs(InventoryMovement.quantity)), 0).asc()
                if asc
                else func.coalesce(func.sum(func.abs(InventoryMovement.quantity)), 0).desc()
            )
            .limit(top_n)
        )
        rows = (await self._session.execute(agg)).all()
        return [
            TopProducto(
                producto_id=pid,
                sku=sku,
                nombre=nombre,
                unidades_movidas=Decimal(str(unidades or 0)),
                movimientos_count=int(movs or 0),
            )
            for pid, sku, nombre, unidades, movs in rows
        ]

    async def _valor_por_bodega(self) -> list[ValorPorBodega]:
        """Desglose de stock y valor por bodega (solo bodegas activas)."""
        stmt = (
            select(
                Warehouse.id,
                Warehouse.code,
                Warehouse.name,
                Warehouse.warehouse_type,
                func.coalesce(func.sum(StockLevel.quantity), 0).label("unidades"),
                func.coalesce(
                    func.sum(StockLevel.quantity * Product.precio_costo), 0
                ).label("valor"),
            )
            .join(StockLevel, StockLevel.warehouse_id == Warehouse.id)
            .join(Product, Product.id == StockLevel.product_id)
            .where(Warehouse.is_active == True)  # noqa: E712
            .where(Product.is_active == True)  # noqa: E712
            .group_by(
                Warehouse.id, Warehouse.code, Warehouse.name, Warehouse.warehouse_type
            )
            .order_by(
                func.coalesce(
                    func.sum(StockLevel.quantity * Product.precio_costo), 0
                ).desc()
            )
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            ValorPorBodega(
                bodega_id=bid,
                bodega_code=code,
                bodega_name=name,
                bodega_type=warehouse_type,
                valor_total=Decimal(str(valor or 0)),
                unidades_total=Decimal(str(unidades or 0)),
            )
            for bid, code, name, warehouse_type, unidades, valor in rows
        ]
