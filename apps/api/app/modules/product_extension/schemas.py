"""
Schemas Pydantic para el sub-recurso ``detalles_neumaticos`` (Fase 2).

Una relación 1:1 opt-in con ``products``. Un producto tiene 0 o 1
``DetalleNeumatico``; si no existe, el GET devuelve 404.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DetalleNeumaticoUpsert(BaseModel):
    """Payload para PUT (upsert)."""

    ancho: int = Field(ge=1, le=999)
    perfil: int = Field(ge=1, le=999)
    aro: int = Field(ge=1, le=99)
    indice_carga: int | None = Field(default=None, ge=0, le=200)
    indice_velocidad: str | None = Field(default=None, max_length=5)
    dot: str | None = Field(default=None, max_length=20)


class DetalleNeumaticoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    producto_id: UUID
    ancho: int
    perfil: int
    aro: int
    indice_carga: int | None
    indice_velocidad: str | None
    dot: str | None
