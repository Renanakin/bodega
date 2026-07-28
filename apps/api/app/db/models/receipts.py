"""Modelo: receipts (Recepciones de mercaderia).

FIX (FASE POST-E2E): el modulo de Recepciones estaba documentado en el manual
('') pero NO implementado. Este modelo + el router/service en
``app/modules/receipts/`` lo implementa siguiendo la spec del manual
seccion 8.

Una Recepcion es un documento que registra la entrada de mercaderia de un
proveedor. Tiene 2 fases:
1. Crear en estado ``pending``: NO toca stock.
2. Confirmar: genera movimientos ``in`` en la bodega destino.

Relaciones:
- ``id_bodega_destino`` (FK a warehouses)
- ``id_proveedor`` (FK a proveedores, opcional: una recepcion puede ser
  sin proveedor si es devolucion, merma o ajuste)
- ``id_orden_compra`` (FK a ordenes_compra, opcional: la recepcion puede
  referenciar una OC, lo que la marca como cumplida)
- ``numero_documento``: factura/guia del proveedor (string, no unico
  para no romper si llega el mismo doc 2 veces)
- ``estado``: pending | confirmed | cancelled
- ``created_by`` (FK a users)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.ordenes_compra import OrdenCompra
    from app.db.models.proveedores import Proveedor
    from app.db.models.users import User
    from app.db.models.warehouses import Warehouse


class Receipt(Base):
    """Recepcion de mercaderia de un proveedor (o devolucion/ajuste)."""

    __tablename__ = "receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    codigo: Mapped[str] = mapped_column(String(40), nullable=False, unique=True, index=True)
    # Bodega donde entra la mercaderia
    id_bodega_destino: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Proveedor (opcional: NULL = devolucion, merma, ajuste sin proveedor)
    id_proveedor: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("proveedores.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # Orden de compra asociada (opcional, para cuando la recepcion viene
    # de una OC aprobada; al confirmar la recepcion la OC pasa a received)
    id_orden_compra: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ordenes_compra.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Numero de documento del proveedor (factura, guia de despacho)
    numero_documento: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Estado del ciclo de vida
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True,
    )
    # Notas libres del operador
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Auditoria basica
    created_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        # server_default lo pone Alembic; default local es para tests.
        # Importante: NO usar UTC (offset-aware) porque la columna BD es
        # TIMESTAMP WITHOUT TIME ZONE (naive). Pasamos func.now() del server.
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True,
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Relaciones (lazy para no romper el import circular)
    bodega_destino: Mapped["Warehouse"] = relationship(
        "Warehouse", foreign_keys=[id_bodega_destino], lazy="joined",
    )
    proveedor: Mapped["Proveedor | None"] = relationship(
        "Proveedor", foreign_keys=[id_proveedor], lazy="joined",
    )
    orden_compra: Mapped["OrdenCompra | None"] = relationship(
        "OrdenCompra", foreign_keys=[id_orden_compra], lazy="joined",
    )
    lineas: Mapped[list["ReceiptLine"]] = relationship(
        "ReceiptLine", back_populates="receipt",
        cascade="all, delete-orphan", lazy="selectin",
    )

    __table_args__ = (
        Index("ix_receipts_estado_bodega", "estado", "id_bodega_destino"),
    )


class ReceiptLine(Base):
    """Linea de una recepcion: 1 SKU + cantidad + precio."""

    __tablename__ = "receipt_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    id_receipt: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_producto: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    cantidad: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    precio_unitario: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    # ID del movimiento de inventario generado al confirmar (referencia)
    movement_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True,
    )

    # Relacion inversa con Receipt
    receipt: Mapped["Receipt"] = relationship("Receipt", back_populates="lineas")
