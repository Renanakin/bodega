"""AuthService (FIX BUG-002 compatible legacy + async).

FIX BUG-002: este repository soporta AMBOS backends (AsyncSession O
SQLiteDatabase legacy). El ``AuthService`` expone metodos ``async``
que internamente resuelven coroutines (modo async) o valores
sincronicos (modo legacy) con ``_maybe_await``.

El resto de la app (100+ callers) sigue funcionando porque
``service.audit()`` sigue siendo ``def`` (no requiere await) y
``asyncio.iscoroutine`` se usa internamente para detectar el modo.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from app.core.errors import AuthenticationError, InvalidCredentialsError
from app.db.session import AuditLogRecord, SessionRecord, UserRecord, utcnow
from app.modules.auth.repository import AuthRepository
from app.modules.auth.security import issue_token, session_expiration, verify_password


async def _maybe_await(value: Any) -> Any:
    """Si ``value`` es una coroutine, la espera; sino lo devuelve tal cual."""
    if inspect.iscoroutine(value):
        return await value
    return value


@dataclass(slots=True)
class AuthSessionView:
    token: str
    expires_at: object


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self._repository = repository

    async def login(
        self, username: str, password: str
    ) -> tuple[UserRecord, AuthSessionView]:
        user = await _maybe_await(self._repository.get_user_by_username(username.strip().lower()))
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        session = SessionRecord(
            id=uuid4(),
            user_id=user.id,
            token=issue_token(),
            expires_at=session_expiration(),
            created_at=utcnow(),
        )
        await _maybe_await(self._repository.add_session(session))
        await self.audit(
            user_id=user.id,
            action="auth.login",
            entity_type="session",
            entity_id=session.token,
            detail=f"Inicio de sesion de {user.username}",
        )
        return user, AuthSessionView(token=session.token, expires_at=session.expires_at)

    async def get_user_by_token(self, token: str | None) -> UserRecord:
        if not token:
            raise AuthenticationError()
        session = await _maybe_await(self._repository.get_session_by_token(token))
        if session is not None and session.expires_at.tzinfo is None:
            from datetime import UTC

            session.expires_at = session.expires_at.replace(tzinfo=UTC)
        if session is None or session.expires_at <= utcnow():
            if session is not None:
                await _maybe_await(self._repository.delete_session(token))
            raise AuthenticationError()
        user = await _maybe_await(self._repository.get_user_by_id(session.user_id))
        if user is None or not user.is_active:
            raise AuthenticationError()
        return user

    async def logout(self, token: str | None) -> None:
        if token:
            await _maybe_await(self._repository.delete_session(token))

    async def list_audit_logs(
        self,
        limit: int = 50,
        *,
        entity_type: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ):
        return await _maybe_await(
            self._repository.list_audit_logs(
                limit,
                entity_type=entity_type,
                action=action,
                user_id=user_id,
                date_from=date_from,
                date_to=date_to,
            )
        )

    async def audit(
        self,
        *,
        user_id,
        action: str,
        entity_type: str,
        entity_id: str | None,
        detail: str | None,
    ) -> None:
        """Registra un evento de auditoria.

        FIX: este metodo es ``async`` para que el router lo pueda ``await``.
        Antes era sync + fire-and-forget, lo que causaba que el flush
        se perdiera en algunos tests (la coroutine quedaba pendiente).
        """
        result = self._repository.add_audit_log(
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
        await _maybe_await(result)
