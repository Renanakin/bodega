"""Modelos SQLAlchemy para solicitudes_recarga (N productos).

ADR-0003: Reemplaza transfers (1 producto) por solicitudes (N productos).
ADR-0002: Regla CHECK: origen=auxiliar, destino=principal.

Reglas de dominio:
- REG-001: mecanico_box NO puede ser origen de una solicitud.
- REG-002: mecanico_box NO puede ser destino de una solicitud.
- REG-003: principal NO puede ser origen de una solicitud.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from app.db.base import GUID, Base, created_at_column
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class SolicitudEstado(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    IN_TRANSIT = "in_transit"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SolicitudRecarga(Base):
    """Solicitud de recarga interna: N productos desde bodega auxiliar hacia principal."""

    __tablename__ = "solicitudes_recarga"
    __table_args__ = (
        Index("ix_solicitudes_estado_created_at", "estado", "created_at"),
        # Reglas de dominio (ADR-0002). En SQLite no se puede poner subqueries
        # en CHECK, por lo que los checks que dependen del warehouse_type
        # (origen ∈ {auxiliar, mecanico_box}, destino = principal) viven en
        # el service via `SolicitudService._validate_direction`. Aqui solo
        # agregamos el check de origen != destino que SI es portable.
        CheckConstraint(
            "id_bodega_origen <> id_bodega_destino",
            name="ck_solicitudes_origen_distinto_destino",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    id_bodega_origen: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    id_bodega_destino: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    estado: Mapped[SolicitudEstado] = mapped_column(
        Enum(
            SolicitudEstado,
            name="solicitud_estado_enum",
            native_enum=False,
            length=30,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=SolicitudEstado.PENDING,
    )
    prioridad: Mapped[str] = mapped_column(String(30), nullable=True)
    notas: Mapped[str] = mapped_column(String(500), nullable=True)
    motivo_rechazo: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at = created_at_column()
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


class DetalleSolicitudRecarga(Base):
    """Linea de detalle: un producto dentro de una solicitud (PK compuesta)."""

    __tablename__ = "detalle_solicitud_recarga"
    __table_args__ = (
        CheckConstraint("cantidad_solicitada > 0", name="cantidad_solicitada_positive"),
        CheckConstraint(
            "cantidad_despachada >= 0 AND cantidad_despachada <= cantidad_solicitada",
            name="cantidad_despachada_valid",
        ),
        CheckConstraint(
            "cantidad_recibida >= 0 AND cantidad_recibida <= cantidad_despachada",
            name="cantidad_recibida_valid",
        ),
    )

    id_solicitud: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("solicitudes_recarga.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id_producto: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    cantidad_solicitada: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cantidad_despachada: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    cantidad_recibida: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    barcode_validado: Mapped[str] = mapped_column(String(100), nullable=True)
    notas: Mapped[str] = mapped_column(String(500), nullable=True)
