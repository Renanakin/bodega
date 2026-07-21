"""
Engine y session async para SQLite (modo tests o dev ultra-ligero).

NO usar en producción (ADR-0001). Solo para tests rápidos y demos.
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


def create_sqlite_engine(db_path: str | None = None) -> AsyncEngine:
    """Crea un AsyncEngine para SQLite.

    Args:
        db_path: ruta a la BD SQLite. Si es None, se resuelve del
            ``settings.database_url`` (ej: ``sqlite+aiosqlite:///path/db.db``).
            Si no hay URL definido, se usa ``:memory:`` (default para tests).
    """
    if db_path is None:
        url = get_settings().database_url or ""
        # Extraer path del URL: ``sqlite+aiosqlite:///path/to/db.db`` -> path
        if url.startswith(("sqlite+aiosqlite:///", "sqlite:///")):
            db_path = url.split(":///", 1)[1] or ":memory:"
        else:
            db_path = ":memory:"
    aiosqlite_url = f"sqlite+aiosqlite:///{db_path}"
    log.info("db.sqlite_engine_creating", path=db_path, url=aiosqlite_url)
    return create_async_engine(
        aiosqlite_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Crea una factory de sesiones async."""
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
        autoflush=False,
    )


async def ping_sqlite(engine: AsyncEngine) -> bool:
    """Ping al SQLite. Retorna True si responde."""
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.warning("sqlite.ping_failed", error=str(e))
        return False
