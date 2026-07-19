"""
Logging profesional con structlog (Regla de Oro R8 + Fase 9).

Refinamientos Fase 9 (alineado con la spec del prompt):
- Renombre estandar a ``correlation_id`` (W3C / OpenTelemetry) + alias
  ``request_id`` para mantener compat con callers previos.
- Procesadores extra: ``add_logger_name`` (modulo en cada log),
  ``UnicodeDecoder`` (utf-8 seguro), ``format_exc_info`` (stacktrace
  completo en excepciones), ``StackInfoRenderer`` (stack de Python si
  ``stack_info=True``).
- Filtro bound logger por nivel: el wrapper_class ``make_filtering_bound_logger``
  descarta logs por debajo del nivel configurado ANTES de procesar, evitando
  overhead en hot path.
- ``cache_logger_on_first_use=True`` (cero overhead en hot path).
- Idempotente: configurar N veces no duplica processors (chequea flag).
- Nivel de log configurable via ``settings.log_level`` (env ``LOG_LEVEL``).

Prohibido usar ``print()`` en codigo de produccion (R8).
Cada log incluye contexto automatico: ``correlation_id``, ``user_id``,
``entity_id`` cuando aplique.

API publica (estable desde Fase 0):
    - ``configure_logging()`` - llamar una vez al arrancar la app.
    - ``get_logger(name)`` - logger estructurado por modulo.
    - ``bind_request_context(request_id, user_id)`` - setea contexto.
    - ``clear_request_context()`` - limpia contexto.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import get_settings


# --- Contexto (R8) -----------------------------------------------------------

# ContextVar propio para request_id / user_id. Se mantienen para que
# ``bind_request_context`` / ``clear_request_context`` sigan funcionando en
# modulos previos (Fase 0-8). Tambien se bindea a ``structlog.contextvars``
# para que el processor ``merge_contextvars`` los inyecte automaticamente.
_correlation_id_ctx: ContextVar[str | None] = ContextVar(
    "correlation_id", default=None
)
_user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)

# Flag de idempotencia (ver configure_logging).
_logging_configured: bool = False


def _add_context_vars(
    _: Any, method_name: str, event_dict: EventDict  # noqa: ARG001
) -> EventDict:
    """Inyecta ``correlation_id`` y ``user_id`` desde el ContextVar propio.

    Si structlog.contextvars ya tiene los valores (via
    ``structlog.contextvars.bind_contextvars``), este processor es un
    no-op para esas claves (no las sobreescribe).

    Tambien expone ``request_id`` como alias de ``correlation_id`` para
    compatibilidad con callers que ya loguean ``request_id=...`` (Fase 0-8).
    """
    cid = _correlation_id_ctx.get()
    uid = _user_id_ctx.get()
    if cid and "correlation_id" not in event_dict:
        event_dict["correlation_id"] = cid
        # Alias retro-compat: muchos modulos (Fase 0-8) leen ``request_id``
        # en logs estructurados. Mantenemos ambos nombres.
        event_dict.setdefault("request_id", cid)
    if uid and "user_id" not in event_dict:
        event_dict["user_id"] = uid
    return event_dict


def _resolve_log_level(level_name: str) -> int:
    """Resuelve el nombre del nivel a su valor numerico.

    Acepta ``"INFO"`` / ``"info"`` / ``"WARNING"`` (case-insensitive).
    Si el nombre es invalido, cae a INFO (fail-safe, loguea un warning).
    """
    level = logging.getLevelName(str(level_name).upper())
    if not isinstance(level, int):
        logging.getLogger(__name__).warning(
            "logging.invalid_log_level_fallback",
            requested=level_name,
            fallback="INFO",
        )
        return logging.INFO
    return level


def configure_logging() -> None:
    """Configura structlog y stdlib logging. Llamar una sola vez al arrancar.

    Es idempotente: llamarla N veces deja un solo set de processors
    (controlado por ``_logging_configured``).

    Comportamiento:
    - Produccion: JSON a stdout (parseable por Datadog/Loki/etc).
    - Desarrollo: texto coloreado a stderr (legible en consola).
    - Nivel de log segun ``settings.log_level`` (env ``LOG_LEVEL``).
    - Loggers ruidosos (``uvicorn.access``, ``sqlalchemy.engine``,
      ``asyncio``) se silencian en production para no contaminar logs
      estructurados.
    """
    global _logging_configured
    if _logging_configured:
        return

    settings = get_settings()
    log_level_int = _resolve_log_level(settings.log_level)

    # Processors compartidos (orden importa: contextvars se mergea PRIMERO
    # para que el resto de los processors puedan ver correlation_id).
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # correlation_id, user_id (structlog)
        _add_context_vars,  # correlation_id, user_id (legacy ContextVar)
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Renderer segun entorno.
    if settings.is_production:
        # JSON puro: stdout para que docker/kubernetes lo capturen.
        renderer: Processor = structlog.processors.JSONRenderer()
        stream = sys.stdout
    else:
        # Consola coloreada: stderr para no contaminar stdout de tests
        # que a veces leen stdout para asserts.
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        stream = sys.stderr

    structlog.configure(
        processors=[
            *shared_processors,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
        context_class=dict,
        # ``structlog.stdlib.LoggerFactory`` retorna loggers de stdlib
        # (con atributo ``.name``) en vez de ``PrintLogger`` puro. Esto
        # es necesario para que ``structlog.stdlib.add_logger_name``
        # funcione, y ademas permite que ``logging.basicConfig()`` abajo
        # capture los logs via stdlib (util para ``caplog`` en tests).
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Redirigir logs de stdlib (uvicorn, sqlalchemy, asyncio) a structlog.
    logging.basicConfig(
        format="%(message)s",
        stream=stream,
        level=log_level_int,
    )

    # Silenciar loggers ruidosos en production; en dev dejar visibles
    # para debugging. ``uvicorn.access`` se mantiene (logs de requests
    # en production son valiosos, pero a nivel WARNING para no duplicar
    # con nuestro middleware de request logging).
    noisy_in_prod = ("sqlalchemy.engine", "asyncio", "urllib3")
    noisy_in_dev = ("sqlalchemy.engine.Engine",)  # muy verboso
    for logger_name in noisy_in_prod:
        logging.getLogger(logger_name).setLevel(
            logging.WARNING if settings.is_production else logging.INFO
        )
    for logger_name in noisy_in_dev:
        if not settings.is_production:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
    # uvicorn.access: en production NO queremos duplicar el log de cada
    # request (ya lo emite nuestro CorrelationIdMiddleware con info
    # adicional como correlation_id, elapsed_ms, etc).
    logging.getLogger("uvicorn.access").setLevel(
        logging.WARNING if settings.is_production else logging.INFO
    )

    _logging_configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Obtiene un logger estructurado.

    Uso:
        from app.core.logging import get_logger
        log = get_logger(__name__)
        log.info("user.created", user_id=str(user.id), email=user.email)
    """
    return structlog.get_logger(name)


