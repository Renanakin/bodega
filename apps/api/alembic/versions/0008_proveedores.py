"""proveedores table

Revision ID: 0008_proveedores
Revises: 0007_ordenes_compra
Create Date: 2026-07-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0008_proveedores"
down_revision: str | None = "0007_ordenes_compra"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proveedores",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("rut", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("telefono", sa.String(length=30), nullable=True),
        sa.Column("direccion", sa.String(length=300), nullable=True),
        sa.Column("contacto_nombre", sa.String(length=150), nullable=True),
        sa.Column("lead_time_dias", sa.Integer(), nullable=False, server_default=sa.text("7")),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("length(nombre) > 0", name="ck_proveedores_nombre_not_blank"),
        sa.PrimaryKeyConstraint("id", name="pk_proveedores"),
        sa.UniqueConstraint("nombre", name="uq_proveedores_nombre"),
        sa.UniqueConstraint("rut", name="uq_proveedores_rut"),
    )


def downgrade() -> None:
    op.drop_table("proveedores")
