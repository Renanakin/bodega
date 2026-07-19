from __future__ import annotations

from app.db.session import SQLiteDatabase, get_database
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import AuthSessionResponse, AuthUserResponse, LoginRequest
from app.modules.auth.service import AuthService
from fastapi import APIRouter, Depends, Header, Response

router = APIRouter()


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return None


def get_current_user(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
):
    return service.get_user_by_token(_extract_bearer_token(authorization))


@router.post("/login", response_model=AuthSessionResponse)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthSessionResponse:
    _, session = service.login(payload.username, payload.password)
    return AuthSessionResponse(token=session.token, expires_at=session.expires_at)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
) -> Response:
    service.logout(_extract_bearer_token(authorization))
    response.status_code = 204
    return response


@router.get("/me", response_model=AuthUserResponse)
def me(user=Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse.model_validate(user)
