"""Extensión de products con codigo_barras, precios y categoria. Plus detalles_neumaticos.

Reglas aplicadas:
- R3: extension de un modelo existente, no duplicación.
- R5: nombres describen el rol (product_extension vs products).
"""
import uuid

from app.db.base import GUID, Base
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# --- Tabla extension: detalles_neumaticos (opt-in 1:1 con products) ---

class DetalleNeumatico(Base):
    """Detalle de un producto tipo neumatico (1:1 opt-in)."""

    __tablename__ = "detalles_neumaticos"
    __table_args__ = (
        CheckConstraint("ancho > 0", name="ancho_positive"),
        CheckConstraint("perfil > 0", name="perfil_positive"),
        CheckConstraint("aro > 0", name="aro_positive"),
    )

    producto_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ancho: Mapped[int] = mapped_column(Integer, nullable=False)
    perfil: Mapped[int] = mapped_column(Integer, nullable=False)
    aro: Mapped[int] = mapped_column(Integer, nullable=False)
    indice_carga: Mapped[int] = mapped_column(Integer, nullable=True)
    indice_velocidad: Mapped[str] = mapped_column(String(5), nullable=True)
    dot: Mapped[str] = mapped_column(String(20), nullable=True)
