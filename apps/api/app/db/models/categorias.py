"""Modelo SQLAlchemy para categorias de productos."""

import uuid

from app.db.base import GUID, Base, created_at_column, updated_at_column
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class Category(Base):
    """Categoria de productos. Soporta jerarquia opcional via parent_id."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    descripcion: Mapped[str] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        # Self-FK: una categoria puede tener subcategorias
        # No uso ForeignKey() para evitar problemas con import circular
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at = created_at_column()
    updated_at = updated_at_column()
