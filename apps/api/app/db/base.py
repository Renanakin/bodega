"""
DeclarativeBase y mixins compartidos por todos los modelos SQLAlchemy.

Reglas aplicadas:
- R3: ubicación obvia (db/base.py) para todo lo común entre modelos.
- R4: ningún modelo aquí; solo la base y mixins.
- R5: nombres autoexplicativos; cada mixin tiene un solo propósito.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator

# Convenciones de nombres para constraints (recomendación Alembic)
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos del dominio."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# --- Tipos personalizados ---


class GUID(TypeDecorator):
    """Tipo UUID portable: usa UUID nativo en Postgres, TEXT(36) en SQLite.

    En SQLite almacena como string UUID canonico (con guiones, 36 chars)
    en vez de hex (32 chars). Esto alinea el formato con el codigo
    legacy sync que usa ``str(uuid4())`` y permite que ambos paths
    (sync + async) compartan la misma BD sin mismatch de formato de id.

    Postgres: UUID nativo (16 bytes, mas eficiente).
    SQLite: TEXT/CHAR(36) con el formato canonico.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        # SQLite: almacenar como string canonico con guiones (36 chars)
        # para alinear con el codigo legacy sync que usa str(uuid4()).
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(uuid.UUID(str(value)))

    def process_result_value(self, value, dialect) -> Any | None:  # noqa: ARG002
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


# --- Columnas reutilizables (mixins) ---

# Anotación para columna UUID con default uuid4
UuidPK = Annotated[
    uuid.UUID,
    mapped_column(GUID(), primary_key=True, default=uuid.uuid4),
]


def created_at_column() -> Mapped[datetime]:
    """Columna created_at con default now() UTC."""
    return mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


def updated_at_column() -> Mapped[datetime]:
    """Columna updated_at con default now() UTC y onupdate."""
    return mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
