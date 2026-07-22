"""
Helper de audit asíncrono (Fase 3+).

Centraliza la lógica de ``audit_logs`` que antes vivía en cada router
como un bloque de 15 líneas. El patrón viejo:

    auth_service.audit(
        user_id=user.id,
        action="warehouse.create",
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        detail="...",
    )

Se reemplaza por:

    await record_audit(
        session=session,  # AsyncSession del request
        user_id=user.id,
        action="warehouse.create",
        entity_type="warehouse",
        entity_id=str(warehouse.id),
        detail="...",
    )

Convenciones:
- Comparte la ``AsyncSession`` del request (no sesión independiente)
  para que el orden de commits refleje el orden temporal real.
- Best-effort: NUNCA falla la operación principal. Si el commit del
  audit rebota, se loguea como warning y se continúa.
- El commit lo hace el caller (router) junto con la mutación principal;
  ``record_audit`` solo hace ``session.add()`` + ``flush()``.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.db.models.users import AuditLog
from app.db.session import utcnow
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


async def record_audit(
    session: AsyncSession,
    *,
    user_id: Any,
    action: str,
    entity_type: str,
    entity_id: str | None,
    detail: str | None,
) -> None:
    """Inserta un audit log de forma best-effort.

    Args:
        session: AsyncSession del request. Comparte la transacción
            con la operación principal; ``record_audit`` hace commit
            explicito para que el audit quede durable inmediatamente,
            sin depender del commit del caller.
        user_id: UUID del usuario que ejecutó la acción.
        action: nombre simbólico (ej. ``warehouse.create``).
        entity_type: tipo de entidad afectada (ej. ``warehouse``).
        entity_id: ID de la entidad (string UUID o lo que aplique).
        detail: descripción libre (o None).
    """
    try:
        log_row = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            created_at=utcnow(),
        )
        session.add(log_row)
        await session.flush()
        # Commit explicito para que el audit quede durable ya, sin
        # depender de que el caller (o el get_session al final del
        # request) lo haga. Si falla el commit, log warning y continuar.
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        # Audit best-effort: nunca falla la operación principal.
        log.warning("audit.record_failed", action=action, error=str(exc))


__all__ = ["record_audit"]
