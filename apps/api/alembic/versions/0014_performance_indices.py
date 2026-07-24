"""0014 performance indices for Big-O compliance

P1 del roadmap Big-O (docs/informe_escalabilidad_big_o.md):
agrega los indices que faltan para que las queries criticas
sean O(log n) en lugar de O(n) seq scan.

Cubre:
- audit_logs(actor_id, created_at)        - GET /audit
- stock_levels bajo minimo (partial)      - GET /solicitudes/bajo-minimo
- solicitudes_recarga(codigo) UNIQUE      - busqueda por codigo
- ordenes_compra(codigo) UNIQUE            - busqueda por codigo
- inventory_movements(reference) partial  - cuadre OC vs factura
- email_outbox(message_id) UNIQUE partial - idempotencia de envios
- user_sessions(user_id)                  - admin endpoints
- notifications(recipient_id, leido)      - bandeja de notificaciones

Idempotente: usa IF NOT EXISTS en todas las sentencias.
No modifica datos.

Revision ID: 0014_performance_indices
Revises: 0013_unique_stock_levels
Create Date: 2026-07-24 15:50:00
"""
from __future__ import annotations

from alembic import op


revision = "0014_performance_indices"
down_revision = "0013_unique_stock_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea los 8 indices nuevos.

    Cada CREATE INDEX es idempotente (IF NOT EXISTS). Si la migracion se
    corre dos veces, la segunda es no-op. Esto es importante porque
    el codigo de arranque del sistema corre migraciones en cada deploy.
    """
    # 1. audit_logs: busqueda por user_id (actor) + fecha
    #    Nota: el campo se llama user_id en el schema (no actor_id).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_user_created_at "
        "ON audit_logs (user_id, created_at DESC)"
    )

    # 2. stock_levels: bajo minimo (partial index - subset de filas)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stock_levels_bajo_minimo "
        "ON stock_levels (warehouse_id, quantity) "
        "WHERE min_quantity > 0"
    )

    # 3. solicitudes_recarga: codigo UNIQUE
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_solicitudes_codigo "
        "ON solicitudes_recarga (codigo)"
    )

    # 4. ordenes_compra: codigo UNIQUE
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_ordenes_codigo "
        "ON ordenes_compra (codigo)"
    )

    # 5. inventory_movements: reference (partial - solo con ref)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inventory_movements_reference "
        "ON inventory_movements (reference_type, reference_id) "
        "WHERE reference_id IS NOT NULL"
    )

    # 6. email_outbox: hot path del worker Arq (pendientes para enviar).
    #    Tabla no tiene message_id, en su lugar optimizamos la query
    #    WHERE status IN ('pending', 'failed') ORDER BY created_at.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_outbox_pending_worker "
        "ON email_outbox (status, created_at) "
        "WHERE status IN ('pending', 'failed')"
    )

    # 7. user_sessions: por user_id
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id "
        "ON user_sessions (user_id)"
    )

    # 8. notificaciones: user_id + leida + fecha
    #    Nota: la tabla se llama `notificaciones`, FK es `user_id`,
    #    y el campo es `leida` (femenino).
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notificaciones_user_leida "
        "ON notificaciones (user_id, leida, created_at DESC)"
    )

    # ANALYZE para que el planner use los nuevos indices.
    # Sin esto, Postgres puede elegir seq scan porque no sabe que
    # la tabla es grande. ANALYZE recolecta estadisticas.
    for table in (
        "audit_logs",
        "stock_levels",
        "solicitudes_recarga",
        "ordenes_compra",
        "inventory_movements",
        "email_outbox",
        "user_sessions",
        "notificaciones",
    ):
        op.execute(f"ANALYZE {table}")


def downgrade() -> None:
    """Revierte los 8 indices.

    Usar DROP INDEX IF EXISTS para que sea idempotente. No es comun
    hacer downgrade de una migracion de performance, pero esta disponible.
    """
    op.execute("DROP INDEX IF EXISTS idx_audit_logs_user_created_at")
    op.execute("DROP INDEX IF EXISTS idx_stock_levels_bajo_minimo")
    op.execute("DROP INDEX IF EXISTS uq_solicitudes_codigo")
    op.execute("DROP INDEX IF EXISTS uq_ordenes_codigo")
    op.execute("DROP INDEX IF EXISTS idx_inventory_movements_reference")
    op.execute("DROP INDEX IF EXISTS idx_email_outbox_pending_worker")
    op.execute("DROP INDEX IF EXISTS idx_user_sessions_user_id")
    op.execute("DROP INDEX IF EXISTS idx_notificaciones_user_leida")
