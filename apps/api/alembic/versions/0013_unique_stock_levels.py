"""0013 unique stock levels per warehouse/product

BUG 9 (fix 2026-07-23): stock_levels permitia duplicados
(warehouse_id, product_id). Eso provocaba:

- Filas duplicadas en GET /solicitudes/bajo-minimo.
- Error 'Productos duplicados en la solicitud' en el Evaluator
  cuando varios SKUs bajo minimo en la misma bodega resultaban en
  un INSERT con productos repetidos.
- Conteo inflado en el report (skus_bajo_minimo contaba cada
  duplicado por separado).

Esta migracion:
1) Elimina duplicados dejando la fila con updated_at mas reciente
   (desempate por id para estabilidad).
2) Reemplaza el indice ix_stock_levels_warehouse_product (no-unique)
   por un UNIQUE constraint uq_stock_levels_warehouse_product.

Idempotente: si el constraint ya existe, no falla.

Revision ID: 0013_unique_stock_levels
Revises: 0012_single_principal_warehouse
Create Date: 2026-07-23 00:50:00
"""
from __future__ import annotations

from alembic import op


revision = "0013_unique_stock_levels"
down_revision = "0012_single_principal_warehouse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Eliminar duplicados dejando la fila con updated_at mas reciente.
    op.execute(
        """
        DELETE FROM stock_levels
        WHERE id IN (
          SELECT id FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                     PARTITION BY warehouse_id, product_id
                     ORDER BY updated_at DESC, id DESC
                   ) AS rn
            FROM stock_levels
          ) t
          WHERE t.rn > 1
        )
        """
    )

    # 2. Eliminar el indice antiguo (no-unique) para reemplazarlo
    #    por el constraint UNIQUE.
    op.execute("DROP INDEX IF EXISTS ix_stock_levels_warehouse_product")

    # 3. Crear el UNIQUE constraint.
    op.execute(
        """
        ALTER TABLE stock_levels
          ADD CONSTRAINT uq_stock_levels_warehouse_product
          UNIQUE (warehouse_id, product_id)
        """
    )


def downgrade() -> None:
    # Revertir a no-unique (no se restauran los duplicados borrados;
    # seria necesario un backup pre-migracion).
    op.execute(
        "ALTER TABLE stock_levels DROP CONSTRAINT IF EXISTS uq_stock_levels_warehouse_product"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stock_levels_warehouse_product "
        "ON stock_levels (warehouse_id, product_id)"
    )
