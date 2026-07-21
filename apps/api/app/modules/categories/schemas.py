"""
Schemas Pydantic para categorías (Fase 2).

Capa: API (entrada/salida HTTP). Validación estructural via Pydantic.
Reglas de negocio viven en ``CategoryService``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=500)
    parent_id: UUID | None = None

    @field_validator("nombre")
    @classmethod
    def normalize_nombre(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("nombre no puede ser vacio")
        return cleaned

    @field_validator("descripcion")
    @classmethod
    def normalize_descripcion(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CategoryUpdate(BaseModel):
    """PATCH parcial — todos los campos opcionales."""

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=500)
    parent_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("nombre")
    @classmethod
    def normalize_nombre(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("nombre no puede ser vacio")
        return cleaned

    @field_validator("descripcion")
    @classmethod
    def normalize_descripcion(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nombre: str
    descripcion: str | None
    parent_id: UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryNode(BaseModel):
    """Nodo del arbol de categorias (Fase 8).

    Es una vista recursiva: cada nodo incluye sus hijos como ``CategoryNode``
    anidados. Se calcula server-side en una sola query (CTE recursivo o
    carga + agrupamiento en memoria) para evitar N+1 en el front.
    """

    id: UUID
    nombre: str
    descripcion: str | None
    parent_id: UUID | None
    is_active: bool
    # Conteos utiles para la UI (no se exponen en GET flat).
    subcategorias_count: int = 0
    productos_count: int = 0
    # Hijos recursivos.
    children: list[CategoryNode] = []


# Habilita la recursion Pydantic (CategoryNode.children -> CategoryNode).
CategoryNode.model_rebuild()
