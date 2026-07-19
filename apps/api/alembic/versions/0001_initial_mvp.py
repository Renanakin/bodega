"""initial MVP schema

Revision ID: 0001_initial_mvp
Revises:
Create Date: 2026-07-14 00:00:00.000000

Reglas aplicadas (ADR-0001):
- 8 tablas: warehouses, products, inventory_movements, stock_levels,
  transfers, users, user_sessions, audit_logs.
- Tipos UUID portables (Postgres native UUID / SQLite CHAR(32)).
- CHECK constraints portables.
- Foreign keys con ON DELETE explícito.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0001_initial_mvp"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- warehouses ---
    op.create_table(
        "warehouses",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("warehouse_type", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("parent_warehouse_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "warehouse_type IN ('principal', 'auxiliar', 'mecanico_box')",
            name="ck_warehouses_warehouse_type_valid",
        ),
        sa.CheckConstraint(
            "(warehouse_type IN ('principal', 'auxiliar') AND parent_warehouse_id IS NULL) "
            "OR (warehouse_type = 'mecanico_box' AND parent_warehouse_id IS NOT NULL)",
            name="ck_warehouses_parent_required_for_box",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_warehouses"),
        sa.UniqueConstraint("code", name="uq_warehouses_code"),
        sa.ForeignKeyConstraint(
            ["parent_warehouse_id"], ["warehouses.id"],
            ondelete="SET NULL", name="fk_warehouses_parent_warehouse_id_warehouses",
        ),
    )

    # --- products ---
    op.create_table(
        "products",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=60), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('admin', 'supervisor', 'origin_operator', 'destination_operator')", name="ck_users_role_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    # --- stock_levels ---
    op.create_table(
        "stock_levels",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("min_quantity", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("max_quantity", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_levels_quantity_non_negative"),
        sa.CheckConstraint("min_quantity >= 0", name="ck_stock_levels_min_quantity_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_stock_levels"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"],
            ondelete="CASCADE", name="fk_stock_levels_warehouse_id_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"],
            ondelete="CASCADE", name="fk_stock_levels_product_id_products",
        ),
    )
    op.create_index("ix_stock_levels_product", "stock_levels", ["product_id"])

    # --- inventory_movements ---
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("movement_type", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_movements_quantity_positive"),
        sa.CheckConstraint(
            "movement_type IN ('in', 'out', 'adjustment_in', 'adjustment_out')",
            name="ck_inventory_movements_movement_type_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_movements"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"],
            ondelete="RESTRICT", name="fk_inventory_movements_warehouse_id_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"],
            ondelete="RESTRICT", name="fk_inventory_movements_product_id_products",
        ),
    )
    op.create_index(
        "ix_inventory_movements_warehouse_product_created_at",
        "inventory_movements", ["warehouse_id", "product_id", "created_at"],
    )
    op.create_index(
        "ix_inventory_movements_product_created_at",
        "inventory_movements", ["product_id", "created_at"],
    )

    # --- transfers ---
    op.create_table(
        "transfers",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("from_warehouse_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_warehouse_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("received_quantity", sa.Numeric(precision=14, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("dispatch_notes", sa.String(length=500), nullable=True),
        sa.Column("receive_notes", sa.String(length=500), nullable=True),
        sa.Column("incident_type", sa.String(length=30), nullable=True),
        sa.Column("incident_notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_transfers_quantity_positive"),
        sa.CheckConstraint(
            "received_quantity >= 0 AND received_quantity <= quantity",
            name="ck_transfers_received_valid",
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'dispatched', 'partially_received', 'received', 'cancelled')",
            name="ck_transfers_status_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_transfers"),
        sa.UniqueConstraint("code", name="uq_transfers_code"),
        sa.ForeignKeyConstraint(
            ["from_warehouse_id"], ["warehouses.id"],
            ondelete="RESTRICT", name="fk_transfers_from_warehouse_id_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["to_warehouse_id"], ["warehouses.id"],
            ondelete="RESTRICT", name="fk_transfers_to_warehouse_id_warehouses",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"],
            ondelete="RESTRICT", name="fk_transfers_product_id_products",
        ),
    )
    op.create_index("ix_transfers_status_created_at", "transfers", ["status", "created_at"])

    # --- user_sessions ---
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.UniqueConstraint("token", name="uq_user_sessions_token"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            ondelete="CASCADE", name="fk_user_sessions_user_id_users",
        ),
    )
    op.create_index("ix_user_sessions_token", "user_sessions", ["token"])

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("detail", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            ondelete="SET NULL", name="fk_audit_logs_user_id_users",
        ),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_user_sessions_token", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_transfers_status_created_at", table_name="transfers")
    op.drop_table("transfers")
    op.drop_index("ix_inventory_movements_product_created_at", table_name="inventory_movements")
    op.drop_index("ix_inventory_movements_warehouse_product_created_at", table_name="inventory_movements")
    op.drop_table("inventory_movements")
    op.drop_index("ix_stock_levels_product", table_name="stock_levels")
    op.drop_table("stock_levels")
    op.drop_table("users")
    op.drop_table("products")
    op.drop_table("warehouses")
