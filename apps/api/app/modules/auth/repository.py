from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.db.session import AuditLogRecord, SessionRecord, SQLiteDatabase, UserRecord


def _to_user(row) -> UserRecord:
    return UserRecord(
        id=UUID(row["id"]),
        username=row["username"],
        full_name=row["full_name"],
        role=row["role"],
        password_hash=row["password_hash"],
        is_active=bool(row["is_active"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _to_session(row) -> SessionRecord:
    return SessionRecord(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]),
        token=row["token"],
        expires_at=datetime.fromisoformat(row["expires_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _to_audit_log(row) -> AuditLogRecord:
    return AuditLogRecord(
        id=UUID(row["id"]),
        user_id=UUID(row["user_id"]) if row["user_id"] else None,
        action=row["action"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        detail=row["detail"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class AuthRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def get_user_by_username(self, username: str) -> UserRecord | None:
        row = self._db.query_one("SELECT * FROM users WHERE username = ?", (username,))
        return _to_user(row) if row is not None else None

    def get_user_by_id(self, user_id: UUID) -> UserRecord | None:
        row = self._db.query_one("SELECT * FROM users WHERE id = ?", (str(user_id),))
        return _to_user(row) if row is not None else None

    def add_session(self, session: SessionRecord) -> SessionRecord:
        self._db.execute(
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

    def get_session_by_token(self, token: str) -> SessionRecord | None:
        row = self._db.query_one("SELECT * FROM user_sessions WHERE token = ?", (token,))
        return _to_session(row) if row is not None else None

    def delete_session(self, token: str) -> None:
        self._db.execute("DELETE FROM user_sessions WHERE token = ?", (token,))

    def add_audit_log(self, log: AuditLogRecord) -> AuditLogRecord:
        self._db.execute(
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

    def list_audit_logs(self, limit: int = 50) -> list[AuditLogRecord]:
        rows = self._db.query_all(
            "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [_to_audit_log(row) for row in rows]
