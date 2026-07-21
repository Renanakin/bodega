from __future__ import annotations

from uuid import UUID

from app.db.session import SQLiteDatabase, get_database
from app.modules.audit.schemas import AuditLogResponse
from app.modules.auth.repository import AuthRepository
from app.modules.auth.router import get_current_user
from app.modules.auth.service import AuthService
from fastapi import APIRouter, Depends, Query

router = APIRouter()


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
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
    _: object = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> list[AuditLogResponse]:
    return service.list_audit_logs(
        limit,
        entity_type=entity_type,
        action=action,
        user_id=str(user_id) if user_id else None,
        date_from=date_from,
        date_to=date_to,
    )
