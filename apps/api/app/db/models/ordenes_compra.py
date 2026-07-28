"""Modelos SQLAlchemy para ordenes de compra externas + email outbox (ADR-0005, ADR-0006)."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from app.db.base import GUID, Base, created_at_column
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class OrdenCompraEstado(str, enum.Enum):
    BORRADOR = "borrador"
    ENVIADO_A_SUPERVISOR = "enviado_a_supervisor"
    APROBADO = "aprobado"
    COMPRADO = "comprado"
    RECHAZADO = "rechazado"


class OrdenCompra(Base):
    """Orden de compra externa. Pasa por aprobacion de supervisor via email+token."""

    __tablename__ = "ordenes_compra"
    __table_args__ = (
        CheckConstraint("total_estimado >= 0", name="total_estimado_non_negative"),
        Index("ix_ordenes_estado_created_at", "estado", "created_at"),
        # FKs frecuentes (Fase 3 indice performance).
        Index("ix_ordenes_supervisor", "id_supervisor"),
        Index("ix_ordenes_bodega_principal", "id_bodega_principal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    codigo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    id_bodega_principal: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    id_supervisor: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("supervisores.id", ondelete="RESTRICT"),
        nullable=False,
    )
    proveedor_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    proveedor_contacto: Mapped[str] = mapped_column(String(200), nullable=True)
    estado: Mapped[OrdenCompraEstado] = mapped_column(
        Enum(
            OrdenCompraEstado,
            name="orden_compra_estado_enum",
            native_enum=False,
            length=30,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=OrdenCompraEstado.BORRADOR,
    )
    total_estimado: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    notas: Mapped[str] = mapped_column(Text, nullable=True)
    motivo_rechazo: Mapped[str] = mapped_column(String(500), nullable=True)
    email_token_jti: Mapped[str] = mapped_column(String(64), nullable=True)
    email_enviado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    aprobado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    comprado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # FIX (FASE POST-E2E): persistir el ultimo token generado al enviar
    # el correo. Asi el operador puede reenviar el link si pierde el
    # email, sin tener que esperar a que el worker reprocese el outbox.
    # Solo roles admin/supervisor pueden leerlo via ?include_token=true.
    last_approval_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = created_at_column()
    updated_at = created_at_column()  # reused for simplicity


class DetalleOrdenCompra(Base):
    """Linea de detalle: un producto dentro de una OC (PK compuesta)."""

    __tablename__ = "detalle_orden_compra"
    __table_args__ = (
        CheckConstraint("cantidad_pedida > 0", name="cantidad_pedida_positive"),
        CheckConstraint("costo_unitario_pactado >= 0", name="costo_non_negative"),
    )

    id_orden_compra: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("ordenes_compra.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id_producto: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    cantidad_pedida: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    costo_unitario_pactado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class EmailOutbox(Base):
    """Outbox de emails para envio async (ADR-0005).

    El worker Arq lee esta tabla y envia via SMTP; al éxito marca sent_at.
    """

    __tablename__ = "email_outbox"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'dead')",
            name="email_outbox_status_valid",
        ),
        Index("ix_email_outbox_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    template_name: Mapped[str] = mapped_column(String(100), nullable=True)
    template_context: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = created_at_column()
