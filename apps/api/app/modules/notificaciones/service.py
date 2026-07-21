"""Service para notificaciones in-app (Fase 8 + Deuda #7).

Logica de negocio sobre la tabla ``notificaciones`` (modelo ORM definido
en ``app.db.models.notificaciones``). La capa HTTP (router) traduce
pydantic <-> ORM y mapea errores de dominio.

Operaciones de lectura (Fase 8):
- ``list_for_user``         — lista las notificaciones del usuario (paginated
  via ``limit``).
- ``count_for_user``        — total + no_leidas (para badge en la campanita).
- ``mark_read``             — marca 1 notificacion como leida.
- ``mark_all_read``         — marca TODAS como leidas.

Operaciones de escritura (Deuda #7 — automáticas desde el workflow):
- ``notify_user``           — alias semantico de ``create_notification``.
- ``notify_users``          — bulk insert a N usuarios en una sola query.
- ``notify_role_except_actor`` — broadcast a todos los users con esos roles,
  excluyendo al actor que disparo la transicion (ej. cuando un operador
  crea una solicitud, no se manda la notificacion a si mismo).

Idempotencia:
- ``mark_read`` sobre una notif ya leida: no falla, retorna el mismo record
  con ``read_at`` inalterado.
- ``mark_all_read`` cuando no hay no_leidas: retorna 0 (cero updates).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from app.core.errors import NotificationNotFoundError
from app.core.logging import get_logger
from app.db.models.notificaciones import Notificacion
from app.db.models.users import User, UserRole
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


class NotificacionesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: uuid.UUID, limit: int = 50) -> list[Notificacion]:
        """Lista las notificaciones mas recientes del usuario."""
        stmt = (
            select(Notificacion)
            .where(Notificacion.user_id == user_id)
            .order_by(Notificacion.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: uuid.UUID) -> tuple[int, int]:
        """Retorna ``(total, no_leidas)`` para el badge."""
        total_stmt = select(func.count(Notificacion.id)).where(Notificacion.user_id == user_id)
        total = (await self._session.execute(total_stmt)).scalar_one()
        no_leidas_stmt = select(func.count(Notificacion.id)).where(
            Notificacion.user_id == user_id,
            Notificacion.leida == False,  # noqa: E712
        )
        no_leidas = (await self._session.execute(no_leidas_stmt)).scalar_one()
        return int(total or 0), int(no_leidas or 0)

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> Notificacion:
        """Marca una notificacion como leida (idempotente).

        Verifica que la notificacion pertenezca al usuario (404 si no),
        para evitar que un user marque como leida la notif de otro.
        """
        stmt = select(Notificacion).where(
            Notificacion.id == notification_id,
            Notificacion.user_id == user_id,
        )
        notif = (await self._session.execute(stmt)).scalar_one_or_none()
        if notif is None:
            raise NotificationNotFoundError(str(notification_id))
        if not notif.leida:
            notif.leida = True
            notif.read_at = datetime.now(UTC)
            await self._session.commit()
            await self._session.refresh(notif)
            log.info(
                "notification.marked_read",
                notification_id=str(notif.id),
                user_id=str(user_id),
            )
        return notif

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        """Marca TODAS las no_leidas del usuario como leidas. Retorna el count."""
        now = datetime.now(UTC)
        stmt = (
            update(Notificacion)
            .where(Notificacion.user_id == user_id, Notificacion.leida == False)  # noqa: E712
            .values(leida=True, read_at=now)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        count = int(result.rowcount or 0)
        log.info("notification.marked_all_read", user_id=str(user_id), count=count)
        return count

    # ============================================================ write API

    async def notify_user(
        self,
        *,
        user_id: uuid.UUID,
        tipo: str,
        titulo: str,
        mensaje: str | None = None,
        payload: str | None = None,
    ) -> Notificacion:
        """Inserta una notificacion para un usuario. Llamado internamente
        desde ``SolicitudService`` / ``OrdenCompraService`` cuando ocurre
        una transicion de estado relevante.
        """
        return await self.create_notification(
            user_id=user_id,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            payload=payload,
        )

    async def notify_users(
        self,
        *,
        user_ids: Iterable[uuid.UUID],
        tipo: str,
        titulo: str,
        mensaje: str | None = None,
        payload: str | None = None,
    ) -> int:
        """Bulk insert de notificaciones a N usuarios (1 sola query INSERT).

        Retorna el numero de notificaciones creadas. Si ``user_ids`` esta
        vacio, retorna 0 sin tocar la BD.

        Usado cuando la audiencia es un conjunto conocido de usuarios
        (ej. un grupo reducido de operadores, o todos los admins).
        """
        ids = list({uid for uid in user_ids if uid is not None})
        if not ids:
            return 0
        now = datetime.now(UTC)
        rows = [
            {
                "id": uuid.uuid4(),
                "user_id": uid,
                "tipo": tipo,
                "titulo": titulo,
                "mensaje": mensaje,
                "payload": payload,
                "leida": False,
                "created_at": now,
            }
            for uid in ids
        ]
        await self._session.execute(insert(Notificacion), rows)
        await self._session.commit()
        log.info(
            "notification.broadcast",
            tipo=tipo,
            recipients=len(rows),
        )
        return len(rows)

    async def notify_role_except_actor(
        self,
        *,
        actor_id: uuid.UUID | None,
        roles: Iterable[UserRole],
        tipo: str,
        titulo: str,
        mensaje: str | None = None,
        payload: str | None = None,
    ) -> int:
        """Broadcast a todos los users con alguno de los roles dados,
        excluyendo al ``actor_id`` (para no autoreportarse).

        Usado por el workflow para que, p.ej., cuando un operador crea
        una solicitud, los admin+supervisor la vean, pero el operador
        que la creo no.

        Si ``actor_id`` es None, NO se excluye a nadie (caso del flujo
        publico via token, donde no hay un usuario autenticado).

        Retorna el numero de notificaciones creadas.
        """
        roles_list = list(roles)
        if not roles_list:
            return 0
        stmt = select(User.id).where(
            User.role.in_(roles_list),
            User.is_active.is_(True),
        )
        if actor_id is not None:
            stmt = stmt.where(User.id != actor_id)
        result = await self._session.execute(stmt)
        user_ids = [row[0] for row in result.all()]
        return await self.notify_users(
            user_ids=user_ids,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            payload=payload,
        )

    async def create_notification(
        self,
        *,
        user_id: uuid.UUID,
        tipo: str,
        titulo: str,
        mensaje: str | None = None,
        payload: str | None = None,
    ) -> Notificacion:
        """Inserta una notificacion. Pensado para uso interno del back
        (e.g. cuando ``SolicitudService`` aprueba, emite notif al operador).

        Por ahora NO se llama desde los services existentes (Fase 8 no
        toca SolicitudService); la UI las crea via seeder o via tests.
        Queda expuesta para Fases siguientes.
        """
        n = Notificacion(
            id=uuid.uuid4(),
            user_id=user_id,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            payload=payload,
            leida=False,
        )
        self._session.add(n)
        await self._session.commit()
        await self._session.refresh(n)
        log.info("notification.created", notification_id=str(n.id), tipo=tipo)
        return n
