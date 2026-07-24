"""
Entry point de la aplicación FastAPI.

Aplica las Reglas de Oro:
- R3: la lógica vive en módulos; main.py es solo ensamblaje.
- R4: no hay lógica de negocio aquí.
- R8: middleware de logging y Sentry configurados al arranque.
- R9 (Fase 9): observabilidad operativa (correlation_id, Prometheus,
  Sentry, healthcheck ampliado).

Backend de BD (ADR-0001):
- Si se pasa `db_path` explícito (caso típico de tests) → legacy sync SQLite.
- Si no, se lee `database_url` de Settings:
    * `postgresql+asyncpg://`  → backend Postgres (target de Fase 1).
    * `sqlite://`              → backend SQLite (compat).
    * `None`/vacío             → default legacy SQLite file.
- El backend activo se loguea al arranque (R8: observabilidad).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import DomainError, domain_error_handler
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    install_correlation_handlers,
)

# Configurar logging ANTES de instanciar la app (R8)
configure_logging()
log = get_logger(__name__)


def _init_sentry() -> None:
    """Inicializa Sentry si hay DSN configurado.

    - Si ``settings.sentry_dsn`` esta vacio, no hace nada (Sentry es
      opcional; environments de dev no lo necesitan).
    - Si esta configurado, captura excepciones no manejadas con
      stacktrace, request context, user context, etc.
    - Sentry se inicializa UNA vez por proceso (sentry_sdk.init es
      idempotente y descarta llamadas repetidas).
    """
    settings = get_settings()
    if not settings.sentry_dsn:
        log.info(
            "sentry.disabled",
            reason="sentry_dsn vacio",
        )
        return

    try:
        import sentry_sdk  # noqa: PLC0415
        from sentry_sdk.integrations.fastapi import (  # noqa: PLC0415
            FastApiIntegration,
        )
        from sentry_sdk.integrations.starlette import (  # noqa: PLC0415
            StarletteIntegration,
        )
    except ImportError:
        log.warning("sentry.disabled", reason="sentry-sdk no instalado")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.environment,
        release=settings.app_version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        integrations=[
            FastApiIntegration(),
            StarletteIntegration(),
        ],
        # No capturar PII (emails, IPs) en production por compliance.
        send_default_pii=False,
    )
    log.info(
        "sentry.enabled",
        environment=settings.sentry_environment or settings.environment,
        release=settings.app_version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """Lifespan context: startup/shutdown hooks.

    Args:
        app: instancia de FastAPI (requerido por signature, no se usa directamente).
    """
    log.info(
        "app.starting",
        environment=get_settings().environment,
        version=get_settings().app_version,
    )
    # FIX Fase 5+: ya no hay rama ``sqlite_legacy``. El schema async se
    # inicializa siempre via ``init_async_schema`` (idempotente) si el
    # engine async esta activo. En Postgres/SQLite async dejamos que
    # Alembic sea el unico source of truth del schema en produccion;
    # este create_all es un bootstrap para dev/test.
    if getattr(app.state, "async_engine_initialized", False):
        from app.db.session import init_async_schema  # noqa: PLC0415

        await init_async_schema()
    yield
    log.info("app.shutdown")


def _resolve_backend(db_path: str | None = None) -> tuple[str, str]:
    """Decide qué backend de BD usar y devuelve (backend_name, detail).

    Returns:
        Tupla (backend, detail) donde:
        - backend ∈ {"sqlite", "postgres"}
        - detail es el path o URL (sin credenciales) para logging.

    El parametro ``db_path`` se mantiene por compat historica con tests
    que pasaban ``create_app(db_path=":memory:")``. En Fase 5+ se ignora:
    el backend siempre se decide por ``settings.database_url`` o, en su
    defecto, por el path por defecto (legacy sync ya no existe).
    """
    settings = get_settings()

    # DATABASE_URL define postgres → backend target de Fase 1.
    if settings.db_backend == "postgres":
        from app.db.session import _redact_url

        # settings.database_url es no-None en este branch (db_backend=="postgres"
        # lo garantiza), pero mypy no lo sabe. ``str(...)`` es seguro.
        db_url = settings.database_url or ""
        return "postgres", _redact_url(db_url)

    # Cualquier otro caso: backend SQLite async.
    return "sqlite", settings.database_url or "(default in-memory)"


def create_app(db_path: str | None = None) -> FastAPI:  # noqa: ARG001
    """Factory de la aplicación FastAPI.

    Args:
        db_path: DEPRECATED. Se mantiene por compat historica con
            tests que pasaban ``create_app(db_path=":memory:")``. En
            Fase 5+ se ignora: el backend siempre se decide por
            ``settings.database_url``.

    Returns:
        App FastAPI lista para `uvicorn app.main:app`.
    """
    settings = get_settings()
    backend, backend_detail = _resolve_backend(db_path)

    # Loguear SIEMPRE qué backend se está usando (R8: observabilidad).
    log.info(
        "app.backend_selected",
        backend=backend,
        detail=backend_detail,
        environment=settings.environment,
    )

    # BUG 13 (fix 2026-07-23): redirect_slashes=False en la app raiz
    # y en el api_router. Ver apps/api/app/modules/ordenes_compra/router.py
    # para el contexto completo. Es un safety net global: cuando un
    # cliente olvida el trailing slash, Starlette responde 307 (redirect)
    # que puede enmascarar errores. Con redirect_slashes=False, el 404
    # es limpio.
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    # CORS (R1: orígenes desde Settings, no hardcoded)
    # ``expose_headers`` incluye ``X-Correlation-ID`` para que el browser
    # pueda leerlo y reportarlo en errores de frontend.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Request-ID"],
    )

    # R8+R9: middleware de logging con correlation_id (request_id, latencia,
    # errores). Va DESPUES de CORS para que vea los requests que pasaron
    # la preflight, pero antes que cualquier otro middleware que pueda
    # cortocircuitar (e.g. rate limit).
    # FIX Deuda #6: ``install_correlation_handlers`` registra el
    # ``CorrelationIdMiddleware`` (pure-ASGI) Y el exception handler
    # global que setea ``X-Correlation-ID`` en responses 500 generados
    # por el ``ServerErrorMiddleware`` de Starlette.
    install_correlation_handlers(app)

    # Idempotency-Key middleware (Stripe-style). Se monta DESPUES de
    # ``CorrelationIdMiddleware`` para que los logs de hit/miss ya tengan
    # correlation_id. Solo afecta a POST/PATCH/PUT/DELETE.
    from app.core.idempotency import IdempotencyMiddleware  # noqa: PLC0415

    app.add_middleware(IdempotencyMiddleware)

    # Estado de la app: inicializar el engine async. Ya no hay rama
    # ``sqlite_legacy`` (Fase 5+); todo es async.
    from app.db.session import get_engine  # noqa: PLC0415

    get_engine()
    app.state.async_engine_initialized = True
    # ``app.state.db`` se conserva como None por compat con tests
    # que consultaban ``hasattr(app.state, "db")`` o similar. Los
    # routers que lo necesitaban ya fueron migrados a ``get_session``.
    app.state.db = None

    # Handlers de errores de dominio
    app.add_exception_handler(DomainError, domain_error_handler)

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # Métricas Prometheus (Fase 9: /metrics + métricas HTTP automáticas).
    # Se monta DESPUES de los routers para que el Instrumentator pueda
    # introspeccionar las rutas declaradas.
    if settings.metrics_enabled:
        from app.modules.observability.metrics import instrument_app  # noqa: PLC0415

        instrument_app(app)
        log.info("metrics.enabled", endpoint=settings.metrics_path)

    log.info(
        "app.created",
        environment=settings.environment,
        debug=settings.debug,
    )
    return app


# Inicializar Sentry al importar el modulo (antes de crear la app).
# Asi captura errores que ocurran durante ``create_app()`` (e.g. falla
# al configurar la BD o el middleware).
_init_sentry()

# Instancia para uvicorn
app = create_app()
