"""
Middleware de logging y trazabilidad de requests (Regla de Oro R8 + Fase 9).

Cada request HTTP se loguea con: method, path, status, duration_ms,
correlation_id. El ``correlation_id`` se propaga a traves del ContextVar
para que todos los logs del request (en cualquier modulo) lo incluyan
automaticamente, y se devuelve en el response header ``X-Correlation-ID``
para que el cliente pueda correlacionar logs frontend <-> backend.

FIX Deuda #6: pure-ASGI middleware (en lugar de ``BaseHTTPMiddleware``).
El bug original era que ``BaseHTTPMiddleware`` no permite setear headers
en el response cuando ``call_next`` levanta una excepcion: el response
es creado LUEGO por el exception handler de FastAPI, fuera del control
del middleware. La solucion es implementar el protocolo ASGI directo:
interceptamos el primer ``send({"type": "http.response.start"})`` y le
agregamos el header ``X-Correlation-ID`` ANTES de que la app envie
los headers originales. Asi el header aparece en TODOS los responses,
incluyendo errores 500 del exception handler.

Refinamientos Fase 9:
- Renombre a ``CorrelationIdMiddleware`` (el nombre del header HTTP es
  ``X-Correlation-ID``, estandar W3C / OpenTelemetry).
- Acepta ``X-Correlation-ID`` del request entrante; si no viene, genera
  uno con ``uuid.uuid4()``.
- Log de exito incluye ``status_code`` (estandar) + ``elapsed_ms``.
- Log de error usa ``log.exception`` (captura traceback) y se relanza
  para que el exception handler de FastAPI lo procese.
- Limpia el contexto AL FINAL siempre (incluso en excepciones) para no
  contaminar el siguiente request.
- Header de respuesta ``X-Correlation-ID`` se setea SIEMPRE, incluso
  en errores 500 (verificado por test E2E).
"""

from __future__ import annotations

import time
import uuid

import structlog
from app.core.logging import bind_request_context, clear_request_context, get_request_id
from fastapi import Request, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger(__name__)


class CorrelationIdMiddleware:
    """Pure-ASGI middleware: gestiona correlation_id + logging de request/response.

    Implementa el protocolo ASGI directamente (no usa ``BaseHTTPMiddleware``)
    para tener control total sobre el ``send`` callback. Esto permite
    setear el header ``X-Correlation-ID`` en el response INCLUSO cuando
    el handler levanta una excepcion y FastAPI genera un response 500
    via su exception handler (FIX Deuda #6).

    Flujo por request:
        1. Lee ``X-Correlation-ID`` del request entrante. Si no existe,
           genera uno con ``uuid.uuid4()``.
        2. Bind el correlation_id al context de structlog para que
           todos los logs del request lo incluyan.
        3. Mide latencia con ``time.perf_counter()``.
        4. Envia el request a la app downstream con un wrapper de
           ``send`` que intercepta el primer ``http.response.start``
           y agrega el header ``X-Correlation-ID``.
        5. Loguea ``request.completed`` o ``request.failed``.
        6. Limpia el contexto para no contaminar el siguiente request.
    """

    HEADER = "X-Correlation-ID"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # Solo interceptamos HTTP; el resto (lifespan, websocket)
            # pasa directo.
            await self.app(scope, receive, send)
            return

        # 1. Extraer o generar correlation_id
        # En ASGI, scope["headers"] es una lista de tuplas (bytes, bytes).
        correlation_id: str | None = None
        for name, value in scope.get("headers", []):
            # headers son (bytes, bytes)
            if name.decode("latin-1").lower() == self.HEADER.lower():
                correlation_id = value.decode("latin-1")
                break
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        bind_request_context(request_id=correlation_id)

        # 2. Medir latencia
        start = time.perf_counter()
        status_code: int | None = None

        # 3. Wrapper de send que intercepta el primer http.response.start
        # y agrega el header X-Correlation-ID. Tambien captura el
        # status_code para logging.
        response_started = False

        async def send_with_correlation_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start" and not response_started:
                response_started = True
                status_code = message["status"]
                # Agregar (o sobreescribir) el header X-Correlation-ID
                # en la lista de headers del response.
                raw_headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                # Filtrar el header existente (si viene del cliente) y agregar el nuestro.
                filtered = [
                    (k, v)
                    for k, v in raw_headers
                    if k.decode("latin-1").lower() != self.HEADER.lower()
                ]
                filtered.append((self.HEADER.encode("latin-1"), correlation_id.encode("latin-1")))
                message["headers"] = filtered
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_id)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            log.exception(
                "request.failed",
                method=scope.get("method", "?"),
                path=scope.get("path", "?"),
                client_ip=_client_ip(scope),
                elapsed_ms=elapsed_ms,
                error_type=type(exc).__name__,
            )
            # FIX Deuda #6: re-lanzamos para que el ``ServerErrorMiddleware``
            # (mas externo en la chain ASGI) capture la excepcion y
            # genere un response 500. El exception handler global
            # registrado en ``create_app`` (apps/api/app/main.py) se
            # encarga de setear ``X-Correlation-ID`` en ese response 500.
            #
            # IMPORTANTE: NO limpiamos el contexto aca. El exception
            # handler (``exception_handler_with_correlation_id``) lo
            # lee via ``get_request_id()`` para setear el header. Si
            # limpiamos aca, el handler no encontraria el correlation_id
            # y el response 500 quedaria sin el header.
            #
            # La limpieza se hace en el exception handler (o al final
            # del bloque try/else, si no hubo excepcion).
            raise
        else:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            log.info(
                "request.completed",
                method=scope.get("method", "?"),
                path=scope.get("path", "?"),
                status=status_code or 0,
                client_ip=_client_ip(scope),
                elapsed_ms=elapsed_ms,
            )
            # Limpiar contexto solo si NO hubo excepcion (en ese caso,
            # el exception handler ya lo limpia).
            clear_request_context()


