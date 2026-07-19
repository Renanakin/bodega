"""products extension: codigo_barras, id_categoria, precios + detalles_neumaticos

Revision ID: 0003_products_extension
Revises: 0002_categorias
Create Date: 2026-07-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0003_products_extension"
down_revision: str | None = "0002_categorias"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extender products
    op.add_column("products", sa.Column("codigo_barras", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("id_categoria", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "products",
        sa.Column("precio_costo", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "products",
        sa.Column("precio_venta", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
    )
    op.create_unique_constraint("uq_products_codigo_barras", "products", ["codigo_barras"])
    op.create_foreign_key(
        "fk_products_id_categoria_categories",
        "products", "categories",
        ["id_categoria"], ["id"],
        ondelete="SET NULL",
    )

    # detalles_neumaticos (1:1 opt-in)
    op.create_table(
        "detalles_neumaticos",
        sa.Column("producto_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ancho", sa.Integer(), nullable=False),
        sa.Column("perfil", sa.Integer(), nullable=False),
        sa.Column("aro", sa.Integer(), nullable=False),
        sa.Column("indice_carga", sa.Integer(), nullable=True),
        sa.Column("indice_velocidad", sa.String(length=5), nullable=True),
        sa.Column("dot", sa.String(length=20), nullable=True),
        sa.CheckConstraint("ancho > 0", name="ck_detalles_neumaticos_ancho_positive"),
        sa.CheckConstraint("perfil > 0", name="ck_detalles_neumaticos_perfil_positive"),
        sa.CheckConstraint("aro > 0", name="ck_detalles_neumaticos_aro_positive"),
        sa.PrimaryKeyConstraint("producto_id", name="pk_detalles_neumaticos"),
        sa.ForeignKeyConstraint(
            ["producto_id"], ["products.id"],
            ondelete="CASCADE", name="fk_detalles_neumaticos_producto_id_products",
        ),
    )


def downgrade() -> None:
    op.drop_table("detalles_neumaticos")
    op.drop_constraint("fk_products_id_categoria_categories", "products", type_="foreignkey")
    op.drop_constraint("uq_products_codigo_barras", "products", type_="unique")
    op.drop_column("products", "precio_venta")
    op.drop_column("products", "precio_costo")
    op.drop_column("products", "id_categoria")
    op.drop_column("products", "codigo_barras")
