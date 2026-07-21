"""Modelos SQLAlchemy para users + auth (sessions + audit).

NOTA: NO usar `from __future__ import annotations` ni `relationship()` aquí.
"""

import enum
import uuid
from datetime import datetime

from app.db.base import GUID, Base, created_at_column
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    ORIGIN_OPERATOR = "origin_operator"
    DESTINATION_OPERATOR = "destination_operator"


class User(Base):
    """Usuario del sistema con su rol."""

    __tablename__ = "users"
    # NOTE: validación de username/full_name no-blank se hace en service.py (R4).
    # SQLite no soporta btrim() en CHECK constraints.

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    username: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role_enum",
            native_enum=False,
            length=40,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at = created_at_column()


class UserSession(Base):
    """Sesión activa de un usuario (token bearer)."""

    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_token", "token"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at = created_at_column()


class AuditLog(Base):
    """Log de auditoría de acciones críticas."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=True)
    detail: Mapped[str] = mapped_column(String(1000), nullable=True)
    created_at = created_at_column()
