"""
Tests unitarios para observabilidad Fase 9 (Fase 9: structlog + middleware).

Cubre:
- ``configure_logging`` no falla y es idempotente.
- structlog emite JSON en produccion y console en dev.
- ``correlation_id`` se inyecta en cada log.
- ``CorrelationIdMiddleware`` setea X-Correlation-ID en el response.
- ``CorrelationIdMiddleware`` acepta X-Correlation-ID entrante (idempotente).
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import (
    _logging_configured,
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)
from app.core.middleware import CorrelationIdMiddleware


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_logging_state() -> Iterator[None]:
    """Reset del estado global de structlog entre tests.

    Importante: ``configure_logging`` es idempotente (no-op si ya esta
    configurado), pero en tests queremos poder reconfigurar el formato
    (JSON vs console) segun el caso. Por eso reseteamos el flag.
    """
    import app.core.logging as logging_mod

    logging_mod._logging_configured = False
    structlog.contextvars.clear_contextvars()
    yield
    # Cleanup post-test
    logging_mod._logging_configured = False
    structlog.contextvars.clear_contextvars()


class TestConfigureLogging:
    """``configure_logging()`` no falla y configura los processors esperados."""

    def test_configure_logging_no_falla(self, env_development: None) -> None:
        """Llamar configure_logging() no debe lanzar excepciones."""
        configure_logging()
        # Verificar que structlog tiene processors configurados
        cfg = structlog.get_config()
        assert cfg is not None
        assert len(cfg["processors"]) > 0

    def test_configure_logging_es_idempotente(self, env_development: None) -> None:
        """Llamar configure_logging() N veces no duplica processors."""
        configure_logging()
        cfg1 = structlog.get_config()
        n1 = len(cfg1["processors"])
        configure_logging()
        configure_logging()
        cfg2 = structlog.get_config()
        n2 = len(cfg2["processors"])
        assert n1 == n2, "configure_logging() no es idempotente"

    def test_logger_returns_bound_logger(self) -> None:
        """``get_logger(name)`` retorna un BoundLogger de structlog."""
        log = get_logger("test.module")
        assert log is not None
        assert hasattr(log, "info")
        assert hasattr(log, "error")
        assert hasattr(log, "warning")


class TestLogFormat:
    """Formato de log: JSON en production, console en dev.

    Nota: con ``structlog.stdlib.LoggerFactory()``, los logs fluyen por
    stdlib ``logging``, asi que usamos ``caplog`` para capturarlos.
    Para el test de produccion (JSON), capturamos via ``caplog`` y
    parseamos el ``record.message`` (que es el output del JSONRenderer
    aplicado a la cadena por ``logging.basicConfig(format='%(message)s')``).
    """

    def test_structlog_emite_console_en_dev(
        self, env_development: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """En dev (ENVIRONMENT=development) los logs usan ConsoleRenderer."""
        configure_logging()
        log = get_logger("test.dev")
        with caplog.at_level(logging.DEBUG, logger="test.dev"):
            log.info("test.event", foo="bar")
        # Buscar el record por nombre
        records = [r for r in caplog.records if r.name == "test.dev"]
        assert len(records) >= 1
        msg = records[-1].getMessage()
        # El ConsoleRenderer emite el evento y los key=value
        assert "test.event" in msg
        assert "foo" in msg
        assert "bar" in msg

    def test_structlog_emite_json_en_produccion(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """En production (ENVIRONMENT=production) los logs son JSON.

        Forzamos ENVIRONMENT=production + reload de settings, capturamos
        via caplog y verificamos que el mensaje es JSON parseable.
        """
        monkeypatch.setenv("ENVIRONMENT", "production")
        # Fase 10 hardening: production requiere SECRET_KEY (defense in depth)
        # y SMTP_USE_TLS=true. Sin estos, el model_validator de Settings rechaza
        # la configuracion. Seteamos los valores minimos para que el test
        # pueda enfocarse en el formato de log.
        monkeypatch.setenv("SECRET_KEY", "x" * 32)
        monkeypatch.setenv("SMTP_USE_TLS", "true")
        from app.core.config import reset_settings_cache

        reset_settings_cache()
        configure_logging()

        log = get_logger("test.prod")
        with caplog.at_level(logging.DEBUG, logger="test.prod"):
            log.info("test.prod_event", user_id="user-42", action="login")

        records = [r for r in caplog.records if r.name == "test.prod"]
        assert len(records) >= 1
        # El mensaje es JSON (porque JSONRenderer produce una sola linea JSON
        # y basicConfig usa format="%(message)s" que lo deja intacto).
        msg = records[-1].getMessage()
        data = json.loads(msg)
        assert data["event"] == "test.prod_event"
        assert data["user_id"] == "user-42"
        assert data["action"] == "login"
        # En production, el log debe incluir timestamp ISO
        assert "timestamp" in data
        # El nivel debe ser 'info'
        assert data["level"] == "info"


class TestCorrelationId:
    """``correlation_id`` se inyecta automaticamente en cada log."""

    def test_correlation_id_se_agrega_a_logs(
        self, env_development: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Al bindear correlation_id al contexto, aparece en cada log."""
        configure_logging()
        bind_request_context(request_id="abc-123-def-456", user_id="user-42")
        log = get_logger("test.corr")
        with caplog.at_level(logging.DEBUG, logger="test.corr"):
            log.info("test.correlation_event", payload="hello")
        records = [r for r in caplog.records if r.name == "test.corr"]
        assert len(records) >= 1
        msg = records[-1].getMessage()
        # correlation_id (o su alias request_id) debe estar en el output
        assert "abc-123-def-456" in msg, (
            f"correlation_id no aparece en log: {msg!r}"
        )

    def test_correlation_id_se_limpia_con_clear(self, env_development: None) -> None:
        """``clear_request_context()`` remueve correlation_id y user_id del contexto."""
        configure_logging()
        bind_request_context(request_id="test-id", user_id="user-1")
        # Confirmar que esta bindeado
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("correlation_id") == "test-id"
        assert ctx.get("user_id") == "user-1"
        # Limpiar
        clear_request_context()
        ctx = structlog.contextvars.get_contextvars()
        assert ctx.get("correlation_id") is None
        assert ctx.get("user_id") is None


