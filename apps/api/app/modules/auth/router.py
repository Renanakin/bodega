from __future__ import annotations

from app.db.session import get_database, get_session
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import AuthSessionResponse, AuthUserResponse, LoginRequest
from app.modules.auth.service import AuthService
from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


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
    user, session_view = await service.login(payload.username, payload.password)
    # En modo async, el repo agregó la sesión a la AsyncSession pero NO
    # hizo commit. Hacemos commit explícito para que el siguiente
    # ``get_user_by_token`` la vea.
    if service._repository.is_async:
        await session.commit()
    return AuthSessionResponse(token=session_view.token, expires_at=session_view.expires_at)


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
