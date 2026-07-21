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
    """Configura ENVIRONMENT=development y DATABASE_URL=sqlite in-memory para todos los tests."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    reset_settings_cache()


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
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Sesión async por test (rollback al final)."""
    async with AsyncSession(async_engine, expire_on_commit=False) as session:
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
