from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class MovementType(StrEnum):
    IN = "in"
    OUT = "out"
    ADJUSTMENT_IN = "adjustment_in"
    ADJUSTMENT_OUT = "adjustment_out"


class InventoryMovementCreate(BaseModel):
    warehouse_id: UUID
    product_id: UUID
    movement_type: MovementType
    quantity: Quantity
    reference_type: str | None = Field(default=None, max_length=50)
    reference_id: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("reference_type", "reference_id", "notes")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class InventoryMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    warehouse_id: UUID
    warehouse_code: str
    product_id: UUID
    product_sku: str
    movement_type: MovementType
    quantity: Decimal
    reference_type: str | None
    reference_id: str | None
    notes: str | None
    created_at: datetime


class StockLevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    warehouse_id: UUID
    warehouse_code: str
    warehouse_name: str
    product_id: UUID
    product_sku: str
    product_name: str
    quantity: Decimal
    min_quantity: Decimal
    updated_at: datetime


class InventorySummaryResponse(BaseModel):
    warehouses: int
    products: int
    stock_records: int
    movements: int
    low_stock_alerts: int


# --- Fase 8: parametrizacion por bodega x producto ---

class StockParametersUpsert(BaseModel):
    """Payload para ``PUT /api/v1/inventory/parametros/{producto_id}/{bodega_id}`` (Fase 8).

    Reemplaza la tupla ``(min_quantity, max_quantity)`` de un ``stock_level``
    especifico. Si la fila no existe, se crea con ``quantity=0`` y los
    parametros dados.

    Restricciones de negocio (validadas tambien en el service):
    - ``stock_maximo`` debe ser ``>= stock_minimo``.
    - ``lead_time_dias`` debe ser ``>= 0``.
    - ``supplier_preferred_id`` (opcional) debe ser un proveedor activo
      (la validacion se hace en el service contra el modulo ``proveedores``).
    """

    stock_minimo: Decimal = Field(
        ge=Decimal("0"),
        description="Umbral bajo minimo (alerta).",
    )
    stock_maximo: Decimal = Field(
        ge=Decimal("0"),
        description="Umbral objetivo (reposicion).",
    )
    lead_time_dias: int = Field(ge=0, le=365, default=7)
    supplier_preferred_id: UUID | None = None


class StockParametersResponse(BaseModel):
    """Vista de los parametros de un (producto, bodega) especifico."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    warehouse_id: UUID
    warehouse_code: str | None = None
    product_id: UUID
    product_sku: str | None = None
    quantity: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None = None
    updated_at: datetime
