"""Schemas Pydantic para notificaciones in-app (Fase 8)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificacionResponse(BaseModel):
    """Notificacion expuesta al frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    tipo: str
    titulo: str
    mensaje: str | None
    payload: str | None = Field(
        default=None,
        description="JSON serializado (string) con contexto: id de la OC, "
        "id de la solicitud, etc.",
    )
    leida: bool
    created_at: datetime
    read_at: datetime | None


class NotificacionCount(BaseModel):
    """Conteo simple para el badge de la campanita."""

    total: int
    no_leidas: int
