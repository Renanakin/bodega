"""add refresh tokens to user_sessions (C5.1)

Revision ID: 0011_refresh_tokens
Revises: 0010_indices_performance
Create Date: 2026-07-22

C5.1: refresh tokens. El schema original tenia solo un access token
(``token``) con expiracion. Ahora tenemos access (1h) + refresh (7d).
El refresh se usa para obtener un nuevo access via POST /auth/refresh.

Backfill: las sesiones existentes (pre-C5.1) reciben un refresh_token
derivado del access token. NO son refresh tokens validos, pero
permiten que la BD mantenga la constraint NOT NULL.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_refresh_tokens"
down_revision = "0010_indices_performance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Agregar columnas como NULLABLE primero para no romper sesiones
    # existentes durante el deploy.
    op.add_column(
        "user_sessions",
        sa.Column("refresh_token", sa.String(500), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill: derivar refresh_token del access token para sesiones
    # existentes. NO son refresh validos; el usuario debera re-loguearse.
    op.execute(
        "UPDATE user_sessions "
        "SET refresh_token = 'legacy-' || substr(token, 1, 40), "
        "    refresh_expires_at = expires_at "
        "WHERE refresh_token IS NULL"
    )

    # Ahora hacer NOT NULL.
    op.alter_column("user_sessions", "refresh_token", nullable=False)
    op.alter_column("user_sessions", "refresh_expires_at", nullable=False)

    # UNIQUE constraint (el access token ya tiene UNIQUE).
    op.create_unique_constraint(
        "uq_user_sessions_refresh_token",
        "user_sessions",
        ["refresh_token"],
    )

    # Indice para busquedas rapidas.
    op.create_index(
        "idx_user_sessions_refresh_token",
        "user_sessions",
        ["refresh_token"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_sessions_refresh_token", table_name="user_sessions")
    op.drop_constraint(
        "uq_user_sessions_refresh_token", "user_sessions", type_="unique"
    )
    op.drop_column("user_sessions", "refresh_expires_at")
    op.drop_column("user_sessions", "refresh_token")
