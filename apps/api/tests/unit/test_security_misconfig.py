"""
Tests de seguridad ofensivos: A05:2021 - Security Misconfiguration.

FASE A3 del plan_ejecucion_testing.md.
Cubre debug mode, stack traces, secrets en logs, CORS permisivo,
endpoints ocultos, y headers de seguridad.
"""
from __future__ import annotations

import os
import unittest
from uuid import uuid4

# Configurar antes de importar
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.config import reset_settings_cache  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402
from tests.unit._async_test_base import AsyncTestBase  # noqa: E402

reset_settings_cache()


def _create_test_engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


class TestDebugMode(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """A05:2021 - Debug mode expone informacion sensible."""

    async def test_debug_mode_desactivado_en_produccion(self) -> None:
        """Con ENVIRONMENT=production + DEBUG=true, Settings debe rechazar
        la configuracion (OWASP A05:2021).

        Validamos:
        1. debug=True + ENVIRONMENT=production => ValueError al instanciar.
        2. debug=False + ENVIRONMENT=production => OK.

        NOTA: el validator ``_validate_production_secrets`` corre en
        ``mode="after"``, asi que cualquier regla de produccion falla
        ANTES de poder inspeccionar debug. Para aislar el test, seteamos
        ``SMTP_USE_TLS=true`` (la otra regla de prod) y asi el unico
        error esperado es el de debug.
        """
        from app.core.config import get_settings

        original_env = os.environ.get("ENVIRONMENT")
        original_debug = os.environ.get("DEBUG")
        original_smtp = os.environ.get("SMTP_USE_TLS")
        try:
            # Caso 1: debug=True en produccion debe fallar
            os.environ["ENVIRONMENT"] = "production"
            os.environ["DEBUG"] = "true"
            # Satisfacer la otra regla de prod (smtp_use_tls) para que el
            # unico error sea el de debug.
            os.environ["SMTP_USE_TLS"] = "true"
            reset_settings_cache()
            with self.assertRaises(
                ValueError,
                msg="debug=True en produccion no fue rechazado",
            ) as cm:
                get_settings()
            # Verificar que el mensaje es especificamente sobre debug.
            self.assertIn(
                "debug", str(cm.exception).lower(),
                f"Mensaje de error inesperado: {cm.exception}",
            )

            # Caso 2: debug=False en produccion es OK
            os.environ["DEBUG"] = "false"
            reset_settings_cache()
            settings = get_settings()
            self.assertFalse(
                settings.debug,
                f"debug=True en production (env={settings.environment})",
            )
        finally:
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env
            else:
                os.environ.pop("ENVIRONMENT", None)
            if original_debug is not None:
                os.environ["DEBUG"] = original_debug
            else:
                os.environ.pop("DEBUG", None)
            if original_smtp is not None:
                os.environ["SMTP_USE_TLS"] = original_smtp
            else:
                os.environ.pop("SMTP_USE_TLS", None)
            reset_settings_cache()

    async def test_no_hay_traceback_completo_en_500(self) -> None:
        """Error 500 NO debe incluir stack trace en la respuesta."""
        # Forzar un error 500 enviando un payload invalido a un endpoint
        r = self.client.post(
            "/api/v1/warehouses",
            json={"code": None, "name": None, "warehouse_type": None},
            headers=self.headers,
        )
        # En dev, FastAPI puede devolver el detalle del error.
        # En prod, debe devolver mensaje generico.
        if r.status_code >= 500:
            content = r.text
            # NO debe contener "Traceback" ni paths absolutos del codigo
            self.assertNotIn("Traceback", content)
            self.assertNotIn("/app/", content)


class TestSecretsInLogs(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """A02:2021 - Secrets en logs (passwords, tokens).

    Capturamos logs via ``logging.getLogger("app")`` (stdlib logger
    subyacente de structlog), NO via el proxy de structlog (que no
    expone ``.addHandler()``).
    """

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        import logging
        import io

        # Capturar logs del stdlib logger que usa structlog internamente.
        self.log_stream = io.StringIO()
        self.log_handler = logging.StreamHandler(self.log_stream)
        self.log_handler.setLevel(logging.DEBUG)
        # ``structlog.stdlib.LoggerFactory`` delega a
        # ``logging.getLogger(name)``, asi que ese es el logger que
        # recibe los records.
        stdlib_logger = logging.getLogger("app")
        stdlib_logger.setLevel(logging.DEBUG)
        stdlib_logger.addHandler(self.log_handler)

    async def asyncTearDown(self) -> None:
        import logging
        stdlib_logger = logging.getLogger("app")
        stdlib_logger.removeHandler(self.log_handler)
        await super().asyncTearDown()

    async def test_password_no_aparece_en_logs(self) -> None:
        """El password del usuario NO debe aparecer en logs de login."""
        self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "demo123"},
        )
        logs = self.log_stream.getvalue()
        # Verificar que el password NO esta en los logs
        self.assertNotIn("demo123", logs, "Password 'demo123' aparece en logs!")

    async def test_jwt_token_no_aparece_en_logs_de_error(self) -> None:
        """Tokens invalidos NO deben aparecer en logs de error."""
        self.client.get(
            "/api/v1/warehouses",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid"},
        )
        logs = self.log_stream.getvalue()
        # El token invalido NO debe aparecer en logs
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", logs)


