"""Modelo SQLAlchemy para ubicaciones físicas de estanteria (Nivel 2 de stock)."""

import uuid

from app.db.base import GUID, Base, created_at_column, updated_at_column
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class UbicacionEstanteria(Base):
    """Ubicacion fisica dentro de una bodega: pasillo, estanteria, altura."""

    __tablename__ = "ubicaciones_estanteria"
    __table_args__ = (
        UniqueConstraint(
            "id_bodega",
            "pasillo",
            "estanteria",
            "altura",
            name="uq_ubicaciones_bodega_pasillo_estanteria_altura",
        ),
        CheckConstraint("pasillo > 0", name="pasillo_positive"),
        CheckConstraint("estanteria > 0", name="estanteria_positive"),
        CheckConstraint("altura > 0", name="altura_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    id_bodega: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )
    pasillo: Mapped[int] = mapped_column(Integer, nullable=False)
    estanteria: Mapped[int] = mapped_column(Integer, nullable=False)
    altura: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at = created_at_column()
    updated_at = updated_at_column()
