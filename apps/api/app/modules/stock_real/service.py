"""
Service de stock por ubicación (Fase 2).

Tres responsabilidades:
1. ``list_stock_real``: consulta granular con filtros.
2. ``upsert_stock_real``: upsert por (producto, ubicación).
3. ``distribucion_por_sku``: grilla multibodega para el spec §4.1
   (formato "Bodega X: 140 (P-01/E-02)").
4. ``bajo_minimo``: alerta de productos por debajo del mínimo en una
   bodega concreta.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from app.core.errors import (
    ProductNotFoundError,
    UbicacionNotFoundError,
    WarehouseNotFoundError,
)
from app.db.session import SQLiteDatabase, utcnow
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


def _format_ubicacion_code(pasillo: int, estanteria: int, altura: int) -> str:
    """Formato compacto del spec: P-01/E-02/A-01."""
    return f"P-{pasillo:02d}/E-{estanteria:02d}/A-{altura:02d}"


class StockRealService:
    def __init__(
        self,
        db: SQLiteDatabase,
        stock_real_repository: StockRealRepository,
        ubicacion_repository: UbicacionRepository,
        warehouse_repository: WarehouseRepository,
        product_repository: ProductRepository,
    ) -> None:
        self._db = db
        self._stock_real = stock_real_repository
        self._ubicaciones = ubicacion_repository
        self._warehouses = warehouse_repository
        self._products = product_repository

    # --- CRUD granular ---

    def list_stock_real(
        self,
        *,
        warehouse_id: uuid.UUID | None = None,
        product_id: uuid.UUID | None = None,
    ) -> list[StockRealItem]:
        if warehouse_id is not None and self._warehouses.get_by_id(warehouse_id) is None:
            raise WarehouseNotFoundError(str(warehouse_id))
        if product_id is not None and self._products.get_by_id(product_id) is None:
            raise ProductNotFoundError(str(product_id))

        rows = self._stock_real.list(
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

    def upsert_stock_real(
        self,
        id_producto: uuid.UUID,
        id_ubicacion: uuid.UUID,
        cantidad: Decimal,
    ) -> StockRealItem:
        if self._products.get_by_id(id_producto) is None:
            raise ProductNotFoundError(str(id_producto))
        if self._ubicaciones.get_by_id(id_ubicacion) is None:
            raise UbicacionNotFoundError(str(id_ubicacion))

        now = utcnow()
        self._stock_real.upsert(id_producto, id_ubicacion, cantidad, now)
        return StockRealItem(
            id_producto=id_producto,
            id_ubicacion=id_ubicacion,
            cantidad=cantidad,
            updated_at=now,
        )

    # --- Grilla multibodega (spec §4.1) ---

    def distribucion_por_sku(self, sku: str) -> DistribucionMultibodegaResponse:
        product = self._products.get_by_sku(sku.strip().upper())
        if product is None:
            raise ProductNotFoundError(sku)

        # Nivel 1: stock agregado por bodega
        stock_rows = self._db.query_all(
            """
            SELECT
                sl.warehouse_id, sl.quantity, sl.min_quantity,
                w.code, w.name, w.warehouse_type
            FROM stock_levels sl
            JOIN warehouses w ON w.id = sl.warehouse_id
            WHERE sl.product_id = ?
            ORDER BY w.code
            """,
            (str(product.id),),
        )

        # Nivel 2: ubicaciones del producto
        ubic_rows = self._db.query_all(
            """
            SELECT
                u.id, u.id_bodega, u.pasillo, u.estanteria, u.altura, sr.cantidad
            FROM inventario_stock_real sr
            JOIN ubicaciones_estanteria u ON u.id = sr.id_ubicacion
            WHERE sr.id_producto = ?
            ORDER BY u.id_bodega, u.pasillo, u.estanteria, u.altura
            """,
            (str(product.id),),
        )
        ubicaciones_por_bodega: dict[str, list[UbicacionDistribucionItem]] = {}
        for urow in ubic_rows:
            item = UbicacionDistribucionItem(
                id_ubicacion=uuid.UUID(urow["id"]),
                pasillo=int(urow["pasillo"]),
                estanteria=int(urow["estanteria"]),
                altura=int(urow["altura"]),
                cantidad=Decimal(str(urow["cantidad"])),
                code=_format_ubicacion_code(
                    int(urow["pasillo"]),
                    int(urow["estanteria"]),
                    int(urow["altura"]),
                ),
            )
            ubicaciones_por_bodega.setdefault(str(urow["id_bodega"]), []).append(item)

        bodegas: list[DistribucionBodegaItem] = []
        total_global = Decimal("0")
        for srow in stock_rows:
            quantity = Decimal(str(srow["quantity"]))
            min_quantity = Decimal(str(srow["min_quantity"]))
            total_global += quantity

            if quantity <= 0:
                estado = "critico"
            elif min_quantity > 0 and quantity <= min_quantity:
                estado = "alerta"
            else:
                estado = "normal"

            bodegas.append(
                DistribucionBodegaItem(
                    bodega_id=uuid.UUID(srow["warehouse_id"]),
                    bodega_code=srow["code"],
                    bodega_name=srow["name"],
                    bodega_type=srow["warehouse_type"],
                    total_quantity=quantity,
                    min_quantity=min_quantity,
                    estado=estado,
                    ubicaciones=ubicaciones_por_bodega.get(
                        str(srow["warehouse_id"]), []
                    ),
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

    def bajo_minimo(
        self, bodega_id: uuid.UUID | None = None
    ) -> list[BajoMinimoItem]:
        if bodega_id is not None and self._warehouses.get_by_id(bodega_id) is None:
            raise WarehouseNotFoundError(str(bodega_id))

        clauses = ["sl.min_quantity > 0", "sl.quantity <= sl.min_quantity"]
        params: list[object] = []
        if bodega_id is not None:
            clauses.append("sl.warehouse_id = ?")
            params.append(str(bodega_id))
        where = " AND ".join(clauses)

        rows = self._db.query_all(
            f"""
            SELECT
                sl.warehouse_id, sl.product_id, sl.quantity, sl.min_quantity, sl.updated_at,
                w.code, w.name,
                p.sku, p.name AS product_name
            FROM stock_levels sl
            JOIN warehouses w ON w.id = sl.warehouse_id
            JOIN products p ON p.id = sl.product_id
            WHERE {where}
            ORDER BY (sl.quantity - sl.min_quantity) ASC, w.code, p.sku
            """,
            tuple(params),
        )
        return [
            BajoMinimoItem(
                bodega_id=uuid.UUID(r["warehouse_id"]),
                bodega_code=r["code"],
                bodega_name=r["name"],
                product_id=uuid.UUID(r["product_id"]),
                product_sku=r["sku"],
                product_name=r["product_name"],
                quantity=Decimal(str(r["quantity"])),
                min_quantity=Decimal(str(r["min_quantity"])),
                updated_at=datetime.fromisoformat(r["updated_at"]),
            )
            for r in rows
        ]