def _client_ip(scope: Scope) -> str | None:
    """Extrae la IP del cliente del scope ASGI, tolerando clientes ausentes."""
    client = scope.get("client")
    if client is None:
        return None
    if isinstance(client, tuple) and len(client) >= 1:
        return str(client[0])
    return None


# =============================================================================
# Exception handler global (FIX Deuda #6)
# =============================================================================
# El ``ServerErrorMiddleware`` de Starlette (mas externo que
# ``CorrelationIdMiddleware`` en la chain ASGI) captura las excepciones
# no manejadas y genera un response 500. Ese response NO pasa por nuestro
# ``send_wrapper`` (porque nosotros somos mas internos), asi que el
# header ``X-Correlation-ID`` no se setea. Solucion: registrar un
# exception handler global que setea el header en el response 500 cuando
# el ``ServerErrorMiddleware`` lo procesa.


async def exception_handler_with_correlation_id(_request: Request, _exc: Exception) -> Response:
    """Exception handler global que setea ``X-Correlation-ID`` en el response.

    Se registra para ``Exception`` (catch-all) en ``create_app`` via
    ``app.add_exception_handler(Exception, exception_handler_with_correlation_id)``.
    Cuando una excepcion no manejada se propaga al ``ServerErrorMiddleware``,
    este handler la intercepta y personaliza el response 500 agregando
    el header ``X-Correlation-ID`` (FIX Deuda #6).

    Tambien limpia el ContextVar de correlation_id para no contaminar
    el siguiente request (el middleware no lo limpia cuando hay
    excepcion porque re-lanza, ver el docstring de ``__call__``).
    """
    from fastapi.responses import JSONResponse

    correlation_id = get_request_id()
    headers: dict[str, str] = {}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    # Limpiar contexto DESPUES de leerlo (no antes, sino el header
    # tendria value None).
    clear_request_context()
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
        headers=headers,
    )


async def sqlite_integrity_error_handler(_request: Request, exc: Exception) -> Response:
    """Handler especifico para ``sqlite3.IntegrityError``.

    Convierte el error 500 en un 422 (Unprocessable Entity) con el mensaje
    del constraint violated, para que la UI muestre algo util en vez de
    "Internal Server Error".

    Aplica a CHECK constraints (ej. ``warehouse_type`` invalido, falta
    ``parent_warehouse_id`` para ``mecanico_box``) y UNIQUE constraints
    (ej. ``code`` duplicado).
    """
    import sqlite3

    from fastapi.responses import JSONResponse

    correlation_id = get_request_id()
    headers: dict[str, str] = {}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    clear_request_context()

    raw = str(exc) if isinstance(exc, sqlite3.IntegrityError) else str(exc)
    # ``sqlite3.IntegrityError`` con check_same_thread=False a veces trae
    # un mensaje generico tipo "CHECK constraint failed: ...". Devolvemos
    # el texto tal cual para que la UI lo muestre.
    if "CHECK constraint failed" in raw:
        detail_code = "check_constraint_violated"
    elif "UNIQUE constraint failed" in raw:
        detail_code = "unique_constraint_violated"
    else:
        detail_code = "integrity_error"

    return JSONResponse(
        status_code=422,
        content={"detail": {"code": detail_code, "message": raw}},
        headers=headers,
    )


def install_correlation_handlers(app: ASGIApp) -> None:
    """Registra el middleware y el exception handler en una app FastAPI.

    Helper para usar en ``create_app``:
        install_correlation_handlers(app)

    Equivale a:
        app.add_middleware(CorrelationIdMiddleware)
        app.add_exception_handler(Exception, exception_handler_with_correlation_id)
    """
    # ``add_middleware`` agrega al final de la lista; en Starlette
    # el orden de ejecucion es inverso al de la lista, asi que
    # ``CorrelationIdMiddleware`` se ejecuta DESPUES de
    # ``ServerErrorMiddleware`` (mas interno). Eso significa que
    # las exceptions de la app NO se ven afectadas por nuestro
    # try/except del middleware; se propagan al ServerErrorMiddleware.
    if hasattr(app, "add_middleware"):
        app.add_middleware(CorrelationIdMiddleware)
    if hasattr(app, "add_exception_handler"):
        # El handler especifico se registra ANTES del catch-all para que
        # FastAPI matchee por especificidad (subclase de Exception).
        import sqlite3

        app.add_exception_handler(sqlite3.IntegrityError, sqlite_integrity_error_handler)
        app.add_exception_handler(Exception, exception_handler_with_correlation_id)


# --- Backward-compat (Fase 0-9) --------------------------------------------
# Algunos modulos previos importaban ``RequestLoggingMiddleware`` (nombre
# original de Fase 0-8). Ahora es un alias del nuevo pure-ASGI middleware.
RequestLoggingMiddleware = CorrelationIdMiddleware
