"""ordenes_compra + detalle_orden_compra + email_outbox

ADR-0005 (SMTP) + ADR-0006 (token approval).

Revision ID: 0007_ordenes_compra
Revises: 0006_solicitudes_recarga
Create Date: 2026-07-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0007_ordenes_compra"
down_revision: str | None = "0006_solicitudes_recarga"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ordenes_compra",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("id_bodega_principal", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_supervisor", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proveedor_nombre", sa.String(length=200), nullable=False),
        sa.Column("proveedor_contacto", sa.String(length=200), nullable=True),
        sa.Column("estado", sa.String(length=30), nullable=False, server_default="borrador"),
        sa.Column("total_estimado", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("motivo_rechazo", sa.String(length=500), nullable=True),
        sa.Column("email_token_jti", sa.String(length=64), nullable=True),
        sa.Column("email_enviado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aprobado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comprado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("total_estimado >= 0", name="ck_ordenes_total_estimado_non_negative"),
        sa.CheckConstraint(
            "estado IN ('borrador', 'enviado_a_supervisor', 'aprobado', 'comprado', 'rechazado')",
            name="ck_ordenes_estado_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ordenes_compra"),
        sa.UniqueConstraint("codigo", name="uq_ordenes_codigo"),
        sa.ForeignKeyConstraint(
            ["id_bodega_principal"], ["warehouses.id"],
            ondelete="RESTRICT", name="fk_ordenes_id_bodega_principal_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["id_supervisor"], ["supervisores.id"],
            ondelete="RESTRICT", name="fk_ordenes_id_supervisor_supervisores",
        ),
    )
    op.create_index(
        "ix_ordenes_estado_created_at", "ordenes_compra", ["estado", "created_at"],
    )

    op.create_table(
        "detalle_orden_compra",
        sa.Column("id_orden_compra", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_producto", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cantidad_pedida", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("costo_unitario_pactado", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.CheckConstraint("cantidad_pedida > 0", name="ck_detalle_orden_cantidad_pedida_positive"),
        sa.CheckConstraint("costo_unitario_pactado >= 0", name="ck_detalle_orden_costo_non_negative"),
        sa.PrimaryKeyConstraint(
            "id_orden_compra", "id_producto", name="pk_detalle_orden_compra",
        ),
        sa.ForeignKeyConstraint(
            ["id_orden_compra"], ["ordenes_compra.id"],
            ondelete="CASCADE", name="fk_detalle_orden_id_orden_compra_ordenes",
        ),
        sa.ForeignKeyConstraint(
            ["id_producto"], ["products.id"],
            ondelete="RESTRICT", name="fk_detalle_orden_id_producto_products",
        ),
    )

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("template_name", sa.String(length=100), nullable=True),
        sa.Column("template_context", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("attempts >= 0", name="ck_email_outbox_attempts_non_negative"),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="ck_email_outbox_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_outbox"),
    )
    op.create_index("ix_email_outbox_status", "email_outbox", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_status", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_table("detalle_orden_compra")
    op.drop_index("ix_ordenes_estado_created_at", table_name="ordenes_compra")
    op.drop_table("ordenes_compra")
