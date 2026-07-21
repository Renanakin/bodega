from __future__ import annotations

from uuid import UUID

from app.db.session import get_database, get_session
from app.modules.audit.schemas import AuditLogResponse
from app.modules.auth.repository import AuthRepository
from app.modules.auth.router import get_current_user
from app.modules.auth.service import AuthService
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


async def get_auth_service(
    db=Depends(get_database),
    session: AsyncSession = Depends(get_session),
) -> AuthService:
    backend = db if db is not None else session
    return AuthService(AuthRepository(backend))


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200, description="Maximo de registros a devolver."),
    entity_type: str | None = Query(
        default=None,
        max_length=80,
        description="Filtra por tipo de entidad (ej. 'warehouse', 'product', 'solicitud').",
    ),
    action: str | None = Query(
        default=None,
        max_length=80,
        description="Filtra por accion (ej. 'create', 'approve', 'login', 'dispatch').",
    ),
    user_id: UUID | None = Query(
        default=None,
        description="Filtra por UUID del usuario que realizo la accion.",
    ),
    date_from: str | None = Query(
        default=None,
        description="Filtra desde fecha ISO 8601 inclusive (created_at >= date_from).",
    ),
    date_to: str | None = Query(
        default=None,
        description="Filtra hasta fecha ISO 8601 inclusive (created_at <= date_to).",
    ),
    _user=Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> list[AuditLogResponse]:
    user_id_str = str(user_id) if user_id is not None else None
    rows = await service.list_audit_logs(
        limit=limit,
        entity_type=entity_type,
        action=action,
        user_id=user_id_str,
        date_from=date_from,
        date_to=date_to,
    )
    return [AuditLogResponse.model_validate(r) for r in rows]


@router.get("/actions", response_model=list[str])
async def list_audit_actions(
    _user=Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> list[str]:
    rows = await service.list_audit_logs(limit=200)
    seen: list[str] = []
    for r in rows:
        if r.action not in seen:
            seen.append(r.action)
    return seen
