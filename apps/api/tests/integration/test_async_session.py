"""
Tests de integración para db/session.py (Fase 2: PostgreSQL real + Alembic).

Valida:
- Engine async funciona (Postgres o SQLite según env).
- Healthcheck con ping a DB y Redis.
- get_session como dependency de FastAPI.
"""

from __future__ import annotations

import pytest
from app.db.session import detect_backend, get_engine, ping_database

pytestmark = pytest.mark.integration


class TestEngineInitialization:
    """Engine se inicializa correctamente y se reutiliza (singleton)."""

    def test_engine_is_cached(self) -> None:
        """get_engine() retorna la misma instancia en llamadas sucesivas."""
        e1 = get_engine()
        e2 = get_engine()
        assert e1 is e2

    def test_detect_backend_returns_expected(self) -> None:
        """``detect_backend`` refleja el ``DATABASE_URL`` actual (sqlite o postgres)."""
        from app.core.config import get_settings

        settings = get_settings()
        expected = "postgres" if settings.database_url.startswith("postgresql") else "sqlite"
        assert detect_backend() == expected


class TestPingDatabase:
    """ping_database() retorna True en SQLite funcional."""

    @pytest.mark.asyncio
    async def test_ping_sqlite_returns_true(self) -> None:
        result = await ping_database()
        assert result is True


class TestHealthcheckContract:
    """El endpoint /api/v1/health expone la estructura correcta."""

    @pytest.mark.asyncio
    async def test_health_structure_contains_required_keys(self) -> None:
        """El healthcheck devuelve 'status' y 'checks' con database y redis."""
        from app.modules.health.router import healthcheck
        from fastapi import Response

        response = Response()
        result = await healthcheck(response)

        assert "status" in result
        assert "checks" in result
        assert "database" in result["checks"]
        assert "redis" in result["checks"]
        assert "status" in result["checks"]["database"]
        assert "status" in result["checks"]["redis"]
        assert result["checks"]["database"]["backend"] in ("sqlite", "postgres")
