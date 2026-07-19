"""
Alembic environment (ADR-0001).

Reglas aplicadas:
- R1: lee DATABASE_URL desde Settings (nunca hardcoded en alembic.ini).
- R3: ubicación estándar (alembic/env.py).
- R5: nombres de variables autoexplicativos.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context

# Importar Settings y Base ANTES de tocar config
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

# Importar todos los modelos para que Base.metadata los conozca
# (R3: este import es intencional aunque no se usen las clases)
from app.db import models  # noqa: F401
from app.db.base import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

configure_logging()
log = get_logger(__name__)

# Alembic Config object
config = context.config

# Sobrescribir sqlalchemy.url desde Settings (R1)
settings = get_settings()
# Solo inyectamos la URL si está definida. Si no, confiamos en que el caller
# (CLI alembic o test) haya provisto sqlalchemy.url por otra vía.
if settings.database_url:
    config.set_main_option("sqlalchemy.url", settings.database_url)

# Configurar logging desde alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata para autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (genera SQL sin conectar)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Aplica las migraciones en la conexión dada."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode (con engine async)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
