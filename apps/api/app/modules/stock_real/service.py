"""
Service de stock por ubicación (async).

Tres responsabilidades:
1. ``list_stock_real``: consulta granular con filtros.
2. ``upsert_stock_real``: upsert por (producto, ubicación).
3. ``distribucion_por_sku``: grilla multibodega para el spec §4.1.
4. ``bajo_minimo``: alerta de productos por debajo del mínimo en una
   bodega concreta.

Convenciones:
- Métodos ``async def``.
- ``await session.commit()`` + ``refresh()`` después de mutaciones.
- Para las queries JOIN que el spec necesita (``stock_levels`` +
  ``warehouses``), uso SQLAlchemy ORM con join en vez de SQL crudo.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.core.errors import (
    ProductNotFoundError,
    UbicacionNotFoundError,
    WarehouseNotFoundError,
)
from app.db.models.inventory import StockLevel
from app.db.models.products import Product
from app.db.models.stock_real import InventarioStockReal
from app.db.models.ubicaciones import UbicacionEstanteria
from app.db.models.warehouses import Warehouse
from app.modules.products.repository import ProductRepository
from app.modules.stock_real.repository import StockRealRepository
from app.modules.stock_real.schemas import (
    BajoMinimoItem,
    DistribucionBodegaItem,
    DistribucionMultibodegaResponse,
    StockRealItem,
    UbicacionDistribucionItem,
)
from app.modules.ubicaciones.repository import UbicacionRepository
from app.modules.warehouses.repository import WarehouseRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _format_ubicacion_code(pasillo: int, estanteria: int, altura: int) -> str:
    """Formato compacto del spec: P-01/E-02/A-01."""
    return f"P-{pasillo:02d}/E-{estanteria:02d}/A-{altura:02d}"


def _now_utc() -> datetime:
    return datetime.now(UTC)


class StockRealService:
    def __init__(
        self,
        session: AsyncSession,
        stock_real_repository: StockRealRepository | None = None,
        ubicacion_repository: UbicacionRepository | None = None,
        warehouse_repository: WarehouseRepository | None = None,
        product_repository: ProductRepository | None = None,
    ) -> None:
        self._session = session
        self._stock_real = stock_real_repository or StockRealRepository(session)
        self._ubicaciones = ubicacion_repository or UbicacionRepository(session)
        self._warehouses = warehouse_repository or WarehouseRepository(session)
        self._products = product_repository or ProductRepository(session)

    # --- CRUD granular ---

    async def list_stock_real(
        self,
        *,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[StockRealItem]:
        if warehouse_id is not None and await self._warehouses.get_by_id(warehouse_id) is None:
            raise WarehouseNotFoundError(str(warehouse_id))
        if product_id is not None and await self._products.get_by_id(product_id) is None:
            raise ProductNotFoundError(str(product_id))

        rows = await self._stock_real.list(
            warehouse_id=warehouse_id, product_id=product_id
        )
        return [
            StockRealItem(
                id_producto=r.id_producto,
                id_ubicacion=r.id_ubicacion,
                cantidad=r.cantidad,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    async def upsert_stock_real(
        self,
        id_producto: uuid.UUID,
        id_ubicacion: uuid.UUID,
        cantidad: Decimal,
    ) -> StockRealItem:
        if await self._products.get_by_id(id_producto) is None:
            raise ProductNotFoundError(str(id_producto))
        if await self._ubicaciones.get_by_id(id_ubicacion) is None:
            raise UbicacionNotFoundError(str(id_ubicacion))

        await self._stock_real.upsert(id_producto, id_ubicacion, cantidad)
        await self._session.commit()
        # Leer el row final para obtener el updated_at que la BD le asignó.
        final = await self._stock_real.get(id_producto, id_ubicacion)
        if final is None:
            raise UbicacionNotFoundError(str(id_ubicacion))
        return StockRealItem(
            id_producto=id_producto,
            id_ubicacion=id_ubicacion,
            cantidad=final.cantidad,
            updated_at=final.updated_at,
        )

    # --- Grilla multibodega (spec §4.1) ---

    async def distribucion_por_sku(self, sku: str) -> DistribucionMultibodegaResponse:
        product = await self._products.get_by_sku(sku.strip().upper())
        if product is None:
            raise ProductNotFoundError(sku)

        # Nivel 1: stock agregado por bodega (JOIN stock_levels + warehouses).
        sl_stmt = (
            select(StockLevel, Warehouse)
            .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
            .where(StockLevel.product_id == product.id)
            .order_by(Warehouse.code)
        )
        sl_rows = (await self._session.execute(sl_stmt)).all()

        # Nivel 2: ubicaciones del producto (JOIN inventario_stock_real + ubicaciones).
        ub_stmt = (
            select(InventarioStockReal, UbicacionEstanteria)
            .join(
                UbicacionEstanteria,
                UbicacionEstanteria.id == InventarioStockReal.id_ubicacion,
            )
            .where(InventarioStockReal.id_producto == product.id)
            .order_by(
                UbicacionEstanteria.id_bodega,
                UbicacionEstanteria.pasillo,
                UbicacionEstanteria.estanteria,
                UbicacionEstanteria.altura,
            )
        )
        ub_rows = (await self._session.execute(ub_stmt)).all()

        ubicaciones_por_bodega: dict[str, list[UbicacionDistribucionItem]] = {}
        for sr, u in ub_rows:
            item = UbicacionDistribucionItem(
                id_ubicacion=u.id,
                pasillo=u.pasillo,
                estanteria=u.estanteria,
                altura=u.altura,
                cantidad=sr.cantidad,
                code=_format_ubicacion_code(u.pasillo, u.estanteria, u.altura),
            )
            ubicaciones_por_bodega.setdefault(str(u.id_bodega), []).append(item)

        bodegas: list[DistribucionBodegaItem] = []
        total_global = Decimal("0")
        for sl, w in sl_rows:
            quantity = sl.quantity
            min_quantity = sl.min_quantity
            total_global += quantity

            if quantity <= 0:
                estado = "critico"
            elif min_quantity > 0 and quantity <= min_quantity:
                estado = "alerta"
            else:
                estado = "normal"

            bodegas.append(
                DistribucionBodegaItem(
                    bodega_id=w.id,
                    bodega_code=w.code,
                    bodega_name=w.name,
                    bodega_type=w.warehouse_type,
                    total_quantity=quantity,
                    min_quantity=min_quantity,
                    estado=estado,
                    ubicaciones=ubicaciones_por_bodega.get(str(w.id), []),
                )
            )

        return DistribucionMultibodegaResponse(
            producto_id=product.id,
            sku=product.sku,
            name=product.name,
            precio_costo=product.precio_costo,
            precio_venta=product.precio_venta,
            total_global=total_global,
            bodegas=bodegas,
        )

    # --- Bajo mínimo ---

    async def bajo_minimo(
        self, bodega_id: uuid.UUID | None = None
    ) -> list[BajoMinimoItem]:
        if bodega_id is not None and await self._warehouses.get_by_id(bodega_id) is None:
            raise WarehouseNotFoundError(str(bodega_id))

        stmt = (
            select(StockLevel, Warehouse, Product)
            .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
            .join(Product, Product.id == StockLevel.product_id)
            .where(StockLevel.min_quantity > 0)
            .where(StockLevel.quantity <= StockLevel.min_quantity)
        )
        if bodega_id is not None:
            stmt = stmt.where(StockLevel.warehouse_id == bodega_id)
        stmt = stmt.order_by(
            (StockLevel.quantity - StockLevel.min_quantity).asc(),
            Warehouse.code,
            Product.sku,
        )
        rows = (await self._session.execute(stmt)).all()

        return [
            BajoMinimoItem(
                bodega_id=w.id,
                bodega_code=w.code,
                bodega_name=w.name,
                product_id=p.id,
                product_sku=p.sku,
                product_name=p.name,
                quantity=sl.quantity,
                min_quantity=sl.min_quantity,
                updated_at=sl.updated_at,
            )
            for sl, w, p in rows
        ]


__all__ = ["StockRealService"]
