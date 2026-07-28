"""Schemas Pydantic para ordenes de compra (Fase 6).

Separados del router para mantener clean architecture.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class DetalleOCCreate(BaseModel):
    id_producto: uuid.UUID
    cantidad_pedida: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    costo_unitario_pactado: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class OCCreate(BaseModel):
    id_bodega_principal: uuid.UUID
    id_supervisor: uuid.UUID
    proveedor_nombre: str = Field(min_length=1, max_length=200)
    proveedor_contacto: str | None = Field(default=None, max_length=200)
    notas: str | None = Field(default=None, max_length=1000)
    lineas: list[DetalleOCCreate] = Field(min_length=1)


class OCUpdate(BaseModel):
    """PATCH: solo actualizable si estado=Borrador."""

    id_supervisor: uuid.UUID | None = None
    proveedor_nombre: str | None = Field(default=None, min_length=1, max_length=200)
    proveedor_contacto: str | None = Field(default=None, max_length=200)
    notas: str | None = Field(default=None, max_length=1000)


class DetalleOCResponse(BaseModel):
    id_orden_compra: uuid.UUID
    id_producto: uuid.UUID
    product_sku: str | None = None
    product_name: str | None = None
    cantidad_pedida: Decimal
    costo_unitario_pactado: Decimal


class OCResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    codigo: str
    id_bodega_principal: uuid.UUID
    id_supervisor: uuid.UUID
    supervisor_nombre: str | None = None
    supervisor_email: str | None = None
    proveedor_nombre: str
    proveedor_contacto: str | None
    estado: str
    total_estimado: Decimal
    notas: str | None
    motivo_rechazo: str | None
    email_enviado_at: datetime | None
    aprobado_at: datetime | None
    comprado_at: datetime | None
    created_at: datetime
    updated_at: datetime | None
    # FIX (FASE POST-E2E): expone el token solo si el caller lo pide
    # explicitamente via ?include_token=true. None por default.
    last_approval_token: str | None = None
    detalles: list[DetalleOCResponse] = Field(default_factory=list)


class OCListResponse(BaseModel):
    """Wrapper de paginacion cursor-based (P0 roadmap Big-O).

    Devuelve items + next_cursor + has_more. Si el cliente NO manda
    `cursor`, este endpoint devuelve la lista plana (compat backwards).
    """
    items: list[OCResponse]
    next_cursor: str | None = None
    has_more: bool = False


class RechazoPayload(BaseModel):
    motivo: str = Field(min_length=1, max_length=500)


class EnviarCorreoResponse(BaseModel):
    oc: OCResponse
    approval_token: str  # solo para testing E2E; en prod NO se devuelve
    outbox_id: uuid.UUID


class CompraRequest(BaseModel):
    """Body opcional para `marcar_comprada` (placeholder)."""

    notas: str | None = Field(default=None, max_length=500)
