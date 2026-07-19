"""Router para inspeccionar email_outbox (debug/admin)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.ordenes_compra import EmailOutbox
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles


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