class TestCorrelationIdMiddleware:
    """CorrelationIdMiddleware gestiona X-Correlation-ID y logging."""

    def _build_app(self) -> FastAPI:
        """Helper: construir una app FastAPI minima con el middleware."""
        app = FastAPI()
        app.add_middleware(CorrelationIdMiddleware)

        @app.get("/ping")
        async def ping() -> dict[str, str]:
            return {"pong": "ok"}

        @app.get("/raise")
        async def raise_endpoint() -> dict[str, str]:
            raise RuntimeError("boom")

        return app

    def test_correlation_id_se_devuelve_en_response_header(self) -> None:
        """El response debe incluir X-Correlation-ID (generado si no vino)."""
        app = self._build_app()
        client = TestClient(app, raise_server_exceptions=True)
        response = client.get("/ping")
        assert response.status_code == 200
        # Header X-Correlation-ID debe existir y ser un UUID
        assert "X-Correlation-ID" in response.headers
        cid = response.headers["X-Correlation-ID"]
        assert len(cid) > 0
        # Verificar que es un UUID valido (importamos structlog's uuid)
        import uuid as uuid_mod

        uuid_mod.UUID(cid)  # raises if invalid

    def test_correlation_id_se_preserva_si_viene_en_request(self) -> None:
        """Si el request trae X-Correlation-ID, el middleware lo respeta."""
        app = self._build_app()
        client = TestClient(app, raise_server_exceptions=True)
        sent_id = "11111111-2222-3333-4444-555555555555"
        response = client.get("/ping", headers={"X-Correlation-ID": sent_id})
        assert response.status_code == 200
        # El mismo correlation_id debe volver en el response
        assert response.headers["X-Correlation-ID"] == sent_id

    def test_correlation_id_se_loguea_en_errores(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Cuando un handler lanza excepcion, se loguea ``request.failed``
        con el correlation_id (para trazabilidad del error)."""
        app = self._build_app()
        client = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level(logging.WARNING):
            response = client.get("/raise", headers={"X-Correlation-ID": "err-trace-id-9999"})
        # El status es 500 (handler rompio)
        assert response.status_code == 500
        # El log de request.failed debe incluir el correlation_id que
        # enviamos. Esto es lo que permite a ops rastrear el error
        # en el log de produccion.
        failed_logs = [
            r for r in caplog.records
            if r.name == "app.core.middleware" and "request.failed" in r.getMessage()
        ]
        assert len(failed_logs) >= 1
        msg = failed_logs[-1].getMessage()
        assert "err-trace-id-9999" in msg, (
            f"correlation_id no aparece en log de error: {msg!r}"
        )
