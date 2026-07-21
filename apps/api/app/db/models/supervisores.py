"""Modelo SQLAlchemy para supervisores (entidad de dominio).

Distinto de users.role='supervisor' (que es permiso de auth).
Esta entidad es la persona fisica con email que autoriza OC externas.
"""

import uuid

from app.db.base import GUID, Base, created_at_column, updated_at_column
from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column


class Supervisor(Base):
    """Supervisor con email que recibe notificaciones de OC y autoriza por token."""

    __tablename__ = "supervisores"
    __table_args__ = (CheckConstraint("length(nombre) > 0", name="nombre_not_blank"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    telefono: Mapped[str] = mapped_column(String(30), nullable=True)
    cargo: Mapped[str] = mapped_column(String(100), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at = created_at_column()
    updated_at = updated_at_column()
