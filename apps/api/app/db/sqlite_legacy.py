"""
Compatibilidad LEGACY: ``SQLiteDatabase`` sync sobre sqlite3 stdlib.

Esta capa existe para mantener funcionando los repositories de
warehouses/products/inventory/transfers/auth que aun no se migraron
a async (Fase 3+). Se migraran gradualmente; no agregar funcionalidad
nueva aca.

WAL mode + busy_timeout permiten que el engine async (aiosqlite) y
este legacy sync (sqlite3 stdlib) compartan el mismo archivo sin
"database is locked" en operaciones concurrentes.
"""

from __future__ import annotations

import contextlib
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from app.core.config import get_settings
from fastapi import Request


def utcnow() -> datetime:
    """UTC now, helper compartido."""
    return datetime.now(UTC)


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
        # FIX: registrar alias NOW() -> CURRENT_TIMESTAMP para que las
        # migraciones SQL portables (mismas para Postgres y SQLite)
        # funcionen en SQLite sin reescribirlas.
        self._connection.create_function("NOW", 0, lambda: datetime.now(UTC).isoformat())
        # WAL mode (Write-Ahead Logging): permite que el engine async
        # (aiosqlite) y este legacy sync (sqlite3 stdlib) compartan el
        # mismo archivo sin "database is locked" en operaciones
        # concurrentes.
        if str(self.path) != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
            # busy_timeout: esperar hasta 5s si el archivo esta locked
            # por otra conexion (engine async) antes de fallar.
            self._connection.execute("PRAGMA busy_timeout=5000")
        self._apply_migrations()

    @contextmanager
    def transaction(self) -> Any:
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
    def begin_immediate_transaction(self) -> Any:
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

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> sqlite3.Cursor:
        # CRITICO: serializar TODOS los accesos a la conexion con el RLock.
        # Sin esto, uvicorn manda multiples requests en paralelo y sqlite3
        # stdlib (aun con check_same_thread=False) lanza
        # "InterfaceError: bad parameter or other API misuse" cuando
        # dos threads ejecutan a la vez sobre la misma conexion.
        with self._lock:
            return self._connection.execute(sql, params)

    def execute_script(self, sql: str) -> None:
        with self._lock:
            self._connection.executescript(sql)

    def query_one(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple[Any, ...] | list[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.execute(sql, params).fetchall()

    def close(self) -> None:
        self._connection.close()

    def __del__(self) -> None:  # noqa: D401
        with contextlib.suppress(Exception):
            self.close()

    def _apply_migrations(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )

        # FIX (FASE B + bug pre-existente): antes de aplicar las
        # migraciones SQL, asegurarse de que las tablas existen. Las
        # migraciones 0010+ usan `ALTER TABLE ... ADD COLUMN` (ej.
        # 0011_refresh_tokens agrega `refresh_token` a `user_sessions`),
        # lo cual falla con "no such column" si la tabla no existe.
        #
        # Caso problematico: tests que crean la BD legacy `:memory:` SIN
        # haber pasado por `Base.metadata.create_all` (engine async).
        # Antes de este fix, las migraciones se ejecutaban sobre una BD
        # vacia y el ALTER TABLE fallaba, rompiendo TODA la suite legacy.
        #
        # Approach: emitir el DDL generado por SQLAlchemy directamente
        # sobre `self._connection` (la conexion sqlite3 stdlib legacy).
        # Asi NO necesitamos un engine separado, ni archivos temporales.
        # Solo capturamos los DDL de los modelos y los ejecutamos via
        # `self.execute_script`.
        try:
            from app.db import models  # noqa: F401  -- registra modelos en Base.metadata
            from app.db.base import Base
            from sqlalchemy import create_mock_engine
            from sqlalchemy.schema import CreateTable as _CreateTable

            # Crear un engine mock (no se conecta) solo para usar el
            # compilador de DDL de SQLAlchemy. El dialecto sqlite
            # genera el CREATE TABLE correcto para nuestro caso.
            # `executor` recibe el SQL compilado pero no lo ejecuta.
            dummy_engine = create_mock_engine("sqlite://", lambda *args, **kwargs: None)

            with self._lock:
                for table in Base.metadata.sorted_tables:
                    # Saltar tablas que ya existen (idempotente)
                    if self._connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table.name,),
                    ).fetchone() is not None:
                        continue
                    ddl = str(_CreateTable(table).compile(dummy_engine))
                    self.execute_script(ddl)
            # No dispose en mock engine (no es necesario, igual se libera)
        except Exception as exc:  # noqa: BLE001
            # No bloquear: si falla (ej. modelo no registrado), las
            # migraciones se aplican igual y el ALTER fallara con un
            # error explicito (mejor que un error silencioso).
            import structlog

            structlog.get_logger(__name__).warning(
                "sqlite_legacy.create_all_pre_migration_failed",
                error=str(exc),
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
            # FIX: los ALTER TABLE ADD COLUMN no son idempotentes en SQLite
            # pre-3.35. Si la columna ya existe (porque el modelo la
            # incluye via create_all arriba), la migracion falla con
            # "duplicate column name". Continuamos en ese caso (es benigno).
            try:
                self.execute_script(migration_path.read_text(encoding="utf-8"))
                self.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                    (version, utcnow().isoformat()),
                )
            except sqlite3.OperationalError as exc:
                # Errores esperados cuando la migracion es obsoleta o ya
                # aplicada via create_all del modelo.
                if "duplicate column" in str(exc).lower():
                    # La columna ya existe (modelo la creo). Marcamos
                    # como aplicada para no intentar de nuevo.
                    self.execute(
                        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES(?, ?)",
                        (version, utcnow().isoformat()),
                    )
                else:
                    # Otro error: relanzar para que el caller sepa
                    raise
        self._connection.commit()


def create_database(db_path: str | Path | None = None) -> SQLiteDatabase:
    """Factory legacy para tests con SQLite in-memory (Fase 0/1)."""
    return SQLiteDatabase(db_path or get_settings().resolved_database_path)


def get_database(request: Request) -> SQLiteDatabase:
    """FastAPI dependency: obtiene el SQLiteDatabase del app.state."""
    return request.app.state.db


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
    if ":///" in url:
        path = url.split(":///", 1)[1]
    elif "://" in url:
        path = url.split("://", 1)[1]
    else:
        path = url
    if path == "" or path == ":memory:":
        return ":memory:"
    return path
