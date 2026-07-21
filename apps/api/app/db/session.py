"""
Session factory principal (ADR-0001).

Esta es la entrada unica para que la app obtenga una AsyncSession.
Detecta el backend por el scheme de DATABASE_URL:
  - postgresql+asyncpg://...  -> Postgres (default produccion)
  - sqlite+aiosqlite://...     -> SQLite (tests rapidos)
  - sqlite:// (legacy Fase 0)   -> SQLite in-memory (compat)

Estructura del archivo:
- Seccion 1   -> Async engine + session (Fase 2+): detect_backend, get_engine,
                get_session_factory, get_session, ping_database.
- Seccion 1.5 -> Interface abstracta `Database` + implementaciones async
                (`PostgresDatabase`, `AsyncSQLiteDatabase`) + factory
                `create_database_from_url`.

Reglas aplicadas:
- R3: ubicacion obvia (db/session.py) - unico punto de creacion de engine.
- R4: solo infraestructura; la logica vive en repository.py.
- R6: pool configurado para 100+ usuarios concurrentes.

Compatibilidad LEGACY (Fase 0/1) en `db/sqlite_legacy.py`:
- `SQLiteDatabase` (sync, sobre sqlite3 stdlib).
- `create_database`, `get_database` (factories).
- Re-exportados aqui para preservar `from app.db.session import ...`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Mapping,
    Sequence,
)
from contextlib import asynccontextmanager
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import Base

# Re-exports para retrocompatibilidad de imports (R5, regla 30 segundos).
# Los imports del estilo `from app.db.session import SQLiteDatabase, get_database,
# create_database, utcnow, WarehouseRecord, ...` siguen funcionando.
from app.db.records import (  # noqa: F401
    AuditLogRecord,
    InventoryMovementRecord,
    ProductRecord,
    SessionRecord,
    StockLevelRecord,
    TransferRecord,
    UserRecord,
    WarehouseRecord,
)
from app.db.sqlite_legacy import (  # noqa: F401  # noqa: F401
    SQLiteDatabase,
    _extract_sqlite_path_from_url,
    create_database,
    get_database,
    utcnow,
)
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

log = get_logger(__name__)


# =============================================================================
# Seccion 1: Async engine + session (Fase 2+)
# =============================================================================


def detect_backend() -> str:
    """Detecta el backend a usar segun DATABASE_URL.

    Returns:
        "postgres" o "sqlite"
    """
    url = get_settings().database_url
    if url.startswith("postgresql+asyncpg://"):
        return "postgres"
    if url.startswith("sqlite+aiosqlite://") or url.startswith("sqlite://"):
        return "sqlite"
    return "postgres"  # default


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Singleton del AsyncEngine (R3: punto unico)."""
    global _engine, _session_factory
    if _engine is None:
        backend = detect_backend()
        if backend == "postgres":
            from app.db.postgres import create_postgres_engine

            _engine = create_postgres_engine()
        else:
            from app.db.sqlite import create_sqlite_engine

            _engine = create_sqlite_engine()
        log.info("db.engine_initialized", backend=backend)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Singleton de la factory de sesiones."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        backend = detect_backend()
        if backend == "postgres":
            from app.db.postgres import create_session_factory
        else:
            from app.db.sqlite import create_session_factory
        _session_factory = create_session_factory(engine)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: inyecta una AsyncSession por request.

    Uso:
        @router.get("/x")
        async def x(session: AsyncSession = Depends(get_session)):
            ...
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def ping_database() -> bool:
    """Ping al backend activo. Para healthcheck."""
    engine = get_engine()
    backend = detect_backend()
    if backend == "postgres":
        from app.db.postgres import ping_postgres

        return await ping_postgres(engine)
    from app.db.sqlite import ping_sqlite

    return await ping_sqlite(engine)


