"""add indices for FK columns and common query paths

Revision ID: 0010_indices_performance
Revises: 0009_users_supervisor_link
Create Date: 2026-07-20

Fase 3 (3.2 - audit de performance). Anade indices en columnas FK
y combinaciones frecuentes que se consultan en endpoints hot path
pero no tenian indice.

Cambios:
- stock_levels: indice compuesto (warehouse_id, product_id). Ya hay
  ix_stock_levels_product sobre (product_id); este anade el orden
  natural de consulta por bodega + producto.
- detalle_orden_compra: indice sobre producto_id para joins N+1->1
  (ya resuelto en codigo, este indice acelera el join).
- detalle_solicitud_recarga: indice sobre producto_id (mismo motivo).
- ordenes_compra: indices sobre id_supervisor, id_bodega_principal
  y codigo (unico, ya deberia estar, se asegura explicito).
- audit_log: indices sobre (user_id, created_at) y (entity_type, entity_id)
  para queries de auditoria.
- notifications: indice sobre (user_id, read_at) para query de
  no-leidas.

Impacto esperado:
- /inventory/stock: de O(N) por bodega a O(log N) por (warehouse, product).
- /reports/ejecutivo (resumen_bodegas): el GROUP BY en Python con
  indice en (warehouse_id, product_id) es O(N log N) en vez de O(N^2).
- /audit y /notificaciones: queries de filtrado por usuario son O(log N).

Revision ID: 0010_indices_performance
Revises: 0009_users_supervisor_link
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0010_indices_performance"
down_revision = "0009_users_supervisor_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # stock_levels: ya existe ix_stock_levels_product. Anadimos el
    # compuesto (warehouse_id, product_id) que es el orden natural
    # de consulta en /inventory/stock y resumen_bodegas.
    op.create_index(
        "ix_stock_levels_warehouse_product",
        "stock_levels",
        ["warehouse_id", "product_id"],
        unique=False,
    )

    # detalle_orden_compra: FK hacia productos, muy consultada en
    # /ordenes-compra/<id> y en el dashboard de OC.
    op.create_index(
        "ix_detalle_oc_producto",
        "detalle_orden_compra",
        ["id_producto"],
        unique=False,
    )

    # detalle_solicitud_recarga: FK hacia productos, consultada en
    # /solicitudes/<id> y dashboard del Evaluator.
    op.create_index(
        "ix_detalle_solicitud_producto",
        "detalle_solicitud_recarga",
        ["id_producto"],
        unique=False,
    )

    # ordenes_compra: FKs y codigo unico explicito.
    op.create_index(
        "ix_ordenes_supervisor",
        "ordenes_compra",
        ["id_supervisor"],
        unique=False,
    )
    op.create_index(
        "ix_ordenes_bodega_principal",
        "ordenes_compra",
        ["id_bodega_principal"],
        unique=False,
    )
    # NOTA: NO crear uq_ordenes_codigo aqui. La UniqueConstraint
    # "uq_ordenes_codigo" ya fue creada en 0007_ordenes_compra.py como
    # parte de la definicion de la tabla. Intentar crear un indice con
    # el mismo nombre aqui produce DuplicateTableError en Postgres.

    # audit_log: queries por usuario y por entidad.
    op.create_index(
        "ix_audit_log_user_created",
        "audit_log",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_entity",
        "audit_log",
        ["entity_type", "entity_id"],
        unique=False,
    )

    # notifications: query mas comun es "no leidas del usuario X".
    op.create_index(
        "ix_notifications_user_read",
        "notificaciones",
        ["user_id", "read_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read", table_name="notificaciones")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_user_created", table_name="audit_log")
    # NOTA: uq_ordenes_codigo no se dropea porque no se creo en esta
    # migracion (ver comentario en upgrade).
    op.drop_index("ix_ordenes_bodega_principal", table_name="ordenes_compra")
    op.drop_index("ix_ordenes_supervisor", table_name="ordenes_compra")
    op.drop_index("ix_detalle_solicitud_producto", table_name="detalle_solicitud_recarga")
    op.drop_index("ix_detalle_oc_producto", table_name="detalle_orden_compra")
    op.drop_index("ix_stock_levels_warehouse_product", table_name="stock_levels")
