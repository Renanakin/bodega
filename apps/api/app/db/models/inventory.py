"""Modelos SQLAlchemy para inventory: stock_levels + inventory_movements.

NOTA: NO usar `from __future__ import annotations` ni `relationship()` aquí.
"""
import enum
import uuid
from decimal import Decimal

from app.db.base import GUID, Base, created_at_column, updated_at_column
from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class MovementType(str, enum.Enum):
    """Tipo de movimiento de inventario (alineado con la spec §3.1)."""

    IN = "in"
    OUT = "out"
    ADJUSTMENT_IN = "adjustment_in"
    ADJUSTMENT_OUT = "adjustment_out"


class StockLevel(Base):
    """Stock actual por bodega y producto (Nivel 1: agregado).

    En Fases futuras, este modelo se convierte en vista materializada
    sobre inventario_stock_real.
    """

    __tablename__ = "stock_levels"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("min_quantity >= 0", name="min_quantity_non_negative"),
        Index("ix_stock_levels_product", "product_id"),
        # Compuesto (warehouse_id, product_id) para queries del tipo
        # "stock de un producto en una bodega" (Fase 3 indice performance).
        Index("ix_stock_levels_warehouse_product", "warehouse_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    min_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    max_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=True)
    updated_at = updated_at_column()

    __mapper_args__ = {"eager_defaults": True}


class InventoryMovement(Base):
    """Movimiento de inventario: ledger auditable e inmutable."""

    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index(
            "ix_inventory_movements_warehouse_product_created_at",
            "warehouse_id",
            "product_id",
            "created_at",
        ),
        Index("ix_inventory_movements_product_created_at", "product_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    movement_type: Mapped[MovementType] = mapped_column(
        Enum(MovementType, name="movement_type_enum", native_enum=False, length=30, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=True)
    notes: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at = created_at_column()