def bind_request_context(
    request_id: str, user_id: str | None = None
) -> None:
    """Vincula ``request_id`` (alias de correlation_id) y ``user_id`` al contexto.

    Setea tanto el ContextVar propio (``_correlation_id_ctx`` /
    ``_user_id_ctx``) como el de structlog (``structlog.contextvars``)
    para que el processor ``merge_contextvars`` los inyecte
    automaticamente en cada log.

    Args:
        request_id: ID de trazabilidad (UUID v4 tipicamente). Se expone
            como ``correlation_id`` y ``request_id`` (alias retro-compat).
        user_id: ID del usuario autenticado (o None).
    """
    _correlation_id_ctx.set(request_id)
    _user_id_ctx.set(user_id)
    structlog.contextvars.bind_contextvars(
        correlation_id=request_id, request_id=request_id, user_id=user_id
    )


def clear_request_context() -> None:
    """Limpia el contexto al final del request.

    Reinicia tanto los ContextVar propios como los de structlog.
    """
    _correlation_id_ctx.set(None)
    _user_id_ctx.set(None)
    structlog.contextvars.unbind_contextvars(
        "correlation_id", "request_id", "user_id"
    )


def get_request_id() -> str | None:
    """Retorna el correlation_id actual del contexto (o None si no hay).

    Usado por el exception handler global de ``CorrelationIdMiddleware``
    para inyectar el header ``X-Correlation-ID`` en responses 500
    generados por el exception handler de FastAPI (FIX Deuda #6).
    """
    return _correlation_id_ctx.get()
