from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    warehouse_type: str = Field(min_length=1, max_length=30)
    # ADR-0002: solo los boxes (warehouse_type='mecanico_box') requieren
    # parent_warehouse_id NOT NULL. principal/auxiliar deben traerlo None.
    parent_warehouse_id: UUID | None = Field(
        default=None,
        description=(
            "Bodega padre. Requerida solo para warehouse_type='mecanico_box'."
        ),
    )
    is_active: bool = Field(
        default=True,
        description="Estado activo/inactivo. Default true al crear.",
    )

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("warehouse_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return value.strip().lower()


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    warehouse_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
