"""Schemas Pydantic para Supervisores (Fase 6).

Separados del router para que services/tests/frontend los puedan importar
sin arrastrar dependencias de FastAPI.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SupervisorCreate(BaseModel):
    """Payload de creación."""

    nombre: str = Field(min_length=1, max_length=150)
    email: EmailStr
    telefono: str | None = Field(default=None, max_length=30)
    cargo: str | None = Field(default=None, max_length=100)


class SupervisorUpdate(BaseModel):
    """Payload de actualización parcial (PATCH). Todos los campos opcionales."""

    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    telefono: str | None = Field(default=None, max_length=30)
    cargo: str | None = Field(default=None, max_length=100)
    activo: bool | None = None


class SupervisorResponse(BaseModel):
    """Vista expuesta al frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    email: str
    telefono: str | None
    cargo: str | None
    activo: bool
    created_at: datetime
    updated_at: datetime | None = None
