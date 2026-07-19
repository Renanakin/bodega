"""
Engine y session async para PostgreSQL (ADR-0001).

Aplica las reglas:
- R1: lee DATABASE_URL desde Settings (nunca hardcoded).
- R6: pool con `pool_pre_ping=True` para detectar conexiones muertas.
- R7: timeout 30s en queries lentas para no colgar el event loop.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

log = get_logger(__name__)


def create_postgres_engine() -> AsyncEngine:
    """Crea un AsyncEngine para PostgreSQL con la config de Settings."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,  # R6: detecta conexiones muertas tras restart de PG
        echo=settings.database_echo,  # Solo en development
        future=True,
        connect_args={
            "server_settings": {
                "application_name": f"bodegaje-api-{settings.environment}",
                "statement_timeout": "30000",  # 30s max por query
            },
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Crea una factory de sesiones async."""
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
        autoflush=False,
    )


async def ping_postgres(engine: AsyncEngine) -> bool:
    """Ping al Postgres. Retorna True si responde, False si no."""
    try:
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.warning("postgres.ping_failed", error=str(e))
        return False
