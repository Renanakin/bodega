"""Router LEGACY para inspeccionar email_outbox (debug/admin).

.. deprecated::
    Este modulo (``notifications/`` en ingles) es LEGACY de Fase 7 (SMTP outbox).
    El modulo vivo para notificaciones in-app del operador es
    ``app/modules/notificaciones/router.py`` (en espanol, Fase 8).

    Ambos se montan bajo ``/api/v1/notificaciones`` pero con paths distintos
    (no chocan). Mantener ambos por compatibilidad 6 meses segun
    el patron de deprecation gradual del proyecto (ver ``transfers/``).
    Una vez cumplido el plazo, eliminar este router.
"""

from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.db.models.ordenes_compra import EmailOutbox
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

router = APIRouter()


class EmailOutboxResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    to_email: str
    subject: str
    status: str
    attempts: int
    last_error: str | None
    sent_at: str | None
    created_at: str


@router.get("/outbox", response_model=list[EmailOutboxResponse])
async def list_outbox(
    status: str | None = Query(default=None),
    _=Depends(require_roles("admin", "supervisor")),
    session: AsyncSession = Depends(get_session),
) -> list[EmailOutboxResponse]:
    stmt = select(EmailOutbox).order_by(EmailOutbox.created_at.desc()).limit(100)
    if status:
        stmt = stmt.where(EmailOutbox.status == status)
    result = await session.execute(stmt)
    return [
        EmailOutboxResponse(
            id=o.id,
            to_email=o.to_email,
            subject=o.subject,
            status=o.status,
            attempts=o.attempts,
            last_error=o.last_error,
            sent_at=o.sent_at.isoformat() if o.sent_at else None,
            created_at=o.created_at.isoformat(),
        )
        for o in result.scalars().all()
    ]
