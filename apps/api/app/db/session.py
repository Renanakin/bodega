"""
Session factory principal (ADR-0001).

Esta es la entrada única para que la app obtenga una AsyncSession.
Detecta el backend por el scheme de DATABASE_URL:
  - postgresql+asyncpg://...  → Postgres (default producción)
  - sqlite+aiosqlite://...     → SQLite (tests rápidos)
  - sqlite:// (legacy Fase 0)   → SQLite in-memory (compat)

Estructura del archivo:
- Sección 1   → Async engine + session (Fase 2+): detect_backend, get_engine,
                get_session_factory, get_session, ping_database.
- Sección 1.5 → Interface abstracta `Database` + implementaciones async
                (`PostgresDatabase`, `AsyncSQLiteDatabase`) + factory
                `create_database_from_url`. Las próximas generaciones de
                repositorios consumirán esta interface (Fase 3+).
- Sección 2   → Compatibilidad LEGACY (Fase 0/1): `SQLiteDatabase` síncrono
                sobre sqlite3 stdlib. Los routers actuales dependen de esta
                sección; se migrarán a async en Fases 3-5.

Reglas aplicadas:
- R3: ubicación obvia (db/session.py) — único punto de creación de engine.
- R4: solo infraestructura; la lógica vive en repository.py.
- R6: pool configurado para 100+ usuarios concurrentes.
"""
from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Mapping,
    Sequence,
)
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.base import Base
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

log = get_logger(__name__)


# =============================================================================
# Sección 1: Async engine + session (Fase 2+)
# =============================================================================


