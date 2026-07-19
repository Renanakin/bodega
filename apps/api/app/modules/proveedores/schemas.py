"""Schemas Pydantic para proveedores (Fase 8).

Capa: API (entrada/salida HTTP). Validacion estructural via Pydantic.
Reglas de negocio (unicidad de nombre/RUT, soft delete) viven en
``ProveedorService``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints


# Limites reutilizables: nombre (display) y RUT chileno (8 digitos + DV, opcional).
NombreStr = Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)]
RutStr = Annotated[str, StringConstraints(min_length=1, max_length=20, strip_whitespace=True)]
EmailOpt = Annotated[EmailStr | None, Field(default=None)]


class ProveedorCreate(BaseModel):
    """Payload de creacion.

    ``nombre`` es obligatorio y unico (case-insensitive). ``rut`` es opcional
    pero, si viene, debe ser unico. ``lead_time_dias`` default 7 (una semana).
    """

    nombre: NombreStr
    rut: RutStr | None = None
    email: EmailOpt = None
    telefono: Annotated[str, StringConstraints(max_length=30)] | None = None
    direccion: Annotated[str, StringConstraints(max_length=300)] | None = None
    contacto_nombre: Annotated[str, StringConstraints(max_length=150)] | None = None
    lead_time_dias: int = Field(default=7, ge=0, le=365)
    activo: bool = True


class ProveedorUpdate(BaseModel):
    """PATCH parcial — todos los campos opcionales."""

    nombre: NombreStr | None = Field(default=None, min_length=1, max_length=200)
    rut: RutStr | None = Field(default=None, min_length=1, max_length=20)
    email: EmailStr | None = None
    telefono: Annotated[str, StringConstraints(max_length=30)] | None = None
    direccion: Annotated[str, StringConstraints(max_length=300)] | None = None
    contacto_nombre: Annotated[str, StringConstraints(max_length=150)] | None = None
    lead_time_dias: int | None = Field(default=None, ge=0, le=365)
    activo: bool | None = None


class ProveedorResponse(BaseModel):
    """Vista expuesta al frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    rut: str | None
    email: str | None
    telefono: str | None
    direccion: str | None
    contacto_nombre: str | None
    lead_time_dias: int
    activo: bool
    created_at: datetime
    updated_at: datetime | None = None
