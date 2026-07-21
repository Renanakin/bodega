"""
Schemas Pydantic para ubicaciones físicas (Fase 2).

Una ubicación = (id_bodega, pasillo, estanteria, altura) con UNIQUE
constraint y soft delete via ``is_active``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UbicacionCreate(BaseModel):
    pasillo: int = Field(ge=1, le=9999)
    estanteria: int = Field(ge=1, le=9999)
    altura: int = Field(ge=1, le=99)
    descripcion: str | None = Field(default=None, max_length=200)

    @field_validator("descripcion")
    @classmethod
    def normalize_descripcion(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class UbicacionUpdate(BaseModel):
    """PATCH parcial."""

    descripcion: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None

    @field_validator("descripcion")
    @classmethod
    def normalize_descripcion(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class UbicacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    id_bodega: UUID
    pasillo: int
    estanteria: int
    altura: int
    descripcion: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
