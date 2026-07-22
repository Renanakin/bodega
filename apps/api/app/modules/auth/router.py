from __future__ import annotations

from app.core.rate_limit import rate_limit_by_key_dependency
from app.db.session import get_database, get_session
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    AuthSessionResponse,
    AuthUserResponse,
    LoginRequest,
    RefreshRequest,
)
from app.modules.auth.service import AuthService
from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# C5.2: rate limit por USERNAME (no por IP). Un atacante con botnet
# atacando un usuario especifico (credenciales validas) no podra
# bypasear el limite cambiando de IP.
#
# Limites:
#   /auth/login:   5 intentos por username por minuto.
#   /auth/refresh: 10 refreshes por refresh_token por minuto.
#
# Estos son los valores "tight" del OWASP Authentication Cheat Sheet.
# Se pueden relajar via env si se necesita (AUTH_LOGIN_RATE_LIMIT, etc)
# en una iteracion futura.

def _key_by_username(request: Request) -> str | None:
    """Extrae username del body de /auth/login. Lee el body cacheado
    por FastAPI si esta disponible, sino del stream."""
    body = getattr(request.state, "_json_body", None)
    if body and isinstance(body, dict):
        u = body.get("username")
        return u.strip().lower() if isinstance(u, str) and u.strip() else None
    return None


def _key_by_refresh_token(request: Request) -> str | None:
    """Extrae el refresh_token del body de /auth/refresh."""
    body = getattr(request.state, "_json_body", None)
    if body and isinstance(body, dict):
        rt = body.get("refresh_token")
        return rt if isinstance(rt, str) and len(rt) > 10 else None
    return None


auth_login_rate_limit = rate_limit_by_key_dependency(
    scope="auth_login",
    max_requests=5,
    window_seconds=60,
    key_extractor=_key_by_username,
)

auth_refresh_rate_limit = rate_limit_by_key_dependency(
    scope="auth_refresh",
    max_requests=10,
    window_seconds=60,
    key_extractor=_key_by_refresh_token,
)


async def get_auth_service(
    db=Depends(get_database),
    session: AsyncSession = Depends(get_session),
) -> AuthService:
    """Elige el backend segun el modo del lifespan.

    - Modo legacy / SQLite async: ``db`` (SQLiteDatabase) está disponible.
    - Modo Postgres: ``db`` es None; usamos ``session`` (AsyncSession).
    """
    backend = db if db is not None else session
    return AuthService(AuthRepository(backend))


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return None


async def get_current_user(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
):
    return await service.get_user_by_token(_extract_bearer_token(authorization))


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
    session: AsyncSession = Depends(get_session),
) -> AuthSessionResponse:
    # C5.2: rate limit inline (no como dependency) para que el body
    # ya este parseado cuando hacemos el check.
    from fastapi import HTTPException, status
    from app.core.rate_limit import get_rate_limiter

    limiter = get_rate_limiter()
    rl = limiter.check_by_key(
        key=payload.username.strip().lower(),
        scope="auth_login",
        max_requests=5,
        window_seconds=60,
    )
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limited",
                "message": (
                    f"Demasiados intentos. Reintente en "
                    f"{rl.retry_after_seconds}s."
                ),
                "extra": {"retry_after": rl.retry_after_seconds},
            },
            headers={"Retry-After": str(rl.retry_after_seconds)},
        )

    user, session_view = await service.login(payload.username, payload.password)
    # En modo async, el repo agregó la sesión a la AsyncSession pero NO
    # hizo commit. Hacemos commit explícito para que el siguiente
    # ``get_user_by_token`` la vea.
    if service._repository.is_async:
        await session.commit()
    return AuthSessionResponse(
        token=session_view.token,
        refresh_token=session_view.refresh_token,
        expires_at=session_view.expires_at,
        refresh_expires_at=session_view.refresh_expires_at,
    )


@router.post("/refresh", response_model=AuthSessionResponse)
async def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
    session: AsyncSession = Depends(get_session),
) -> AuthSessionResponse:
    """C5.1: rota un par access+refresh usando el refresh_token. C5.2: rate-limit."""
    # C5.2: rate limit inline por refresh_token (10 por minuto).
    from fastapi import HTTPException, status
    from app.core.rate_limit import get_rate_limiter

    limiter = get_rate_limiter()
    rl = limiter.check_by_key(
        key=payload.refresh_token,
        scope="auth_refresh",
        max_requests=10,
        window_seconds=60,
    )
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limited",
                "message": (
                    f"Demasiados refreshes. Reintente en "
                    f"{rl.retry_after_seconds}s."
                ),
                "extra": {"retry_after": rl.retry_after_seconds},
            },
            headers={"Retry-After": str(rl.retry_after_seconds)},
        )

    new_session_view = await service.refresh_session(payload.refresh_token)
    if service._repository.is_async:
        await session.commit()
    return AuthSessionResponse(
        token=new_session_view.token,
        refresh_token=new_session_view.refresh_token,
        expires_at=new_session_view.expires_at,
        refresh_expires_at=new_session_view.refresh_expires_at,
    )


@router.post(
    "/logout",
    status_code=204,
    response_class=Response,
)
async def logout(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
    session: AsyncSession = Depends(get_session),
) -> Response:
    token = _extract_bearer_token(authorization)
    await service.logout(token)
    if token and service._repository.is_async:
        await session.commit()
    return Response(status_code=204)


@router.get("/me", response_model=AuthUserResponse)
async def me(user=Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse.model_validate(user)
