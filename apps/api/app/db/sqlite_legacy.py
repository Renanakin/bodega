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

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

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
