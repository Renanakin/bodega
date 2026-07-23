"""0012 single principal warehouse

BUG 7 (fix 2026-07-22): the system had 6 warehouses marked as
``warehouse_type='principal'`` (the canonical one + 5 inherited from
seeds and tests). This polluted the Consolidador de Quiebres and any
logic that assumes a single active principal. This migration reassigns
the 5 spurious "principal" warehouses to 'auxiliar'.

Rules:
- Only touches warehouses that are currently 'principal' AND are NOT
  the canonical principal 'BOD-PPAL-E52D7888'. Idempotent: if already
  'auxiliar', the UPDATE matches no rows.
- The CHECK constraint ``ck_warehouses_parent_warehouse_required_for_box``
  requires 'auxiliar' to have ``parent_warehouse_id IS NULL``. The 5
  warehouses being changed already meet this (all have parent NULL).
- Uses raw SQL because the operation is a one-time data fix, not a
  schema change.

Revision ID: 0012_single_principal_warehouse
Revises: 0011_refresh_tokens
Create Date: 2026-07-22 23:48:00
"""
from __future__ import annotations

from alembic import op


revision = "0012_single_principal_warehouse"
down_revision = "0011_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE warehouses
        SET warehouse_type = 'auxiliar',
            updated_at = NOW()
        WHERE warehouse_type = 'principal'
          AND code <> 'BOD-PPAL-E52D7888'
        """
    )


def downgrade() -> None:
    # No es trivial restaurar el tipo original sin un backup de la
    # tabla. Si se necesita rollback, restaurar desde el backup
    # pre-migracion (disaster-recovery runbook).
    raise NotImplementedError(
        "0012_single_principal_warehouse no tiene downgrade: "
        "restaura desde backup pre-migracion si necesitas revertir."
    )
