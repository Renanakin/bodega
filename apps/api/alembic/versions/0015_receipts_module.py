"""0015 receipts module + expose approval_token on OC

FIX (FASE POST-E2E): el modulo de Recepciones estaba documentado en el
manual de usuario (seccion 8) pero NO implementado. Esta migracion:

1. Crea las tablas ``receipts`` y ``receipt_lines``.
2. Agrega la columna ``last_approval_token`` a ``ordenes_compra`` para
   que el sistema pueda devolver el token al hacer GET /ordenes-compra/{id}
   (necesario para que el operador pueda re-enviar el link si pierde el
   email, sin tener que esperar a que el worker reprocese el outbox).

Seguridad: ``last_approval_token`` es HMAC-SHA256 firmado con
``SECRET_KEY`` (no JWT). Solo los roles admin/supervisor pueden leerlo.
El endpoint NO lo expone a menos que se pida explicitamente via el
param ``?include_token=true``.

Revision ID: 0015_receipts_module
Revises: 0014_performance_indices
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = "0015_receipts_module"
down_revision = "0014_performance_indices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Tabla receipts
    op.create_table(
        "receipts",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("codigo", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "id_bodega_destino",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "id_proveedor",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("proveedores.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "id_orden_compra",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("ordenes_compra.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("numero_documento", sa.String(80), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("notas", sa.Text, nullable=True),
        sa.Column(
            "created_by",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "confirmed_by",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_receipts_codigo", "receipts", ["codigo"], unique=True)
    op.create_index("ix_receipts_id_bodega_destino", "receipts", ["id_bodega_destino"])
    op.create_index("ix_receipts_id_proveedor", "receipts", ["id_proveedor"])
    op.create_index("ix_receipts_id_orden_compra", "receipts", ["id_orden_compra"])
    op.create_index("ix_receipts_estado", "receipts", ["estado"])
    op.create_index(
        "ix_receipts_estado_bodega", "receipts", ["estado", "id_bodega_destino"]
    )

    # 2. Tabla receipt_lines
    op.create_table(
        "receipt_lines",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "id_receipt",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("receipts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "id_producto",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("cantidad", sa.Numeric(14, 2), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("movement_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_receipt_lines_id_receipt", "receipt_lines", ["id_receipt"])
    op.create_index("ix_receipt_lines_id_producto", "receipt_lines", ["id_producto"])

    # 3. Columna last_approval_token en ordenes_compra
    op.add_column(
        "ordenes_compra",
        sa.Column("last_approval_token", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ordenes_compra", "last_approval_token")
    op.drop_index("ix_receipt_lines_id_producto", table_name="receipt_lines")
    op.drop_index("ix_receipt_lines_id_receipt", table_name="receipt_lines")
    op.drop_table("receipt_lines")
    op.drop_index("ix_receipts_estado_bodega", table_name="receipts")
    op.drop_index("ix_receipts_estado", table_name="receipts")
    op.drop_index("ix_receipts_id_orden_compra", table_name="receipts")
    op.drop_index("ix_receipts_id_proveedor", table_name="receipts")
    op.drop_index("ix_receipts_id_bodega_destino", table_name="receipts")
    op.drop_index("ix_receipts_codigo", table_name="receipts")
    op.drop_table("receipts")
