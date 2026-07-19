"""
Conftest global: fixtures compartidas entre unit e integration tests.

Regla R6: las fixtures complejas (DB, async engine) viven aquí para evitar
duplicación entre conftest.py de unit/ e integration/.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import structlog
from app.core.config import reset_settings_cache
from app.db import models  # noqa: F401  -- importa modelos para que Base.metadata los conozca
from app.db.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


@pytest.fixture(autouse=True)
def _reset_structlog_context() -> None:
    """Limpia el contexto de structlog entre tests."""
    structlog.contextvars.clear_contextvars()


@pytest.fixture
def env_development(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fuerza ENVIRONMENT=development y limpia el caché de Settings."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX")
    reset_settings_cache()


@pytest.fixture
def caplog_with_structlog(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Fixture que captura tanto logs de stdlib logging como de structlog."""
    import logging
    caplog.set_level(logging.DEBUG)
    return caplog


@pytest_asyncio.fixture
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Engine async con SQLite in-memory compartido via StaticPool.

    StaticPool fuerza a que TODAS las sesiones usen la misma conexión,
    lo cual es necesario para tests de concurrencia donde múltiples
    AsyncSession deben ver los mismos datos.
    """
    from sqlalchemy import event
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    # Habilitar PRAGMA foreign_keys=ON para que SQLite enforcé FKs y CHECKs.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Sesión async por test (rollback al final)."""
    async with AsyncSession(async_engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()


@pytest.fixture
def postgres_required() -> object:
    """Skip el test si DATABASE_URL no apunta a Postgres real."""
    from app.core.config import get_settings
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        pytest.skip(
            "Test requiere PostgreSQL real (DATABASE_URL=postgresql+asyncpg://...)"
        )
    return settings
