from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import RLock
from uuid import UUID

from fastapi import Request

from app.core.config import settings


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


@dataclass(slots=True)
class StockLevelRecord:
    id: UUID
    warehouse_id: UUID
    product_id: UUID
    quantity: Decimal
    min_quantity: Decimal
    updated_at: datetime


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
        self._apply_migrations()

    @contextmanager
    def transaction(self):
        with self._lock:
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

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        return self._connection.execute(sql, params)

    def execute_script(self, sql: str) -> None:
        self._connection.executescript(sql)

    def query_one(self, sql: str, params: tuple | list = ()) -> sqlite3.Row | None:
        return self.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple | list = ()) -> list[sqlite3.Row]:
        return self.execute(sql, params).fetchall()

    def close(self) -> None:
        self._connection.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
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
        migrations_dir = settings.sqlite_migrations_dir
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
    return SQLiteDatabase(db_path or settings.resolved_database_path)


def get_database(request: Request) -> SQLiteDatabase:
    return request.app.state.db


def utcnow() -> datetime:
    return datetime.now(UTC)
