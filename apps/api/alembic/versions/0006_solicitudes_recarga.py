"""solicitudes_recarga + detalle_solicitud_recarga (reemplaza transfers)

ADR-0003: Reemplaza transfers (1 producto) por solicitudes (N productos).

Revision ID: 0006_solicitudes_recarga
Revises: 0005_supervisores
Create Date: 2026-07-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0006_solicitudes_recarga"
down_revision: str | None = "0005_supervisores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "solicitudes_recarga",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("codigo", sa.String(length=50), nullable=False),
        sa.Column("id_bodega_origen", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_bodega_destino", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("estado", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("prioridad", sa.String(length=30), nullable=True),
        sa.Column("notas", sa.String(length=500), nullable=True),
        sa.Column("motivo_rechazo", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('pending', 'approved', 'in_transit', 'partially_received', "
            "'received', 'rejected', 'cancelled')",
            name="ck_solicitudes_estado_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_solicitudes_recarga"),
        sa.UniqueConstraint("codigo", name="uq_solicitudes_codigo"),
        sa.ForeignKeyConstraint(
            ["id_bodega_origen"], ["warehouses.id"],
            ondelete="RESTRICT", name="fk_solicitudes_id_bodega_origen_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["id_bodega_destino"], ["warehouses.id"],
            ondelete="RESTRICT", name="fk_solicitudes_id_bodega_destino_warehouses",
        ),
    )
    op.create_index(
        "ix_solicitudes_estado_created_at",
        "solicitudes_recarga", ["estado", "created_at"],
    )

    op.create_table(
        "detalle_solicitud_recarga",
        sa.Column("id_solicitud", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id_producto", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cantidad_solicitada", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("cantidad_despachada", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("cantidad_recibida", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("barcode_validado", sa.String(length=100), nullable=True),
        sa.Column("notas", sa.String(length=500), nullable=True),
        sa.CheckConstraint("cantidad_solicitada > 0", name="ck_detalle_solicitud_cantidad_solicitada_positive"),
        sa.CheckConstraint(
            "cantidad_despachada >= 0 AND cantidad_despachada <= cantidad_solicitada",
            name="ck_detalle_solicitud_cantidad_despachada_valid",
        ),
        sa.CheckConstraint(
            "cantidad_recibida >= 0 AND cantidad_recibida <= cantidad_despachada",
            name="ck_detalle_solicitud_cantidad_recibida_valid",
        ),
        sa.PrimaryKeyConstraint(
            "id_solicitud", "id_producto", name="pk_detalle_solicitud_recarga",
        ),
        sa.ForeignKeyConstraint(
            ["id_solicitud"], ["solicitudes_recarga.id"],
            ondelete="CASCADE", name="fk_detalle_solicitud_id_solicitud_solicitudes",
        ),
        sa.ForeignKeyConstraint(
            ["id_producto"], ["products.id"],
            ondelete="RESTRICT", name="fk_detalle_solicitud_id_producto_products",
        ),
    )


def downgrade() -> None:
    op.drop_table("detalle_solicitud_recarga")
    op.drop_index("ix_solicitudes_estado_created_at", table_name="solicitudes_recarga")
    op.drop_table("solicitudes_recarga")
