from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Price = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=150)
    unit: str = Field(min_length=1, max_length=20)
    # Extensión Fase 2 (todos opcionales en el create)
    codigo_barras: str | None = Field(default=None, max_length=100)
    precio_costo: Price | None = None
    precio_venta: Price | None = None
    id_categoria: UUID | None = None

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("codigo_barras")
    @classmethod
    def normalize_codigo_barras(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProductUpdate(BaseModel):
    """PATCH parcial — todos los campos opcionales.

    Para desvincular la categoría pasar explicitamente ``id_categoria: null``.
    """

    name: str | None = Field(default=None, min_length=1, max_length=150)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None
    codigo_barras: str | None = Field(default=None, max_length=100)
    precio_costo: Price | None = None
    precio_venta: Price | None = None
    id_categoria: UUID | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().lower()

    @field_validator("codigo_barras")
    @classmethod
    def normalize_codigo_barras(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    unit: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    codigo_barras: str | None = None
    precio_costo: Decimal = Decimal("0")
    precio_venta: Decimal = Decimal("0")
    id_categoria: UUID | None = None
