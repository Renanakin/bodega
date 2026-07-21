"""Schemas Pydantic para el snapshot ejecutivo (Fase 8).

Tipos:
- ``KpiSnapshot``: agregados globales (1 nivel).
- ``TopProducto``: item de un ranking (top 5 mas movidos / menos movidos).
- ``ValorPorBodega``: desglose del valor del stock por bodega.
- ``EjecutivoSnapshot``: payload completo de ``GET /reports/ejecutivo``.

Los schemas son DTOs de salida — no hay input mutante en este endpoint
(read-only). El cliente puede generar el PDF desde ``EjecutivoSnapshot``
usando jsPDF (sin pasar por el server).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TopProducto(BaseModel):
    """Item de ranking (mas / menos movido)."""

    producto_id: uuid.UUID
    sku: str
    nombre: str
    unidades_movidas: Decimal = Field(
        description="Suma absoluta de quantities en inventory_movements (IN-OUT)."
    )
    movimientos_count: int = Field(
        description="Cantidad de movimientos de inventario (cualquier tipo)."
    )


class ValorPorBodega(BaseModel):
    """Valor del stock (CLP) por bodega."""

    bodega_id: uuid.UUID
    bodega_code: str
    bodega_name: str
    bodega_type: str
    valor_total: Decimal
    unidades_total: Decimal


class EjecutivoSnapshot(BaseModel):
    """Snapshot ejecutivo completo. Se regenera en cada GET.

    El cliente puede decidir cachear (e.g. SWR/React Query) o re-preguntar
    cada vez. El calculo se hace en SQL con agregaciones, NO itera filas en
    Python (limpieza: 238 → 238 tests OK).
    """

    generado_en: datetime
    stock_total_activo_valorizado: Decimal = Field(
        description="Suma de (quantity * precio_costo) sobre stock_levels con quantity > 0."
    )
    alertas_criticas_count: int = Field(
        description="SKUs bajo minimo en cualquier bodega (min > 0 AND quantity <= min)."
    )
    transferencias_en_ruta_count: int = Field(
        description="Solicitudes en estado in_transit o partially_received."
    )
    solicitudes_por_estado: dict[str, int] = Field(
        description="Conteo de solicitudes agrupadas por estado (ej. pendiente: 5)."
    )
    top_productos_mas_movidos: list[TopProducto]
    top_productos_menos_movidos: list[TopProducto]
    valor_por_bodega: list[ValorPorBodega]
    total_productos_activos: int = Field(description="Cantidad de productos con is_active=True.")
    total_bodegas: int
    config: dict[str, int] = Field(
        default_factory=lambda: {"top_n": 5},
        description="Configuracion aplicada (e.g. top_n).",
    )


class ReporteInventarioItem(BaseModel):
    """Item de la grilla de inventario para export."""

    model_config = ConfigDict(from_attributes=True)

    bodega_id: uuid.UUID
    bodega_code: str
    bodega_name: str
    producto_id: uuid.UUID
    sku: str
    nombre: str
    quantity: Decimal
    min_quantity: Decimal
    valorizado: Decimal
