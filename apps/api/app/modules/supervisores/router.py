"""Router FastAPI para supervisores (Fase 6).

Entidad de dominio separada de `users.role='supervisor'`. Representa la persona
fisica con email que recibe la notificacion de OC y autoriza por token.

Endpoints:
- GET    /api/v1/supervisores               - listar (filtro ?activo=true|false)
- POST   /api/v1/supervisores               - crear (admin only)
- GET    /api/v1/supervisores/{id}          - obtener
- PATCH  /api/v1/supervisores/{id}          - actualizar parcial (admin only)
- DELETE /api/v1/supervisores/{id}          - soft delete (admin only)
"""

from __future__ import annotations

import uuid

from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.supervisores.schemas import (
    SupervisorCreate,
    SupervisorResponse,
    SupervisorUpdate,
)
from app.modules.supervisores.service import SupervisorService
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_supervisor_service(session: AsyncSession = Depends(get_session)) -> SupervisorService:
    return SupervisorService(session)


@router.get("", response_model=list[SupervisorResponse])
async def list_supervisores(
    activo: bool | None = Query(default=None, description="Filtrar por activo (true/false)"),
    _user=Depends(get_current_user),
    service: SupervisorService = Depends(get_supervisor_service),
) -> list[SupervisorResponse]:
    supers = await service.list_supervisores(solo_activos=activo)
    return [SupervisorResponse.model_validate(s) for s in supers]


@router.get("/{supervisor_id}", response_model=SupervisorResponse)
async def get_supervisor(
    supervisor_id: uuid.UUID,
    _user=Depends(get_current_user),
    service: SupervisorService = Depends(get_supervisor_service),
) -> SupervisorResponse:
    s = await service.get_supervisor(supervisor_id)
    return SupervisorResponse.model_validate(s)


@router.post("", response_model=SupervisorResponse, status_code=status.HTTP_201_CREATED)
async def create_supervisor(
    payload: SupervisorCreate,
    _user=Depends(require_roles("admin")),
    service: SupervisorService = Depends(get_supervisor_service),
) -> SupervisorResponse:
    s = await service.create_supervisor(payload.model_dump())
    return SupervisorResponse.model_validate(s)


@router.patch("/{supervisor_id}", response_model=SupervisorResponse)
async def update_supervisor(
    supervisor_id: uuid.UUID,
    payload: SupervisorUpdate,
    _user=Depends(require_roles("admin")),
    service: SupervisorService = Depends(get_supervisor_service),
) -> SupervisorResponse:
    data = payload.model_dump(exclude_unset=True)
    s = await service.update_supervisor(supervisor_id, data)
    return SupervisorResponse.model_validate(s)


@router.delete("/{supervisor_id}", response_model=SupervisorResponse)
async def deactivate_supervisor(
    supervisor_id: uuid.UUID,
    _user=Depends(require_roles("admin")),
    service: SupervisorService = Depends(get_supervisor_service),
) -> SupervisorResponse:
    """Soft delete: marca `activo=False` (no se elimina la fila)."""
    s = await service.deactivate_supervisor(supervisor_id)
    return SupervisorResponse.model_validate(s)
