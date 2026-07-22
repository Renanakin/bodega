"""
Dataclass records (DTOs) usados por la capa de repositorios legacy.

Estos records son estructuras de datos puras (sin logica) que
representan filas de las tablas. Se usan en warehouses, products,
stock, transfers, auth.

R5: nombres auto-documentados (el nombre del record describe la
entidad que representa).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(slots=True)
class WarehouseRecord:
    id: UUID
    code: str
    name: str
    warehouse_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ProductRecord:
    id: UUID
    sku: str
    name: str
    unit: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # --- Extension Fase 2 (ADR-0001 / aterrizaje 3.2) ---
    codigo_barras: str | None = None
    precio_costo: Decimal = Decimal("0")
    precio_venta: Decimal = Decimal("0")
    id_categoria: UUID | None = None


@dataclass(slots=True)
class StockLevelRecord:
    id: UUID
    warehouse_id: UUID
    product_id: UUID
    quantity: Decimal
    min_quantity: Decimal
    updated_at: datetime
    max_quantity: Decimal | None = None


@dataclass(slots=True)
class InventoryMovementRecord:
    id: UUID
    warehouse_id: UUID
    product_id: UUID
    movement_type: str
    quantity: Decimal
    reference_type: str | None
    reference_id: str | None
    notes: str | None
    created_at: datetime


@dataclass(slots=True)
class TransferRecord:
    id: UUID
    code: str
    from_warehouse_id: UUID
    to_warehouse_id: UUID
    product_id: UUID
    quantity: Decimal
    received_quantity: Decimal
    status: str
    priority: str | None
    notes: str | None
    dispatch_notes: str | None
    receive_notes: str | None
    incident_type: str | None
    incident_notes: str | None
    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    received_at: datetime | None


@dataclass(slots=True)
class UserRecord:
    id: UUID
    username: str
    full_name: str
    role: str
    password_hash: str
    is_active: bool
    created_at: datetime


@dataclass(slots=True)
class SessionRecord:
    id: UUID
    user_id: UUID
    token: str
    refresh_token: str
    expires_at: datetime
    refresh_expires_at: datetime
    created_at: datetime


@dataclass(slots=True)
class AuditLogRecord:
    id: UUID
    user_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    detail: str | None
    created_at: datetime
