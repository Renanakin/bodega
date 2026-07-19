"""Stock por ubicacion fisica (Nivel 2: granularidad fina para picking)."""
import uuid
from decimal import Decimal

from app.db.base import GUID, Base, updated_at_column
from sqlalchemy import CheckConstraint, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column


class InventarioStockReal(Base):
    """Stock fisico por (producto, ubicacion). PK compuesta.

    En Fase 6+, stock_levels pasara a ser vista materializada
    sobre la suma de este modelo agrupada por (bodega, producto).
    """

    __tablename__ = "inventario_stock_real"
    __table_args__ = (
        CheckConstraint("cantidad >= 0", name="cantidad_non_negative"),
    )

    id_producto: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id_ubicacion: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("ubicaciones_estanteria.id", ondelete="CASCADE"),
        primary_key=True,
    )
    cantidad: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    updated_at = updated_at_column()
