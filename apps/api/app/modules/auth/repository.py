"""Repositorio de autenticación (híbrido legacy + async).

FIX BUG-002: este repository usaba ``SQLiteDatabase`` (legacy sync) que
solo existe cuando el backend activo es SQLite legacy. En Postgres
(``postgresql+asyncpg``) el ``SQLiteDatabase`` no existe y la app fallaba
con ``'NoneType' object has no attribute 'query_one'``.

Estrategia: el repository detecta el tipo de ``session``/``db`` recibido
y opera en modo async (SQLAlchemy) o legacy (sqlite3 stdlib). En modo
async es compatible con SQLite (``sqlite+aiosqlite://``) y Postgres
(``postgresql+asyncpg://``). En modo legacy sigue funcionando con
``db_path=":memory:"`` que usan los tests existentes.

Los ``*Record`` dataclasses (UserRecord, SessionRecord, AuditLogRecord) se
mantienen como DTOs de salida para no romper ``AuthService`` y los routers
que los consumen via ``Depends``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.models.users import AuditLog, User, UserSession
from app.db.session import AuditLogRecord, SessionRecord, UserRecord
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession


def _user_to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        password_hash=user.password_hash,
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )


def _session_to_record(session: UserSession) -> SessionRecord:
    return SessionRecord(
        id=session.id,
        user_id=session.user_id,
        token=session.token,
        expires_at=session.expires_at,
        created_at=session.created_at,
    )


def _audit_to_record(log: AuditLog) -> AuditLogRecord:
    return AuditLogRecord(
        id=log.id,
        user_id=log.user_id,
        action=log.action,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        detail=log.detail,
        created_at=log.created_at,
    )


class AuthRepository:
    """Repositorio de auth + audit.

    Acepta AMBOS:
    - ``AsyncSession`` (modo async, SQLite async o Postgres)
    - ``SQLiteDatabase`` legacy (modo sync, ``create_app(db_path=...)``)

    En modo async todos los métodos son ``async`` (await required).
    En modo legacy los métodos son sync (compat con tests existentes).
    """

    def __init__(self, backend: AsyncSession | Any) -> None:
        self._backend = backend
        # Heurística: si tiene ``execute`` async y ``__class__.__name__``
        # contiene 'AsyncSession' → modo async; en otro caso legacy.
        self._is_async = backend.__class__.__name__ == "AsyncSession"

    # ---- Modo async (SQLAlchemy) ----

    async def _async_get_user_by_username(self, username: str) -> UserRecord | None:
        result = await self._backend.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        return _user_to_record(user) if user is not None else None

    async def _async_get_user_by_id(self, user_id: UUID) -> UserRecord | None:
        result = await self._backend.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        return _user_to_record(user) if user is not None else None

    async def _async_add_session(self, session: SessionRecord) -> SessionRecord:
        self._backend.add(
            UserSession(
                id=session.id,
                user_id=session.user_id,
                token=session.token,
                expires_at=session.expires_at,
                created_at=session.created_at,
            )
        )
        await self._backend.flush()
        return session

    async def _async_get_session_by_token(self, token: str) -> SessionRecord | None:
        result = await self._backend.execute(
            select(UserSession).where(UserSession.token == token)
        )
        s = result.scalar_one_or_none()
        return _session_to_record(s) if s is not None else None

    async def _async_delete_session(self, token: str) -> None:
        from sqlalchemy import delete

        await self._backend.execute(
            delete(UserSession).where(UserSession.token == token)
        )
        await self._backend.flush()

    async def _async_add_audit_log(self, log: AuditLogRecord) -> AuditLogRecord:
        self._backend.add(
            AuditLog(
                id=log.id,
                user_id=log.user_id,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                detail=log.detail,
                created_at=log.created_at,
            )
        )
        await self._backend.flush()
        return log

    async def _async_list_audit_logs(
        self,
        limit: int = 50,
        *,
        entity_type: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[AuditLogRecord]:
        clauses = []
        if entity_type is not None:
            clauses.append(AuditLog.entity_type == entity_type)
        if action is not None:
            clauses.append(AuditLog.action == action)
        if user_id is not None:
            clauses.append(AuditLog.user_id == UUID(user_id))
        if date_from is not None:
            clauses.append(AuditLog.created_at >= _parse_dt(date_from))
        if date_to is not None:
            clauses.append(AuditLog.created_at <= _parse_dt(date_to))
        stmt = select(AuditLog)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
        result = await self._backend.execute(stmt)
        return [_audit_to_record(r) for r in result.scalars().all()]

    # ---- Modo legacy (sqlite3 stdlib) ----

    def _legacy_get_user_by_username(self, username: str) -> UserRecord | None:
        row = self._backend.query_one(
            "SELECT * FROM users WHERE username = ?", (username,)
        )
        return _legacy_user_to_record(row) if row is not None else None

    def _legacy_get_user_by_id(self, user_id: UUID) -> UserRecord | None:
        row = self._backend.query_one(
            "SELECT * FROM users WHERE id = ?", (str(user_id),)
        )
        return _legacy_user_to_record(row) if row is not None else None

    def _legacy_add_session(self, session: SessionRecord) -> SessionRecord:
        self._backend.execute(
            """
            INSERT INTO user_sessions (id, user_id, token, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(session.id),
                str(session.user_id),
                session.token,
                session.expires_at.isoformat(),
                session.created_at.isoformat(),
            ),
        )
        return session

    def _legacy_get_session_by_token(self, token: str) -> SessionRecord | None:
        row = self._backend.query_one(
            "SELECT * FROM user_sessions WHERE token = ?", (token,)
        )
        return _legacy_session_to_record(row) if row is not None else None

    def _legacy_delete_session(self, token: str) -> None:
        self._backend.execute("DELETE FROM user_sessions WHERE token = ?", (token,))

    def _legacy_add_audit_log(self, log: AuditLogRecord) -> AuditLogRecord:
        self._backend.execute(
            """
            INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(log.id),
                str(log.user_id) if log.user_id else None,
                log.action,
                log.entity_type,
                log.entity_id,
                log.detail,
                log.created_at.isoformat(),
            ),
        )
        return log

    def _legacy_list_audit_logs(
        self,
        limit: int = 50,
        *,
        entity_type: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[AuditLogRecord]:
        clauses: list[str] = []
        params: list = []
        if entity_type is not None:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if action is not None:
            clauses.append("action = ?")
            params.append(action)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if date_from is not None:
            clauses.append("created_at >= ?")
            params.append(date_from)
        if date_to is not None:
            clauses.append("created_at <= ?")
            params.append(date_to)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._backend.query_all(
            f"SELECT * FROM audit_logs{where} ORDER BY created_at DESC LIMIT ?",  # noqa: S608
            tuple(params),
        )
        return [_legacy_audit_to_record(row) for row in rows]

    # ---- API pública: dispatch según modo ----

    def get_user_by_username(self, username: str) -> Any:
        if self._is_async:
            # Modo async: retorna coroutine (compatible con await).
            return self._async_get_user_by_username(username)
        return self._legacy_get_user_by_username(username)

    def get_user_by_id(self, user_id: UUID) -> Any:
        if self._is_async:
            return self._async_get_user_by_id(user_id)
        return self._legacy_get_user_by_id(user_id)

    def add_session(self, session: SessionRecord) -> Any:
        if self._is_async:
            return self._async_add_session(session)
        return self._legacy_add_session(session)

    def get_session_by_token(self, token: str) -> Any:
        if self._is_async:
            return self._async_get_session_by_token(token)
        return self._legacy_get_session_by_token(token)

    def delete_session(self, token: str) -> Any:
        if self._is_async:
            return self._async_delete_session(token)
        return self._legacy_delete_session(token)

    def add_audit_log(self, log: AuditLogRecord) -> Any:
        if self._is_async:
            return self._async_add_audit_log(log)
        return self._legacy_add_audit_log(log)

    def list_audit_logs(
        self,
        limit: int = 50,
        *,
        entity_type: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> Any:
        if self._is_async:
            return self._async_list_audit_logs(
                limit,
                entity_type=entity_type,
                action=action,
                user_id=user_id,
                date_from=date_from,
                date_to=date_to,
            )
        return self._legacy_list_audit_logs(
            limit,
            entity_type=entity_type,
            action=action,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
        )

    @property
    def is_async(self) -> bool:
        """True si el backend es AsyncSession (Postgres / SQLite async)."""
        return self._is_async


def _legacy_user_to_record(row) -> UserRecord:
    return UserRecord(
        id=UUID(row["id"]),
        username=row["username"],
        full_name=row["full_name"],
        role=row["role"],
        password_hash=row["password_hash"],
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _legacy_session_to_record(row) -> SessionRecord:
    return SessionRecord(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]),
        token=row["token"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _legacy_audit_to_record(row) -> AuditLogRecord:
    return AuditLogRecord(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]) if row["user_id"] else None,
        action=row["action"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        detail=row["detail"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _parse_dt(value: str) -> datetime:
    """Parsea ISO 8601 (acepta ``Z`` como UTC) o devuelve el valor tal cual."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
