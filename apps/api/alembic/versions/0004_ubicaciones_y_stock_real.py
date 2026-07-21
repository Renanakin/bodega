"""ubicaciones_estanteria + inventario_stock_real

Revision ID: 0004_ubicaciones_y_stock_real
Revises: 0003_products_extension
Create Date: 2026-07-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0004_ubicaciones_y_stock_real"
down_revision: str | None = "0003_products_extension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ubicaciones_estanteria",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_bodega", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pasillo", sa.Integer(), nullable=False),
        sa.Column("estanteria", sa.Integer(), nullable=False),
        sa.Column("altura", sa.Integer(), nullable=False),
        sa.Column("descripcion", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("pasillo > 0", name="ck_ubicaciones_pasillo_positive"),
        sa.CheckConstraint("estanteria > 0", name="ck_ubicaciones_estanteria_positive"),
        sa.CheckConstraint("altura > 0", name="ck_ubicaciones_altura_positive"),
        sa.UniqueConstraint(
            "id_bodega", "pasillo", "estanteria", "altura",
            name="uq_ubicaciones_bodega_pasillo_estanteria_altura",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ubicaciones_estanteria"),
        sa.ForeignKeyConstraint(
            ["id_bodega"], ["warehouses.id"],
            ondelete="CASCADE", name="fk_ubicaciones_id_bodega_warehouses",
        ),
    )

    op.create_table(
        "inventario_stock_real",
        sa.Column("id_producto", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_ubicacion", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cantidad", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("cantidad >= 0", name="ck_inventario_stock_real_cantidad_non_negative"),
        sa.PrimaryKeyConstraint(
            "id_producto", "id_ubicacion", name="pk_inventario_stock_real"
        ),
        sa.ForeignKeyConstraint(
            ["id_producto"], ["products.id"],
            ondelete="CASCADE", name="fk_inventario_stock_real_id_producto_products",
        ),
        sa.ForeignKeyConstraint(
            ["id_ubicacion"], ["ubicaciones_estanteria.id"],
            ondelete="CASCADE", name="fk_inventario_stock_real_id_ubicacion_ubicaciones",
        ),
    )

    # NOTE: max_quantity column was already added in 0001_initial_mvp.
    # A previous version of this migration tried to add it again here,
    # which caused DuplicateColumnError on fresh DBs. Keeping the column
    # definition in 0001 is correct (it's part of the initial schema).


def downgrade() -> None:
    op.drop_table("inventario_stock_real")
    op.drop_table("ubicaciones_estanteria")
