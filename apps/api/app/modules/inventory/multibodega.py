"""
Vista de stock multibodega (Fase 6).

Implementa el panel "Grilla Multibodega" del spec §4.1:
buscador SKU -> muestra distribucion real con formato
"Bodega X: 140 (P-01/E-02)".
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.inventory import StockLevel
from app.db.models.products import Product
from app.db.models.ubicaciones import UbicacionEstanteria
from app.db.models.warehouses import Warehouse


log = get_logger(__name__)


@dataclass(slots=True)
class DistribucionPorBodega:
    bodega_id: uuid.UUID
    bodega_code: str
    bodega_name: str
    bodega_type: str
    total_quantity: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
    estado: str  # "normal" | "alerta" | "critico"
    ubicaciones: list[dict]  # [{"pasillo": 1, "estanteria": 2, "altura": 1, "cantidad": 50}]


@dataclass(slots=True)
class DistribucionMultibodega:
    """Distribucion de un producto en todas las bodegas."""

    producto_id: uuid.UUID
    sku: str
    name: str
    precio_costo: Decimal
    precio_venta: Decimal
    total_global: Decimal
    bodegas: list[DistribucionPorBodega]


class StockMultibodegaService:
    """Vista agregada de stock por producto en todas las bodegas."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def distribucion_por_sku(self, sku: str) -> DistribucionMultibodega | None:
        """Devuelve la distribucion de un producto por bodega.

        Formato: {bodega_code: quantity, bodega_code: {ubicaciones: [...]}}.
        """
        prod_stmt = select(Product).where(Product.sku == sku.strip().upper())
        producto = (await self._session.execute(prod_stmt)).scalar_one_or_none()
        if producto is None:
            return None

        # Stock levels por bodega
        stock_stmt = (
            select(StockLevel, Warehouse)
            .join(Warehouse, StockLevel.warehouse_id == Warehouse.id)
            .where(StockLevel.product_id == producto.id)
            .order_by(Warehouse.code)
        )
        stock_rows = list((await self._session.execute(stock_stmt)).all())

        # Ubicaciones del producto
        ub_stmt = (
            select(InventarioStockReal := UbicacionEstanteria, UbicacionEstanteria, StockLevel)  # type: ignore[misc]
            .join(StockLevel, UbicacionEstanteria.id_bodega == StockLevel.warehouse_id)
            .where(StockLevel.product_id == producto.id)
        )
        # Nota: para Fase 6+, cuando se llene inventario_stock_real, esta query devolvera datos.

        bodegas_view = []
        total_global = Decimal("0")
        for stock, wh in stock_rows:
            # Estado segun min/max
            if stock.quantity <= 0:
                estado = "critico"
            elif stock.min_quantity > 0 and stock.quantity <= stock.min_quantity:
                estado = "alerta"
            else:
                estado = "normal"
            bodegas_view.append(
                DistribucionPorBodega(
                    bodega_id=wh.id,
                    bodega_code=wh.code,
                    bodega_name=wh.name,
                    bodega_type=wh.warehouse_type,
                    total_quantity=stock.quantity,
                    min_quantity=stock.min_quantity,
                    max_quantity=stock.max_quantity,
                    estado=estado,
                    ubicaciones=[],  # Se llenara cuando inventario_stock_real se use (Fase 6+)
                )
            )
            total_global += stock.quantity

        return DistribucionMultibodega(
            producto_id=producto.id,
            sku=producto.sku,
            name=producto.name,
            precio_costo=producto.precio_costo,
            precio_venta=producto.precio_venta,
            total_global=total_global,
            bodegas=bodegas_view,
        )

    async def resumen_bodegas(self) -> list[dict]:
        """Devuelve resumen de stock por bodega (para KPIs del dashboard)."""
        # Traer todas las bodegas y todos los stocks en 2 queries
        # (no en N+1). Luego agregar en Python.
        wh_stmt = (
            select(Warehouse)
            .order_by(Warehouse.warehouse_type, Warehouse.code)
        )
        warehouses = list((await self._session.execute(wh_stmt)).scalars().all())
        if not warehouses:
            return []
        # 1 sola query para todo el stock, agrupamos en Python por warehouse_id.
        wh_ids = [wh.id for wh in warehouses]
        stock_stmt = select(StockLevel).where(StockLevel.warehouse_id.in_(wh_ids))
        all_stocks = list((await self._session.execute(stock_stmt)).scalars().all())
        by_wh: dict = {}
        for s in all_stocks:
            bucket = by_wh.setdefault(
                s.warehouse_id,
                {"_stocks": [], "_total": Decimal("0"), "_alertas": 0, "_criticos": 0},
            )
            bucket["_stocks"].append(s)
            bucket["_total"] += s.quantity
            if s.min_quantity > 0 and s.quantity <= s.min_quantity:
                bucket["_alertas"] += 1
            if s.quantity <= 0:
                bucket["_criticos"] += 1
        result = []
        for wh in warehouses:
            bucket = by_wh.get(wh.id, {})
            result.append({
                "id": wh.id,
                "code": wh.code,
                "name": wh.name,
                "type": wh.warehouse_type,
                "total_quantity": bucket.get("_total", Decimal("0")),
                "skus_count": len(bucket.get("_stocks", [])),
                "alertas_count": bucket.get("_alertas", 0),
                "criticos_count": bucket.get("_criticos", 0),
                "is_active": wh.is_active,
            })
        return result
