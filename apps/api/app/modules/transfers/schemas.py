from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Quantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class TransferCreate(BaseModel):
    from_warehouse_id: UUID
    to_warehouse_id: UUID
    product_id: UUID
    quantity: Quantity
    priority: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("priority", "notes")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    from_warehouse_id: UUID
    from_warehouse_code: str
    from_warehouse_name: str
    to_warehouse_id: UUID
    to_warehouse_code: str
    to_warehouse_name: str
    product_id: UUID
    product_sku: str
    product_name: str
    quantity: Decimal
    received_quantity: Decimal
    status: str
    priority: str | None
    notes: str | None
    dispatch_notes: str | None
    receive_notes: str | None
    incident_type: str | None
    incident_notes: str | None
    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    received_at: datetime | None


class TransferUpdate(BaseModel):
    quantity: Quantity
    priority: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("priority", "notes")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TransferDispatch(BaseModel):
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class TransferReceive(BaseModel):
    quantity: Quantity
    notes: str | None = Field(default=None, max_length=500)
    incident_type: str | None = Field(default=None, max_length=30)
    incident_notes: str | None = Field(default=None, max_length=500)

    @field_validator("notes", "incident_type", "incident_notes")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None
