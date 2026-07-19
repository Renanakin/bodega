from __future__ import annotations

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
    limit: int = Query(default=50, ge=1, le=200),
    _: object = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> list[AuditLogResponse]:
    return service.list_audit_logs(limit)
