"""Router FastAPI para notificaciones in-app (Fase 8).

Endpoints:
- ``GET  /api/v1/notificaciones``                  — lista del usuario actual.
- ``GET  /api/v1/notificaciones/no-leidas/count``  — para el badge.
- ``POST /api/v1/notificaciones/{id}/marcar-leida`` — marca una.
- ``POST /api/v1/notificaciones/marcar-todas-leidas`` — bulk.
"""
from __future__ import annotations

import uuid

from app.db.session import get_session
from app.modules.auth.router import get_current_user
from app.modules.notificaciones.schemas import (
    NotificacionCount,
    NotificacionResponse,
)
from app.modules.notificaciones.service import NotificacionesService
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_notificaciones_service(
    session: AsyncSession = Depends(get_session),
) -> NotificacionesService:
    return NotificacionesService(session)


@router.get("", response_model=list[NotificacionResponse])
async def list_notificaciones(
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_current_user),
    service: NotificacionesService = Depends(get_notificaciones_service),
) -> list[NotificacionResponse]:
    """Lista las notificaciones mas recientes del usuario actual."""
    items = await service.list_for_user(user.id, limit=limit)
    return [NotificacionResponse.model_validate(n) for n in items]


@router.get("/no-leidas/count", response_model=NotificacionCount)
async def count_no_leidas(
    user=Depends(get_current_user),
    service: NotificacionesService = Depends(get_notificaciones_service),
) -> NotificacionCount:
    """Retorna (total, no_leidas) para el badge de la campanita."""
    total, no_leidas = await service.count_for_user(user.id)
    return NotificacionCount(total=total, no_leidas=no_leidas)


@router.post(
    "/{notification_id}/marcar-leida", response_model=NotificacionResponse
)
async def mark_leida(
    notification_id: uuid.UUID,
    user=Depends(get_current_user),
    service: NotificacionesService = Depends(get_notificaciones_service),
) -> NotificacionResponse:
    """Marca una notificacion del usuario actual como leida."""
    n = await service.mark_read(notification_id, user.id)
    return NotificacionResponse.model_validate(n)


@router.post("/marcar-todas-leidas", response_model=NotificacionCount)
async def mark_todas_leidas(
    user=Depends(get_current_user),
    service: NotificacionesService = Depends(get_notificaciones_service),
) -> NotificacionCount:
    """Marca TODAS las no_leidas del usuario actual como leidas."""
    count = await service.mark_all_read(user.id)
    # Despues de marcar, no_leidas = 0. Refetch para total real.
    total, _ = await service.count_for_user(user.id)
    return NotificacionCount(total=total, no_leidas=0)
