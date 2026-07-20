"""Query: obtener orden de compra por ID o por token."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ExpiredApprovalTokenError,
    InvalidApprovalTokenError,
)
from app.core.security import (
    ApprovalTokenExpiredError,
    ApprovalTokenInvalidError,
    verify_approval_token,
)
from app.modules.notificaciones.service import NotificacionesService

from app.modules.ordenes_compra.actions._common import OrdenCompraView, require_oc, to_view


async def get_orden(
    session: AsyncSession, oc_id: uuid.UUID
) -> OrdenCompraView:
    """Obtiene una OC por ID. 404 si no existe."""
    oc = await require_oc(session, oc_id)
    return await to_view(session, oc)


async def get_orden_por_token(
    session: AsyncSession, _notif: NotificacionesService, token: str
) -> OrdenCompraView:
    """Lee la OC asociada al token (sin auth, sin mutar estado).

    Raises:
        InvalidApprovalTokenError: firma invalida o malformada.
        ExpiredApprovalTokenError: token expirado.
    """
    try:
        payload = verify_approval_token(token)
    except ApprovalTokenExpiredError as e:
        raise ExpiredApprovalTokenError() from e
    except ApprovalTokenInvalidError as e:
        raise InvalidApprovalTokenError() from e

    oc_id = uuid.UUID(payload["orden_id"])
    oc = await require_oc(session, oc_id)
    return await to_view(session, oc)
