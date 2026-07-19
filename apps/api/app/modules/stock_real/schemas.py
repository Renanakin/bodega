"""
Schemas Pydantic para el módulo de stock por ubicación (Fase 2).

Tres "vistas" del mismo dominio:
1. ``StockRealItem``: fila granular de ``inventario_stock_real`` (por
   producto + ubicación).
2. ``DistribucionBodegaItem`` + ``DistribucionMultibodegaResponse``:
   grilla multibodega que consume el frontend
   ``MultibodegaGrid`` (formato spec §4.1).
3. ``BajoMinimoItem``: alerta para el dashboard / bandeja.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StockRealItem(BaseModel):
    """Fila de stock físico (producto + ubicación)."""

    id_producto: UUID
    id_ubicacion: UUID
    cantidad: Decimal
    updated_at: datetime


class StockRealUpsert(BaseModel):
    """Payload para POST /inventario/real."""

    id_producto: UUID
    id_ubicacion: UUID
    cantidad: Decimal = Field(ge=0, max_digits=14, decimal_places=2)

    @field_validator("cantidad")
    @classmethod
    def normalize_cantidad(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("cantidad no puede ser negativa")
        return value


# --- Distribución multibodega (grilla del spec §4.1) ---


class UbicacionDistribucionItem(BaseModel):
    """Una ubicación concreta donde está el producto."""

    id_ubicacion: UUID
    pasillo: int
    estanteria: int
    altura: int
    cantidad: Decimal
    code: str  # "P-01/E-02/A-01"


class DistribucionBodegaItem(BaseModel):
    """Stock agregado por bodega con sus ubicaciones."""

    bodega_id: UUID
    bodega_code: str
    bodega_name: str
    bodega_type: str
    total_quantity: Decimal
    min_quantity: Decimal
    estado: str  # "normal" | "alerta" | "critico"
    ubicaciones: list[UbicacionDistribucionItem]


class DistribucionMultibodegaResponse(BaseModel):
    """Respuesta de ``GET /inventario/real/distribucion?sku=...``."""

    producto_id: UUID
    sku: str
    name: str
    precio_costo: Decimal
    precio_venta: Decimal
    total_global: Decimal
    bodegas: list[DistribucionBodegaItem]


# --- Bajo mínimo ---


class BajoMinimoItem(BaseModel):
    """Producto bajo mínimo en una bodega concreta."""

    bodega_id: UUID
    bodega_code: str
    bodega_name: str
    product_id: UUID
    product_sku: str
    product_name: str
    quantity: Decimal
    min_quantity: Decimal
    updated_at: datetime
