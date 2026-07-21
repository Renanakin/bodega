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

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import DomainError, domain_error_handler
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    install_correlation_handlers,
)
from app.db.session import create_database
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    # Si el backend activo es async (no sqlite_legacy), crear las tablas
    # en el engine async al startup. Esto unifica el path de BD: los
    # routers async y sync legacy apuntaran a archivos DIFERENTES, pero
    # los routers migrados a async (auth, warehouses, products, etc.)
    # comparten la misma BD con el resto del flujo async (solicitudes).
    # Ver Deuda #1 (Prioridad 1) en docs/HANDOFF_SESION_2026-07-15.md.
    if getattr(app.state, "async_engine_initialized", False):
        from app.db.session import init_async_schema  # noqa: PLC0415

        try:
            await init_async_schema()
        except Exception as exc:  # noqa: BLE001
            log.error(
                "db.async_schema_init_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
    yield
    log.info("app.shutdown")


def _resolve_backend(db_path: str | None) -> tuple[str, str]:
    """Decide qué backend de BD usar y devuelve (backend_name, detail).

    Returns:
        Tupla (backend, detail) donde:
        - backend ∈ {"sqlite_legacy", "sqlite", "postgres"}
        - detail es el path o URL (sin credenciales) para logging.
    """
    settings = get_settings()

    # Caso 1: tests pasan db_path explícito → legacy sync SQLite (Fase 0/1).
    if db_path is not None:
        return "sqlite_legacy", f"path={db_path}"

    # Caso 2: tests sin db_path (create_app() pelado) → legacy sync SQLite.
    if not settings.database_url:
        return "sqlite_legacy", f"path={settings.resolved_database_path}"

    # Caso 3: DATABASE_URL define postgres → backend target de Fase 1.
    if settings.db_backend == "postgres":
        from app.db.session import _redact_url

        return "postgres", _redact_url(settings.database_url)

    # Caso 4: DATABASE_URL es sqlite explícito → backend SQLite async.
    return "sqlite", settings.database_url


def create_app(db_path: str | None = None) -> FastAPI:
    """Factory de la aplicación FastAPI.

    Args:
        db_path: Si se pasa, se usa como ruta SQLite para tests
            (mantiene la API legacy de Fase 0/1). Si es None, se
            decide el backend según `settings.database_url`.

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

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
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

    # Estado de la app: conexión a BD
    if backend == "sqlite_legacy":
        # Modo tests legacy (create_app(db_path=":memory:")):
        # solo sync SQLite, sin engine async.
        app.state.db = create_database(db_path)
        app.state.async_engine_initialized = False
    elif backend == "sqlite":
        # Modo async SQLite (DATABASE_URL=sqlite+aiosqlite:///path):
        # el engine async maneja la BD principal, pero los routers sync
        # siguen usando `app.state.db` con un SQLiteDatabase que apunta
        # al MISMO archivo. Habilitamos WAL mode para que ambos motores
        # (sqlite3 stdlib y aiosqlite) puedan leer/escribir concurrentes
        # sin "database is locked". Esto resuelve la Deuda #1 (paths de
        # BD desincronizados) sin necesidad de migrar 6 routers.
        from app.db.session import get_engine  # noqa: PLC0415

        get_engine()  # inicializa el singleton del AsyncEngine
        # Resolver el path de la BD a partir de la URL
        # `sqlite+aiosqlite:///path/to/db.db` -> `path/to/db.db`
        from app.db.session import _extract_sqlite_path_from_url  # noqa: PLC0415

        sqlite_path = _extract_sqlite_path_from_url(settings.database_url or "")
        # legacy sync contra el mismo path. Si el path es :memory:,
        # ambos (sync y async) usan :memory:.
        app.state.db = create_database(sqlite_path)
        app.state.async_engine_initialized = True
    else:  # postgres
        from app.db.session import get_engine  # noqa: PLC0415

        # Modo Postgres: no hay legacy sync SQLite. Los routers sync
        # legacy (auth/warehouses/products/etc.) no son compatibles con
        # Postgres porque usan SQL crudo con `?` placeholders (sqlite3)
        # en vez de `$1` (asyncpg). Mantenemos `app.state.db = None`
        # y los routers sync daran error 503 hasta migrarlos a async.
        # En Fase 5+ (cuando se complete la migracion), este caso
        # dejara de existir.
        get_engine()
        app.state.db = None
        app.state.async_engine_initialized = True

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