def detect_backend() -> str:
    """Detecta el backend a usar según DATABASE_URL.

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
    """Singleton del AsyncEngine (R3: punto único)."""
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
    """Útil para tests; cierra el engine y resetea el singleton."""
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
    Alembic — es solo un "bootstrap" para dev/test. En producción se
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
# Sección 1.5: Interface Database + factory from URL (ADR-0001)
# =============================================================================
# Esta es la interface unificada que las próximas generaciones de repositorios
# consumirán (Fase 3+). Por ahora los routers usan la Sección 2 (sync
# SQLiteDatabase) por compatibilidad con los tests existentes. La integración
# con PostgreSQL real se valida en tests/test_api_integration.py.


class Database(ABC):
    """Interface abstracta para backends de BD (ADR-0001).

    Cualquier backend (Postgres, SQLite, futuro Citus, etc.) debe implementar
    estos cinco métodos. Los repositorios dependerán de la interface, no del
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

        Retorna el `CursorResult` crudo de SQLAlchemy para inspección si
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

        Commit automático al salir normal; rollback automático ante excepción.
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

    Implementa los 5 métodos del contrato `Database` delegando a un
    `async_sessionmaker`. Compartido por `PostgresDatabase` y
    `AsyncSQLiteDatabase` para evitar duplicación (R3, R4).

    Soporta transacciones anidadas-en-sentido-plano: dentro de un bloque
    `async with db.transaction():` las llamadas a `execute`/`fetch_*`
    usan la misma sesión, y el commit/rollback es al salir del bloque.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
            autoflush=False,
        )
        # Sesión activa dentro de un bloque `transaction()`. None fuera de él.
        # Solo se modifica dentro de `transaction()`; no es thread-safe.
        self._active_session: AsyncSession | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Database]:
        """Abre una transacción; commit al exit, rollback al raise.

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
        session = self._active_session
        if session is not None:
            # Dentro de una transacción: no commit/close aquí, lo hace `transaction()`.
            return await session.execute(text(sql), params or {})
        async with self._session_factory() as session:
            result = await session.execute(text(sql), params or {})
            await session.commit()
            return result

    async def fetch_one(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> dict[str, Any] | None:
        session = self._active_session
        if session is not None:
            result = await session.execute(text(sql), params or {})
            row = result.mappings().first()
            return dict(row) if row is not None else None
        async with self._session_factory() as session:
            result = await session.execute(text(sql), params or {})
            row = result.mappings().first()
            await session.commit()
            return dict(row) if row is not None else None

    async def fetch_all(
        self,
        sql: str,
        params: Mapping[str, Any] | Sequence[Any] | None = None,
    ) -> list[dict[str, Any]]:
        session = self._active_session
        if session is not None:
            result = await session.execute(text(sql), params or {})
            return [dict(row) for row in result.mappings().all()]
        async with self._session_factory() as session:
            result = await session.execute(text(sql), params or {})
            rows = [dict(row) for row in result.mappings().all()]
            await session.commit()
            return rows

    async def close(self) -> None:
        await self._engine.dispose()


class PostgresDatabase(_AsyncSQLADatabase):
    """Implementación async de `Database` para PostgreSQL (ADR-0001).

    Usa SQLAlchemy 2.0 + asyncpg. Soporta UUID nativo, NUMERIC, JSONB
    y transacciones con `SELECT ... FOR UPDATE` (Fase 3+).

    Args:
        url: URL de conexión (ej: postgresql+asyncpg://user:pass@host:5432/db).
        pool_size: conexiones permanentes en el pool (default 10).
        max_overflow: conexiones extra bajo carga (default 20).
        echo: loguea SQL — solo development.
    """

    def __init__(
        self,
        url: str,
        *,
        pool_size: int = 10,
        max_overflow: int = 20,
        echo: bool = False,
    ) -> None:
        engine = create_async_engine(
            url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=True,  # R6: detecta conexiones muertas
            echo=echo,
            future=True,
        )
        super().__init__(engine)


class AsyncSQLiteDatabase(_AsyncSQLADatabase):
    """Implementación async de `Database` para SQLite (tests ultra-rápidos).

    No usar en producción (ADR-0001). Solo para tests de unidades puras
    que no tocan concurrencia ni tipos nativos de Postgres.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        # sqlite+aiosqlite usa 2 slashes para ':memory:' y 3 para path absoluto.
        # Si el path es ':memory:' o vacío, usamos 2 slashes; en otros casos, 3.
        if db_path in (":memory:", "", None):
            url = "sqlite+aiosqlite:///:memory:"
        else:
            url = f"sqlite+aiosqlite:///{db_path}"
        engine = create_async_engine(
            url,
            echo=False,
            future=True,
            connect_args={"check_same_thread": False},
        )
        super().__init__(engine)


def create_database_from_url(url: str, **kwargs: Any) -> Database:
    """Factory que detecta el dialecto de la URL y retorna la Database adecuada.

    Soporta (con coerción automática a asyncpg/aiosqlite):
    - postgresql+asyncpg://... → PostgresDatabase
    - postgresql://...         → PostgresDatabase (driver asyncpg inyectado)
    - postgresql+psycopg2://...→ PostgresDatabase (driver asyncpg inyectado;
        común cuando el caller viene de testcontainers u ORM sync)
    - sqlite+aiosqlite://...   → AsyncSQLiteDatabase
    - sqlite://...             → AsyncSQLiteDatabase (compat legacy)

    Args:
        url: URL de conexión SQLAlchemy completa.
        **kwargs: parámetros extra del engine (pool_size, echo, etc).

    Returns:
        Instancia de Database lista para usar con `async with`.

    Raises:
        ValueError: si el scheme no es postgres/sqlite (fail fast, mejor que
            tratar de instanciar un engine con un driver que no existe).

    Example:
        db = create_database_from_url("postgresql+asyncpg://bodegaje:***@db/bodegaje")
        async with db.transaction():
            await db.execute("INSERT INTO warehouses ...")
    """
    # Coerción centralizada de schemes postgres → postgresql+asyncpg.
    if url.startswith("postgresql+asyncpg://"):
        log.info("db.factory.postgres", host=_redact_url(url))
        return PostgresDatabase(url, **kwargs)
    if url.startswith("postgresql+psycopg2://"):
        coerced = "postgresql+asyncpg://" + url[len("postgresql+psycopg2://") :]
        log.info("db.factory.postgres_coerced", host=_redact_url(coerced))
        return PostgresDatabase(coerced, **kwargs)
    if url.startswith("postgresql://"):
        # El caller omitió el driver explícito; SQLAlchemy elegirá psycopg2
        # por default. Lo corregimos a asyncpg (ADR-0001).
        coerced = "postgresql+asyncpg://" + url[len("postgresql://") :]
        log.info("db.factory.postgres_coerced", host=_redact_url(coerced))
        return PostgresDatabase(coerced, **kwargs)
    if url.startswith(("sqlite+aiosqlite://", "sqlite://")):
        # Quitar el prefijo del scheme para quedarnos con el path.
        # Las URLs tipo sqlite:///path tienen un '/' extra que no es parte del path.
        raw = url.split("://", 1)[1]
        # Soporta: sqlite://:memory:, sqlite:///:memory:, sqlite:///abs/path, sqlite://rel
        if raw.startswith("/:memory:"):
            path = ":memory:"
        elif raw.startswith("/"):
            path = raw  # path absoluto, conserva el '/'
        else:
            path = raw or ":memory:"
        log.info("db.factory.sqlite_async", path=path)
        return AsyncSQLiteDatabase(db_path=path)
    log.error("db.factory.unsupported_scheme", url=_redact_url(url))
    raise ValueError(
        f"create_database_from_url: scheme no soportado en {url!r}. "
        "Use postgresql+asyncpg://, postgresql://, sqlite+aiosqlite:// o sqlite://"
    )


def _redact_url(url: str) -> str:
    """Enmascara la contraseña en una URL para logs."""
    if "@" not in url:
        return url
    scheme_userpass, host_part = url.rsplit("@", 1)
    if ":" in scheme_userpass:
        scheme, _ = scheme_userpass.split("://", 1)
        return f"{scheme}://***@{host_part}"
    return url


# =============================================================================
# Sección 2: Compatibilidad LEGACY (Fase 0/1)
# =============================================================================
# El código de warehouses/products/inventory/transfers/auth repositories
# todavía usa la API sync basada en sqlite3 stdlib + RLock.
# Se migrarán a async gradualmente en Fases 3-5.
# NO agregar funcionalidad nueva en esta sección.


@dataclass(slots=True)
class WarehouseRecord:
    id: UUID
    code: str
    name: str
    warehouse_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ProductRecord:
    id: UUID
    sku: str
    name: str
    unit: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # --- Extensión Fase 2 (ADR-0001 / aterrizaje §3.2) ---
    codigo_barras: str | None = None
    precio_costo: Decimal = Decimal("0")
    precio_venta: Decimal = Decimal("0")
    id_categoria: UUID | None = None


@dataclass(slots=True)
class StockLevelRecord:
    id: UUID
    warehouse_id: UUID
    product_id: UUID
    quantity: Decimal
    min_quantity: Decimal
    updated_at: datetime
    max_quantity: Decimal | None = None


@dataclass(slots=True)
class InventoryMovementRecord:
    id: UUID
    warehouse_id: UUID
    product_id: UUID
    movement_type: str
    quantity: Decimal
    reference_type: str | None
    reference_id: str | None
    notes: str | None
    created_at: datetime


@dataclass(slots=True)
class TransferRecord:
    id: UUID
    code: str
    from_warehouse_id: UUID
    to_warehouse_id: UUID
    product_id: UUID
    quantity: Decimal
    received_quantity: Decimal
    status: str
    priority: str | None
    notes: str | None
    dispatch_notes: str | None
    receive_notes: str | None
    incident_type: str | None
    incident_notes: str | None
    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    received_at: datetime | None


@dataclass(slots=True)
class UserRecord:
    id: UUID
    username: str
    full_name: str
    role: str
    password_hash: str
    is_active: bool
    created_at: datetime


@dataclass(slots=True)
class SessionRecord:
    id: UUID
    user_id: UUID
    token: str
    expires_at: datetime
    created_at: datetime


@dataclass(slots=True)
class AuditLogRecord:
    id: UUID
    user_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    detail: str | None
    created_at: datetime


class SQLiteDatabase:
    """Wrapper legacy sobre sqlite3 stdlib. DEPRECAR en Fase 3+."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._connection = sqlite3.connect(
            ":memory:" if str(self.path) == ":memory:" else self.path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        # WAL mode (Write-Ahead Logging): permite que el engine async
        # (aiosqlite) y este legacy sync (sqlite3 stdlib) compartan el
        # mismo archivo sin "database is locked" en operaciones
        # concurrentes. Es opt-in a nivel de archivo, asi que cualquier
        # conexion posterior al mismo path lo respeta automaticamente.
        # Solo se aplica a archivos fisicos (no a :memory:).
        if str(self.path) != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
            # busy_timeout: esperar hasta 5s si el archivo esta locked
            # por otra conexion (engine async) antes de fallar.
            self._connection.execute("PRAGMA busy_timeout=5000")
        self._apply_migrations()

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        started = not self._connection.in_transaction
        if started:
            self._connection.execute("BEGIN")
        try:
            yield self
            if started:
                self._connection.commit()
        except Exception:
            if started:
                self._connection.rollback()
            raise

    @contextmanager
    def begin_immediate_transaction(self):  # type: ignore[no-untyped-def]
        """Context manager que adquiere el ``RLock`` y emite ``BEGIN IMMEDIATE``.

        Equivalente analogo de ``SELECT ... FOR UPDATE`` sobre SQLite:
        adquiere el ``RESERVED`` lock al inicio de la transaccion,
        serializando a los demas writers. Los readers siguen funcionando.

        Es responsabilidad del caller NO mezclar este context manager con
        llamadas que no tomen el ``RLock`` (ej. ``db.execute()`` directo),
        porque eso bypasea la proteccion contra oversell.

        Yields:
            ``self`` (la ``SQLiteDatabase``) para que el caller pueda
            ejecutar queries dentro del lock.

        Raises:
            Exception: cualquier excepcion dentro del bloque dispara
                ``ROLLBACK`` y re-raise.
        """
        with self._lock:
            started = not self._connection.in_transaction
            if started:
                self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self
                if started:
                    self._connection.commit()
            except Exception:
                if started:
                    self._connection.rollback()
                raise

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:  # type: ignore[no-untyped-def]
        return self._connection.execute(sql, params)

    def execute_script(self, sql: str) -> None:  # type: ignore[no-untyped-def]
        self._connection.executescript(sql)

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:  # type: ignore[no-untyped-def]
        return self.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:  # type: ignore[no-untyped-def]
        return self.execute(sql, params).fetchall()

    def close(self) -> None:
        self._connection.close()

    def __del__(self) -> None:  # noqa: D401
        try:
            self.close()
        except Exception:  # noqa: S110
            pass

    def _apply_migrations(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        migrations_dir = get_settings().sqlite_migrations_dir
        if not migrations_dir.exists():
            return
        applied = {
            row["version"]
            for row in self.query_all("SELECT version FROM schema_migrations ORDER BY version")
        }
        for migration_path in sorted(migrations_dir.glob("*.sql")):
            version = migration_path.name
            if version in applied:
                continue
            self.execute_script(migration_path.read_text(encoding="utf-8"))
            self.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                (version, utcnow().isoformat()),
            )
        self._connection.commit()


def create_database(db_path: str | Path | None = None) -> SQLiteDatabase:
    """Factory legacy para tests con SQLite in-memory (Fase 0/1)."""
    return SQLiteDatabase(db_path or get_settings().resolved_database_path)


def get_database(request: Request) -> SQLiteDatabase:  # type: ignore[no-untyped-def]
    return request.app.state.db


def utcnow() -> datetime:
    return datetime.now(UTC)


def _extract_sqlite_path_from_url(url: str) -> str:
    """Extrae el path de una URL de SQLite (sync o async).

    Soporta:
    - sqlite+aiosqlite:///G:/path/to/db.db  -> G:/path/to/db.db
    - sqlite:///G:/path/to/db.db            -> G:/path/to/db.db
    - sqlite:///:memory:                    -> :memory:
    - sqlite+aiosqlite:///:memory:          -> :memory:
    - Vacio / None                          -> :memory: (default)

    Usado por `app.main.create_app()` para resolver el path comun
    entre el engine async (aiosqlite) y el legacy sync (sqlite3 stdlib)
    cuando el backend activo es "sqlite" (deuda #1).
    """
    if not url:
        return ":memory:"
    # Strip scheme
    if ":///" in url:
        path = url.split(":///", 1)[1]
    elif "://" in url:
        path = url.split("://", 1)[1]
    else:
        path = url
    # :memory: se representa con path vacio despues de ":///"
    if path == "" or path == ":memory:":
        return ":memory:"
    return path