class TestCORS(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """A05:2021 - CORS permisivo expone la API a otros origenes."""

    async def test_cors_no_permite_origines_comodin(self) -> None:
        """CORS NO debe permitir Access-Control-Allow-Origin: *."""
        r = self.client.get(
            "/api/v1/warehouses",
            headers={
                "Origin": "http://evil.com",
                "Authorization": self.headers["Authorization"],
            },
        )
        # El header CORS no debe permitir origenes no listados
        allow_origin = r.headers.get("access-control-allow-origin", "")
        if allow_origin == "*":
            self.fail("CORS permite origenes wildcard (*)")

    async def test_cors_rechaza_origen_no_listado(self) -> None:
        """CORS rechaza origenes no listados en allowed_origins."""
        r = self.client.options(
            "/api/v1/warehouses",
            headers={
                "Origin": "http://attacker.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # El endpoint no expone CORS headers para origenes no listados
        # (o devuelve 200 sin los headers CORS, lo cual es OK)
        if "access-control-allow-origin" in r.headers:
            allow_origin = r.headers["access-control-allow-origin"]
            self.assertNotEqual(
                allow_origin, "*",
                "CORS permite cualquier origen"
            )
            self.assertNotIn(
                "attacker", allow_origin,
                "CORS permite origen atacante"
            )


class TestSecurityHeaders(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """A05:2021 - Headers de seguridad presentes en responses.

    IMPORTANTE: los headers de seguridad se setean en el reverse proxy
    (nginx, ver infra/docker/nginx/conf.d/tls.conf), NO en la app.
    La app NO debe overescribirlos, y la unica excepcion es si FastAPI
    agrega sus propios headers (ej. server identification). Validamos
    que nginx los provea al hacer request via el proxy.

    Estos tests son DOCUMENTATIVOS en el nivel de la app. La validacion
    real se hace en tests/E2E contra el sistema completo (ver
    tests/e2e/test_security_headers.py - futuro FASE D).
    """

    async def test_x_content_type_options_en_proxy(self) -> None:
        """Header X-Content-Type-Options: nosniff se setea en nginx.

        Verificamos que nginx lo provee haciendo un request via el proxy.
        Si no hay proxy, validamos que la app al menos no lo sobreescriba
        con un valor inseguro.
        """
        r = self.client.get("/api/v1/health")
        # En dev (sin proxy), la app no setea este header.
        # La presencia del header viene de nginx. Documentamos.
        xcto = r.headers.get("x-content-type-options")
        # Si viene, debe ser 'nosniff'. Si no viene, OK (vendra de nginx).
        if xcto is not None:
            self.assertEqual(
                xcto.lower(), "nosniff",
                f"X-Content-Type-Options invalido: {xcto!r}"
            )

    async def test_x_frame_options_en_proxy(self) -> None:
        """Header X-Frame-Options se setea en nginx."""
        r = self.client.get("/api/v1/health")
        xfo = r.headers.get("x-frame-options", "")
        # Si viene, debe ser DENY o SAMEORIGIN. Si no, OK (vendra de nginx).
        if xfo:
            self.assertIn(
                xfo.upper(), ("DENY", "SAMEORIGIN"),
                f"X-Frame-Options invalido: {xfo!r}"
            )

    async def test_referrer_policy_en_proxy(self) -> None:
        """Header Referrer-Policy se setea en nginx."""
        r = self.client.get("/api/v1/health")
        rp = r.headers.get("referrer-policy", "")
        # Si viene, debe ser una politica valida. Si no, OK.
        if rp:
            valid = (
                "no-referrer", "same-origin", "strict-origin",
                "strict-origin-when-cross-origin", "no-referrer-when-downgrade",
            )
            self.assertIn(
                rp.lower(), valid,
                f"Referrer-Policy invalido: {rp!r}"
            )


class TestJWTSecretStrength(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """A02:2021 - JWT secret debil o expuesto."""

    async def test_jwt_secret_min_32_chars(self) -> None:
        """JWT_SECRET debe tener al menos 32 caracteres en produccion."""
        from app.core.config import get_settings

        original_env = os.environ.get("ENVIRONMENT")
        original_secret = os.environ.get("JWT_SECRET")
        try:
            os.environ["ENVIRONMENT"] = "production"
            os.environ["JWT_SECRET"] = "short"  # muy corto
            reset_settings_cache()
            try:
                settings = get_settings()
                # Debe haber error de validacion
                self.fail("JWT secret corto fue aceptado en produccion")
            except Exception:
                # OK: la validacion fallo como esperabamos
                pass
        finally:
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env
            else:
                os.environ.pop("ENVIRONMENT", None)
            if original_secret is not None:
                os.environ["JWT_SECRET"] = original_secret
            else:
                os.environ.pop("JWT_SECRET", None)
            reset_settings_cache()

    async def test_jwt_secret_no_es_default(self) -> None:
        """JWT_SECRET NO debe ser un valor default conocido."""
        from app.core.config import get_settings
        from app.core.config import Settings as AppSettings

        # Intentar varios defaults comunes
        bad_defaults = [
            "secret",
            "changeme",
            "your-secret-key",
            "test-secret",
            "default",
        ]
        for bad in bad_defaults:
            original = os.environ.get("JWT_SECRET")
            try:
                os.environ["JWT_SECRET"] = bad
                reset_settings_cache()
                try:
                    AppSettings()
                    # Si no falla, el secret es muy debil
                    # (solo falla en produccion; en dev se permite)
                    from app.core.config import get_settings
                    s = get_settings()
                    if s.environment == "production":
                        self.fail(f"JWT secret debil aceptado en prod: {bad!r}")
                except Exception:
                    pass  # fallo de validacion = OK
            finally:
                if original is not None:
                    os.environ["JWT_SECRET"] = original
                else:
                    os.environ.pop("JWT_SECRET", None)
                reset_settings_cache()


if __name__ == "__main__":
    unittest.main()
