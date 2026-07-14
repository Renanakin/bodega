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
