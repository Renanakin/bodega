from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=120)


class RefreshRequest(BaseModel):
    """C5.1: payload para POST /auth/refresh."""
    refresh_token: str = Field(min_length=10, max_length=500)


class AuthSessionResponse(BaseModel):
    """C5.1: respuesta de login + refresh.

    Antes solo tenia ``token`` + ``expires_at``. Ahora incluye
    ``refresh_token`` + ``refresh_expires_at`` para que el cliente
    pueda renovar el access token sin pedir credenciales de nuevo.
    """
    token: str
    refresh_token: str
    expires_at: datetime
    refresh_expires_at: datetime


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    full_name: str
    role: str
    is_active: bool
