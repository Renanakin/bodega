"""
Tests E2E para ``CorrelationIdMiddleware`` (Deuda #6).

FIX Deuda #6: el middleware ahora es pure-ASGI (no usa
``BaseHTTPMiddleware``). Esto permite setear el header
``X-Correlation-ID`` en TODOS los responses, INCLUIDO los errores
500 generados por el exception handler de FastAPI.

Antes del fix: ``BaseHTTPMiddleware`` capturaba la excepcion en
``call_next`` y la re-lanzaba para que FastAPI generara el response.
Pero el response era creado FUERA del middleware, sin posibilidad
de setear headers. Resultado: en errores 500, el cliente no recibia
el ``X-Correlation-ID`` y no podia reportar el error correlacionado
con los logs del backend.

Despues del fix: el middleware intercepta el primer
``http.response.start`` de CUALQUIER response (incluso los del
exception handler) y agrega el header antes de que la app envie
los headers al cliente.

Tests cubiertos:
- 200 OK incluye X-Correlation-ID
- 404 incluye X-Correlation-ID
- 401 incluye X-Correlation-ID
- 422 (validation error) incluye X-Correlation-ID
- 500 (exception no manejada) incluye X-Correlation-ID
- correlation_id entrante se preserva (echo)
- correlation_id generado es un UUID valido
"""
from __future__ import annotations

import re
import unittest
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.middleware import (
    CorrelationIdMiddleware,
    exception_handler_with_correlation_id,
    install_correlation_handlers,
)


def _create_test_app() -> FastAPI:
    """Crea una app de test con el middleware + rutas que generan
    diferentes status codes (200, 404, 401, 422, 500).
    """
    app = FastAPI()
    install_correlation_handlers(app)

    @app.get("/ok")
    def ok():
        return {"status": "ok"}

    @app.get("/not-found")
    def not_found():
        raise HTTPException(status_code=404, detail="not here")

    @app.get("/unauthorized")
    def unauthorized():
        raise HTTPException(status_code=401, detail="no auth")

    @app.get("/validation-error/{x}")
    def validation_error(x: int):
        return {"x": x}

    @app.get("/boom")
    def boom():
        # Excepcion no manejada por el handler -> FastAPI genera 500.
        raise RuntimeError("kapow")

    return app


class CorrelationIdMiddlewareTestCase(unittest.TestCase):
    """Tests del header X-Correlation-ID en responses exitosos y de error."""

    def setUp(self) -> None:
        self.app = _create_test_app()
        # ``raise_server_exceptions=False`` evita que el TestClient
        # re-lance las excepciones de la app (las ve solo como
        # response 500 generado por el ServerErrorMiddleware).
        # Esto es lo que haria un cliente HTTP real (curl, browser)
        # que recibe un 500 sin ver la excepcion interna.
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def _assert_valid_correlation_id(self, value: str | None) -> None:
        """Helper: valida que el correlation_id sea un UUID valido."""
        self.assertIsNotNone(value, "X-Correlation-ID header ausente")
        # Acepta tanto uuid4 canonico (con guiones) como hex de 32 chars.
        self.assertTrue(
            re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", value)
            or re.match(r"^[0-9a-f]{32}$", value),
            f"X-Correlation-ID no es UUID valido: {value!r}",
        )

    def test_ok_response_includes_correlation_id(self) -> None:
        """200 OK: el header SIEMPRE debe estar presente."""
        response = self.client.get("/ok")
        self.assertEqual(response.status_code, 200)
        cid = response.headers.get("X-Correlation-ID")
        self._assert_valid_correlation_id(cid)

    def test_404_includes_correlation_id(self) -> None:
        """404 Not Found: el header debe estar presente."""
        response = self.client.get("/not-found")
        self.assertEqual(response.status_code, 404)
        cid = response.headers.get("X-Correlation-ID")
        self._assert_valid_correlation_id(cid)

    def test_401_includes_correlation_id(self) -> None:
        """401 Unauthorized: el header debe estar presente."""
        response = self.client.get("/unauthorized")
        self.assertEqual(response.status_code, 401)
        cid = response.headers.get("X-Correlation-ID")
        self._assert_valid_correlation_id(cid)

    def test_422_validation_error_includes_correlation_id(self) -> None:
        """422 Validation Error: el header debe estar presente."""
        # /validation-error/abc falla porque x espera int.
        response = self.client.get("/validation-error/abc")
        self.assertEqual(response.status_code, 422)
        cid = response.headers.get("X-Correlation-ID")
        self._assert_valid_correlation_id(cid)

    def test_500_internal_error_includes_correlation_id(self) -> None:
        """500 Internal Server Error (FIX Deuda #6): el header DEBE estar presente.

        Este es el test critico: ANTES del fix, el 500 NO tenia
        X-Correlation-ID porque el response era creado por el
        exception handler de FastAPI fuera del middleware. POST fix,
        el pure-ASGI middleware intercepta el http.response.start
        y agrega el header.
        """
        response = self.client.get("/boom")
        self.assertEqual(response.status_code, 500)
        cid = response.headers.get("X-Correlation-ID")
        # ESTA es la asercion clave: el header DEBE existir en 500.
        self.assertIsNotNone(
            cid,
            "FIX Deuda #6: X-Correlation-ID no se setea en responses 500. "
            "El pure-ASGI middleware debe interceptar http.response.start "
            "incluso cuando la app downstream levanto una excepcion.",
        )
        self._assert_valid_correlation_id(cid)

    def test_incoming_correlation_id_is_preserved(self) -> None:
        """Si el cliente envia X-Correlation-ID, el server lo eco (no genera uno nuevo)."""
        incoming = "11111111-2222-3333-4444-555555555555"
        response = self.client.get(
            "/ok",
            headers={"X-Correlation-ID": incoming},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("X-Correlation-ID"),
            incoming,
            "El correlation_id entrante debe ser preservado en el response.",
        )

    def test_generated_correlation_id_is_uuid(self) -> None:
        """Sin X-Correlation-ID entrante, el server genera un UUID v4 valido."""
        response = self.client.get("/ok")
        cid = response.headers.get("X-Correlation-ID")
        self._assert_valid_correlation_id(cid)
        # Verifica que es parseable como UUID
        UUID(cid)  # Raises ValueError si no es UUID valido


if __name__ == "__main__":
    unittest.main()
