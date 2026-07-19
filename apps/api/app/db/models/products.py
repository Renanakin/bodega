"""Modelo SQLAlchemy para products.

Extendido en Fase 4 con codigo_barras, id_categoria, precio_costo, precio_venta.
"""
import uuid
from decimal import Decimal

from app.db.base import GUID, Base, created_at_column, updated_at_column
from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column


class Product(Base):
    """Producto del catalogo."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    codigo_barras: Mapped[str] = mapped_column(String(100), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    id_categoria: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    precio_costo: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    precio_venta: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at = created_at_column()
    updated_at = updated_at_column()