def reset_engine_cache() -> None:
    """Util para tests; cierra el engine y resetea el singleton."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def init_async_schema() -> None:
    """Crea todas las tablas declaradas en `Base.metadata` en el engine async.

    Idempotente: si las tablas ya existen, no hace nada. Se usa en el
    ``lifespan`` startup de la app para que la BD async (smoke.db /
    Postgres test) tenga las tablas desde el primer request, sin
    depender de Alembic corriendo aparte.

    Solo se invoca cuando el backend activo es async (sqlite+aiosqlite o
    postgresql+asyncpg). En modo ``sqlite_legacy`` (``app.state.db``),
    las tablas las crea ``SQLiteDatabase._apply_migrations()`` con las
    migraciones .sql.

    NOTA: ``Base.metadata.create_all`` no respeta las migraciones de
    Alembic - es solo un "bootstrap" para dev/test. En produccion se
    sigue usando ``alembic upgrade head``.
    """
    # Importar los modelos ANTES de create_all para que Base.metadata
    # los registre (sino el metadata estaria vacio).
    from app.db.models import (  # noqa: PLC0415, F401
        AuditLog,
        Category,
        DetalleNeumatico,
        DetalleOrdenCompra,
        DetalleSolicitudRecarga,
        EmailOutbox,
        InventarioStockReal,
        InventoryMovement,
        MovementType,
        Notificacion,
        NotificationType,
        OrdenCompra,
        OrdenCompraEstado,
        Product,
        Proveedor,
        SolicitudEstado,
        SolicitudRecarga,
        StockLevel,
        Supervisor,
        Transfer,
        UbicacionEstanteria,
        User,
        UserSession,
        Warehouse,
    )

    engine = get_engine()
    backend = detect_backend()
    # create_all es sync (DDL no es awaitable en SQLAlchemy 2).
    # Se ejecuta en un thread via run_sync para no bloquear el event loop.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info(
        "db.async_schema_initialized",
        backend=backend,
        tables=len(Base.metadata.tables),
    )


# =============================================================================
# Seccion 1.5: Interface Database + factory from URL (ADR-0001)
# =============================================================================
# Esta es la interface unificada que las proximas generaciones de repositorios
# consumiran (Fase 3+). Por ahora los routers usan la Seccion 2 (sync
# SQLiteDatabase) por compatibilidad con los tests existentes. La integracion
# con PostgreSQL real se valida en tests/test_api_integration.py.


class Database(ABC):
    """Interface abstracta para backends de BD (ADR-0001).

    Cualquier backend (Postgres, SQLite, futuro Citus, etc.) debe implementar
    estos cinco metodos. Los repositorios dependeran de la interface, no del
    dialecto concreto.

    Convenciones:
    - Los params se aceptan como Mapping (named) o Sequence (positional).
    - `fetch_one` retorna dict | None; `fetch_all` retorna list[dict].
    - `transaction` es un context manager async que hace commit/rollback.
    """

    @abstractmethod
    async def execute(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> CursorResult[Any]:
        """Ejecuta SQL con efectos (INSERT/UPDATE/DELETE/DDL).

        Retorna el `CursorResult` crudo de SQLAlchemy para inspeccion si
        el caller necesita rowcount/lastrowid.
        """

    @abstractmethod
    async def fetch_one(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Ejecuta un SELECT y retorna la primera fila como dict, o None."""

    @abstractmethod
    async def fetch_all(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Ejecuta un SELECT y retorna todas las filas como lista de dicts."""

    @abstractmethod
    def transaction(self) -> AsyncIterator[Database]:
        """Context manager async transaccional.

        Commit automatico al salir normal; rollback automatico ante excepcion.
        Uso:
            async with db.transaction():
                await db.execute(...)
                await db.execute(...)
        """

    @abstractmethod
    async def close(self) -> None:
        """Cierra el engine y libera el pool."""


class _AsyncSQLADatabase(Database):
    """Base async con SQLAlchemy 2.0. Subclases solo configuran el engine.

    Implementa los 5 metodos del contrato `Database` delegando a un
    `async_sessionmaker`. Compartido por `PostgresDatabase` y
    `AsyncSQLiteDatabase` para evitar duplicacion (R3, R4).

    Soporta transacciones anidadas-en-sentido-plano: dentro de un bloque
    `async with db.transaction():` las llamadas a `execute`/`fetch_*`
    usan la misma sesion, y el commit/rollback es al salir del bloque.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
            autoflush=False,
        )
        # Sesion activa dentro de un bloque `transaction()`. None fuera de el.
        # Solo se modifica dentro de `transaction()`; no es thread-safe.
        self._active_session: AsyncSession | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Database]:
        """Abre una transaccion; commit al exit, rollback al raise.

        Ejemplo:
            async with db.transaction():
                await db.execute(...)
                await db.execute(...)
        """
        async with self._session_factory() as session:
            previous = self._active_session
            self._active_session = session
            try:
                yield self
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                self._active_session = previous

    async def execute(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> CursorResult[Any]:
        """Ejecuta SQL via la sesion activa o una nueva."""
        if self._active_session is not None:
            return await self._active_session.execute(text(sql), params or {})
        async with self._session_factory() as session:
            return await session.execute(text(sql), params or {})

    async def fetch_one(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> dict[str, Any] | None:
        """SELECT con retorno de la primera fila como dict, o None."""
        if self._active_session is not None:
            result = await self._active_session.execute(text(sql), params or {})
        else:
            async with self._session_factory() as session:
                result = await session.execute(text(sql), params or {})
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def fetch_all(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """SELECT con retorno de todas las filas como lista de dicts."""
        if self._active_session is not None:
            result = await self._active_session.execute(text(sql), params or {})
        else:
            async with self._session_factory() as session:
                result = await session.execute(text(sql), params or {})
        return [dict(row) for row in result.mappings().all()]

    async def close(self) -> None:
        await self._engine.dispose()


class PostgresDatabase(_AsyncSQLADatabase):
    """Implementacion async del contrato `Database` para PostgreSQL.

    Usa el engine de `app.db.postgres.create_postgres_engine()`.
    """


class AsyncSQLiteDatabase(_AsyncSQLADatabase):
    """Implementacion async del contrato `Database` para SQLite (aiosqlite).

    Usa el engine de `app.db.sqlite.create_sqlite_engine()`.
    """


def _redact_url(url: str) -> str:
    """Enmascara la password en URLs para logging seguro.

    Convierte `postgresql+asyncpg://user:pass@host:port/db`
    en        `postgresql+asyncpg://user:***@host:port/db`.
    """
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    auth, host_part = rest.split("@", 1)
    if ":" in auth:
        user, _password = auth.split(":", 1)
        return f"{scheme}://{user}:***@{host_part}"
    return f"{scheme}://***@{host_part}"


def create_database_from_url(url: str, **kwargs: Any) -> Database:
    """Crea una instancia de `Database` segun el scheme de la URL.

    - postgresql+asyncpg://...  -> PostgresDatabase
    - sqlite+aiosqlite://...    -> AsyncSQLiteDatabase
    - sqlite://...              -> AsyncSQLiteDatabase (compat legacy)
    """
    if url.startswith("postgresql+asyncpg://"):
        from app.db.postgres import create_postgres_engine

        return PostgresDatabase(create_postgres_engine(**kwargs))
    if url.startswith("sqlite") or url.startswith("sqlite+aiosqlite"):
        from app.db.sqlite import create_sqlite_engine

        path = _extract_sqlite_path_from_url(url)
        return AsyncSQLiteDatabase(create_sqlite_engine(path))
    raise ValueError(f"URL de BD no soportada: {_redact_url(url)}")
