"""Modelo SQLAlchemy para proveedores externos."""
import uuid

from app.db.base import GUID, Base, created_at_column, updated_at_column
from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column


class Proveedor(Base):
    """Proveedor externo de productos."""

    __tablename__ = "proveedores"
    __table_args__ = (
        CheckConstraint("length(nombre) > 0", name="nombre_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    rut: Mapped[str] = mapped_column(String(20), nullable=True, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    telefono: Mapped[str] = mapped_column(String(30), nullable=True)
    direccion: Mapped[str] = mapped_column(String(300), nullable=True)
    contacto_nombre: Mapped[str] = mapped_column(String(150), nullable=True)
    lead_time_dias: Mapped[int] = mapped_column(default=7, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at = created_at_column()
    updated_at = updated_at_column()
