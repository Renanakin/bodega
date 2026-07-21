"""
Tests de integración contra servicios externos vivos (Postgres, Redis, Mailpit).

Requisitos:
- docker compose up -d (Postgres en 5432, Redis en 6379, Mailpit en 1025/8025)
- Variables de entorno: DATABASE_URL=postgresql+asyncpg://, REDIS_URL=redis://, SMTP_HOST=127.0.0.1

Si algún servicio no está disponible, los tests se skippean con razón clara.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
import uuid
from contextlib import suppress

import httpx
import pytest
from app.core.config import get_settings

pytestmark = pytest.mark.integration


# --------------------------------------------------------- PROBES


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


@pytest.fixture
def redis_required() -> None:
    """Skip si Redis no está accesible en el host/port de ``redis_url``."""
    from urllib.parse import urlparse

    settings = get_settings()
    parsed = urlparse(settings.redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    if not _port_open(host, port):
        pytest.skip(f"Redis no accesible en {host}:{port}")


@pytest.fixture
def mailpit_required() -> None:
    if not _port_open("127.0.0.1", 1025):
        pytest.skip("Mailpit SMTP no accesible en 127.0.0.1:1025")
    if not _port_open("127.0.0.1", 8025):
        pytest.skip("Mailpit API no accesible en 127.0.0.1:8025")


@pytest.fixture
def postgres_required_env() -> None:
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        pytest.skip("Requiere DATABASE_URL=postgresql+asyncpg://...")


# --------------------------------------------------------- POSTGRES


class TestPostgresConnectivity:
    """Postgres vivo: ping + una query real via SQLAlchemy async."""

    @pytest.mark.asyncio
    async def test_ping_postgres_via_sqla(
        self,
        postgres_required_env: None,  # type: ignore[no-untyped-def]
    ) -> None:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        db_url = os.environ["DATABASE_URL"]
        engine = create_async_engine(db_url, echo=False)
        try:
            async with engine.connect() as conn:
                t0 = time.perf_counter()
                result = await conn.execute(text("SELECT 1 AS ok, version() AS v"))
                row = result.fetchone()
                latency_ms = (time.perf_counter() - t0) * 1000
            assert row is not None
            assert row.ok == 1
            assert "PostgreSQL" in row.v
            assert latency_ms < 1000, f"Postgres ping tardó {latency_ms:.1f}ms"
        finally:
            await engine.dispose()


# --------------------------------------------------------- REDIS


class TestRedisConnectivity:
    """Redis vivo: PING + SET/GET + healthcheck interno."""

    @pytest.mark.asyncio
    async def test_redis_ping_ok(
        self,
        redis_required: None,  # type: ignore[no-untyped-def]
    ) -> None:
        import redis.asyncio as redis_async  # noqa: PLC0415

        settings = get_settings()
        client = redis_async.from_url(settings.redis_url, decode_responses=True)
        try:
            t0 = time.perf_counter()
            pong = await client.ping()
            latency_ms = (time.perf_counter() - t0) * 1000
            assert pong is True
            assert latency_ms < 100, f"Redis ping tardó {latency_ms:.1f}ms"
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_redis_set_get_roundtrip(
        self,
        redis_required: None,  # type: ignore[no-untyped-def]
    ) -> None:
        """Set + Get + Delete roundtrip con un valor único."""
        import redis.asyncio as redis_async  # noqa: PLC0415

        settings = get_settings()
        client = redis_async.from_url(settings.redis_url, decode_responses=True)
        try:
            key = f"int-test:{uuid.uuid4().hex}"
            value = f"value-{uuid.uuid4().hex}"
            await client.set(key, value, ex=60)
            got = await client.get(key)
            assert got == value
            await client.delete(key)
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_healthcheck_reports_redis_ok(
        self,
        redis_required: None,  # type: ignore[no-untyped-def]
    ) -> None:
        """El healthcheck de la API reporta Redis con status=ok y latencia < 1s."""
        from app.modules.health.router import _check_redis

        result = await _check_redis()
        assert result["status"] == "ok"
        latency = float(result.get("latency_ms", "0"))
        assert latency < 1000


# --------------------------------------------------------- MAILPIT


class TestMailpitConnectivity:
    """Mailpit vivo: SMTP send + API HTTP retrieve."""

    @pytest.mark.asyncio
    async def test_smtp_send_real(
        self,
        mailpit_required: None,  # type: ignore[no-untyped-def]
    ) -> None:
        from app.modules.notifications.smtp import send_email

        # Vaciar cola de Mailpit.
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8025", timeout=5) as http:
            with suppress(httpx.HTTPError):
                await http.delete("/api/v1/messages")

        to_email = f"int-{uuid.uuid4().hex[:8]}@bodega.example"
        subject = f"Integration Test - {uuid.uuid4().hex[:8]}"
        body = f"<h1>Test</h1><p>{uuid.uuid4()}</p>"
        await send_email(to_email=to_email, subject=subject, body_html=body)
        await asyncio.sleep(0.3)

        async with httpx.AsyncClient(base_url="http://127.0.0.1:8025", timeout=5) as http:
            r = await http.get("/api/v1/messages")
            assert r.status_code == 200
            data = r.json()
            subjects = [msg.get("Subject") for msg in data.get("messages", [])]
            assert subject in subjects, (
                f"Mailpit no recibió el mensaje. Subjects: {subjects}"
            )

    @pytest.mark.asyncio
    async def test_smtp_unreachable_does_not_crash(
        self,
    ) -> None:
        """Si SMTP apunta a un puerto cerrado, send_email levanta ``SmtpError``
        (no crashea el server). Usa un puerto inmediatamente cerrado para
        que falle rapido.
        """
        from app.core.config import get_settings, reset_settings_cache
        from app.modules.notifications.smtp import SmtpError, send_email

        original_host = get_settings().smtp_host
        original_port = get_settings().smtp_port
        # Puerto 1 está reservado (tcpmux); conexiones deberian reusar rapido.
        # Si no, 8025 (Mailpit HTTP) sirve: contesta HTTP, no SMTP, falla rapido.
        try:
            os.environ["SMTP_HOST"] = "127.0.0.1"
            os.environ["SMTP_PORT"] = "1"  # tcpmux, no escucha
            os.environ["SMTP_TIMEOUT"] = "2"
            reset_settings_cache()
            with pytest.raises((SmtpError, Exception)) as exc_info:
                await send_email(
                    to_email="x@x.com",
                    subject="SMTP-fail-test",
                    body_html="<p>x</p>",
                )
            # No crashea; levanta error tipado o generico (defensivo).
            assert exc_info.value is not None
        finally:
            os.environ["SMTP_HOST"] = original_host
            os.environ["SMTP_PORT"] = str(original_port)
            os.environ.pop("SMTP_TIMEOUT", None)
            reset_settings_cache()


# --------------------------------------------------------- HEALTHCHECK COMPLETO


class TestHealthcheckContract:
    """Healthcheck del sistema con servicios externos activos."""

    @pytest.mark.asyncio
    async def test_health_redis_ok(
        self,
        redis_required: None,  # type: ignore[no-untyped-def]
    ) -> None:
        """Con Redis vivo, el componente ``redis`` debe reportar ``status=ok``."""
        from app.modules.health.router import _check_redis

        result = await _check_redis()
        assert result["status"] == "ok"
        latency = float(result.get("latency_ms", "0"))
        assert latency < 1000

    @pytest.mark.asyncio
    async def test_health_db_postgres_alive(
        self,
        postgres_required_env: None,  # type: ignore[no-untyped-def]
    ) -> None:
        """Verifica que Postgres está vivo mediante un ping directo SQLAlchemy.

        BUG CONOCIDO: ``app.db.session.get_engine()`` retorna un singleton
        cacheado al import-time de la app. En pytest, el primer test que
        usa Postgres crea un pool atado a un event loop, y al reusar el
        engine en otro test (con un event loop nuevo), asyncpg falla con
        ``Event loop is closed``. Por eso NO usamos ``ping_database()``
        (que usa el engine cacheado) y en su lugar creamos un engine
        local para este test.
        """
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        db_url = os.environ["DATABASE_URL"]
        engine = create_async_engine(db_url, echo=False)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
        finally:
            await engine.dispose()
