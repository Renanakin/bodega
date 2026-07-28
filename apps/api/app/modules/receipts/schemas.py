"""Schemas Pydantic para recepciones (FIX FASE POST-E2E)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


# Limites
CodigoStr = Annotated[str, StringConstraints(min_length=1, max_length=40, strip_whitespace=True)]
DocNumStr = Annotated[str, StringConstraints(min_length=1, max_length=80, strip_whitespace=True)]


class ReceiptLineCreate(BaseModel):
    """Una linea de recepcion: 1 SKU + cantidad + precio unitario."""

    id_producto: uuid.UUID
    cantidad: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    precio_unitario: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)


class ReceiptLineResponse(BaseModel):
    id: uuid.UUID
    id_receipt: uuid.UUID
    id_producto: uuid.UUID
    cantidad: Decimal
    precio_unitario: Decimal
    movement_id: uuid.UUID | None = None
    # Campos enriched
    product_sku: str | None = None
    product_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ReceiptCreate(BaseModel):
    """Payload para crear una recepcion (estado pending)."""

    id_bodega_destino: uuid.UUID
    id_proveedor: uuid.UUID | None = None
    id_orden_compra: uuid.UUID | None = None
    numero_documento: DocNumStr | None = None
    notas: Annotated[str, StringConstraints(max_length=500)] | None = None
    lineas: list[ReceiptLineCreate] = Field(min_length=1, max_length=200)


class ReceiptResponse(BaseModel):
    id: uuid.UUID
    codigo: str
    id_bodega_destino: uuid.UUID
    id_proveedor: uuid.UUID | None = None
    id_orden_compra: uuid.UUID | None = None
    numero_documento: str | None = None
    estado: str
    notas: str | None = None
    created_by: uuid.UUID
    created_at: datetime
    confirmed_at: datetime | None = None
    confirmed_by: uuid.UUID | None = None

    # Enriched
    bodega_codigo: str | None = None
    bodega_nombre: str | None = None
    proveedor_nombre: str | None = None
    orden_compra_codigo: str | None = None
    total_cantidad: Decimal | None = None
    total_monto: Decimal | None = None
    lineas: list[ReceiptLineResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ReceiptListResponse(BaseModel):
    """Wrapper de respuesta para listar recepciones (compat con paginacion simple)."""

    items: list[ReceiptResponse]
    total: int
