"""
Conftest para tests de integración (Regla de Oro R6).

Usa SQLite in-memory async (aiosqlite) para que los tests sean rápidos
y no requieran Docker. Los tests específicos de Postgres usan
pytest-postgresql o se skippean si no hay Docker.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from app.core.config import reset_settings_cache
from app.db import models  # noqa: F401  -- importa modelos para que Base.metadata los conozca
from app.db.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


@pytest.fixture(autouse=True)
def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configura ENVIRONMENT=development y defaults para tests SQLite.

    Si el runner externo ya seteó ``DATABASE_URL=postgresql+...`` o
    ``REDIS_URL=redis://...`` (tests de integración reales), NO los
    pisamos. Los fixtures ``async_engine_postgres`` y los tests SMTP
    leen estas variables explícitamente.
    """
    import os

    monkeypatch.setenv("ENVIRONMENT", "development")
    if not os.getenv("DATABASE_URL", "").startswith("postgresql"):
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    if not os.getenv("REDIS_URL", ""):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    if not os.getenv("JWT_SECRET", ""):
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
    if not os.getenv("SECRET_KEY", ""):
        monkeypatch.setenv("SECRET_KEY", "x" * 32)
    reset_settings_cache()
    # Reset engine cacheado: si un test anterior uso Postgres, su engine
    # asyncpg quedo atado al event loop de ese test. Al cambiar DATABASE_URL
    # hay que invalidar el singleton para que el siguiente test cree uno nuevo.
    from app.db.session import reset_engine_cache

    reset_engine_cache()


@pytest_asyncio.fixture
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Engine async con SQLite in-memory. Las tablas se crean en cada test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_engine_postgres() -> AsyncGenerator[AsyncEngine, None]:
    """Engine async contra Postgres real. Solo se usa en tests marcados con ``@pytest.mark.postgres``.

    Requiere que el runner haya seteado ``DATABASE_URL=postgresql+asyncpg://...``.
    Si no, skip el test.
    """
    import os

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        pytest.skip("Requiere DATABASE_URL=postgresql+asyncpg:// (no seteado)")
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(db_url, echo=False, poolclass=NullPool)
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


@pytest_asyncio.fixture
async def async_session_postgres(async_engine_postgres: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Sesion async contra Postgres. Rollback al final del test."""
    async with AsyncSession(async_engine_postgres, expire_on_commit=False) as session:
        yield session
        await session.rollback()


@pytest.fixture
def postgres_required() -> Any:
    """Skip el test si DATABASE_URL no apunta a Postgres real.

    Uso:
        async def test_x(postgres_required):
            ...
    """
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("Test requiere PostgreSQL real (DATABASE_URL=postgresql+asyncpg://...)")
    return settings
