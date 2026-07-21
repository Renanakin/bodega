from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.core.errors import AuthenticationError, InvalidCredentialsError
from app.db.session import AuditLogRecord, SessionRecord, UserRecord, utcnow
from app.modules.auth.repository import AuthRepository
from app.modules.auth.security import issue_token, session_expiration, verify_password


@dataclass(slots=True)
class AuthSessionView:
    token: str
    expires_at: object


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self._repository = repository

    def login(self, username: str, password: str) -> tuple[UserRecord, AuthSessionView]:
        user = self._repository.get_user_by_username(username.strip().lower())
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        session = SessionRecord(
            id=uuid4(),
            user_id=user.id,
            token=issue_token(),
            expires_at=session_expiration(),
            created_at=utcnow(),
        )
        self._repository.add_session(session)
        self.audit(
            user_id=user.id,
            action="auth.login",
            entity_type="session",
            entity_id=session.token,
            detail=f"Inicio de sesion de {user.username}",
        )
        return user, AuthSessionView(token=session.token, expires_at=session.expires_at)

    def get_user_by_token(self, token: str | None) -> UserRecord:
        if not token:
            raise AuthenticationError()
        session = self._repository.get_session_by_token(token)
        if session is None or session.expires_at <= utcnow():
            if session is not None:
                self._repository.delete_session(token)
            raise AuthenticationError()
        user = self._repository.get_user_by_id(session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError()
        return user

    def logout(self, token: str | None) -> None:
        if token:
            self._repository.delete_session(token)

    def list_audit_logs(
        self,
        limit: int = 50,
        *,
        entity_type: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        return self._repository.list_audit_logs(
            limit,
            entity_type=entity_type,
            action=action,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
        )

    def audit(
        self,
        *,
        user_id,
        action: str,
        entity_type: str,
        entity_id: str | None,
        detail: str | None,
    ) -> None:
        self._repository.add_audit_log(
            AuditLogRecord(
                id=uuid4(),
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                detail=detail,
                created_at=utcnow(),
            )
        )
