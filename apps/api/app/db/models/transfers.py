"""Modelo SQLAlchemy para transfers (legacy, deprecado en Fase 5 por solicitudes).

NOTA: NO usar `from __future__ import annotations` ni `relationship()` aquí.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from app.db.base import GUID, Base, created_at_column
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class TransferStatus(str, enum.Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class Transfer(Base):
    """Transferencia entre bodegas (DEPRECADO en Fase 5, reemplazado por solicitudes)."""

    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "received_quantity >= 0 AND received_quantity <= quantity", name="received_valid"
        ),
        Index("ix_transfers_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    from_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    status: Mapped[TransferStatus] = mapped_column(
        Enum(
            TransferStatus,
            name="transfer_status_enum",
            native_enum=False,
            length=30,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(String(30), nullable=True)
    notes: Mapped[str] = mapped_column(String(500), nullable=True)
    dispatch_notes: Mapped[str] = mapped_column(String(500), nullable=True)
    receive_notes: Mapped[str] = mapped_column(String(500), nullable=True)
    incident_type: Mapped[str] = mapped_column(String(30), nullable=True)
    incident_notes: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at = created_at_column()
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
