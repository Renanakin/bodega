"""users.supervisor_id FK to supervisores (ADR-0002)

Vincula opcionalmente un user con un supervisor (entidad de dominio).
Permite que el user con role=supervisor se corresponda con un supervisor
físico (entidad que recibe emails de OC).

Revision ID: 0009_users_supervisor_link
Revises: 0008_proveedores
Create Date: 2026-07-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0009_users_supervisor_link"
down_revision: str | None = "0008_proveedores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("supervisor_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_supervisor_id_supervisores",
        "users", "supervisores",
        ["supervisor_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_supervisor_id_supervisores", "users", type_="foreignkey")
    op.drop_column("users", "supervisor_id")
