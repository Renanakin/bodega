"""Modelo SQLAlchemy para warehouses (ADR-0002: incluye boxes).

NOTA: NO usar `from __future__ import annotations` ni `relationship()` por ahora.
Hay un bug en SQLAlchemy 2.0.36 + Python 3.14 con Mapped[ForwardRef].
Las relaciones se hacen via queries en los repositories.
"""
import uuid

from app.db.base import GUID, Base, created_at_column, updated_at_column
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class Warehouse(Base):
    """Bodega: principal, auxiliar o box de mecánico (ADR-0002)."""

    __tablename__ = "warehouses"
    __table_args__ = (
        CheckConstraint(
            "warehouse_type IN ('principal', 'auxiliar', 'mecanico_box')",
            name="warehouse_type_valid",
        ),
        CheckConstraint(
            "(warehouse_type IN ('principal', 'auxiliar') AND parent_warehouse_id IS NULL) "
            "OR (warehouse_type = 'mecanico_box' AND parent_warehouse_id IS NOT NULL)",
            name="parent_warehouse_required_for_box",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    warehouse_type: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    parent_warehouse_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = created_at_column()
    updated_at = updated_at_column()
    # NOTE: ADR-0002: mecanico_box requiere parent_warehouse_id NOT NULL.
    # Validado en service.py y en CHECK constraint de la migración 0002.
