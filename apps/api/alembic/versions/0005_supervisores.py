"""supervisores table (entidad de dominio distinta de users.role)

Revision ID: 0005_supervisores
Revises: 0004_ubicaciones_y_stock_real
Create Date: 2026-07-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0005_supervisores"
down_revision: str | None = "0004_ubicaciones_y_stock_real"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supervisores",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("telefono", sa.String(length=30), nullable=True),
        sa.Column("cargo", sa.String(length=100), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("length(nombre) > 0", name="ck_supervisores_nombre_not_blank"),
        sa.PrimaryKeyConstraint("id", name="pk_supervisores"),
        sa.UniqueConstraint("email", name="uq_supervisores_email"),
    )


def downgrade() -> None:
    op.drop_table("supervisores")
