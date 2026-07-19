"""CRUD de Supervisores (Fase 6).

Logica de negocio. La capa HTTP (router) solo traduce pydantic <-> dict
y mapea errores de dominio a status codes via `domain_error_handler`.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.core.errors import DuplicateSupervisorEmailError, SupervisorNotFoundError
from app.core.logging import get_logger
from app.db.models.supervisores import Supervisor
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


class SupervisorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_supervisores(self, solo_activos: bool | None = None) -> list[Supervisor]:
        """Lista todos los supervisores ordenados por nombre.

        Args:
            solo_activos: si True, solo `activo=True`. Si False o None, todos.

        Returns:
            Lista de Supervisor.
        """
        stmt = select(Supervisor).order_by(Supervisor.nombre)
        if solo_activos is True:
            stmt = stmt.where(Supervisor.activo == True)  # noqa: E712
        elif solo_activos is False:
            stmt = stmt.where(Supervisor.activo == False)  # noqa: E712
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_supervisor(self, supervisor_id: uuid.UUID) -> Supervisor:
        s = await self._session.get(Supervisor, supervisor_id)
        if s is None:
            raise SupervisorNotFoundError(str(supervisor_id))
        return s

    async def create_supervisor(self, data: dict[str, Any]) -> Supervisor:
        """Crea un supervisor validando email unico.

        Raises:
            DuplicateSupervisorEmailError: si el email ya existe.
        """
        email_norm = data["email"].lower().strip()

        existing = (
            await self._session.execute(
                select(Supervisor).where(Supervisor.email == email_norm)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateSupervisorEmailError(email_norm)

        s = Supervisor(
            id=uuid.uuid4(),
            nombre=data["nombre"].strip(),
            email=email_norm,
            telefono=data.get("telefono"),
            cargo=data.get("cargo"),
            activo=True,
        )
        self._session.add(s)
        try:
            await self._session.commit()
        except IntegrityError as e:
            # Respaldo: carrera entre check y commit (UNIQUE constraint)
            await self._session.rollback()
            raise DuplicateSupervisorEmailError(email_norm) from e
        await self._session.refresh(s)
        log.info("supervisor.created", supervisor_id=str(s.id), email=email_norm)
        return s

    async def update_supervisor(
        self, supervisor_id: uuid.UUID, data: dict[str, Any]
    ) -> Supervisor:
        """Actualiza campos parciales (PATCH).

        Si se intenta desactivar (`activo=False`), se considera soft-delete.
        """
        s = await self.get_supervisor(supervisor_id)
        for k, v in data.items():
            if v is not None:
                setattr(s, k, v)
        await self._session.commit()
        await self._session.refresh(s)
        log.info("supervisor.updated", supervisor_id=str(s.id), fields=list(data.keys()))
        return s

    async def deactivate_supervisor(self, supervisor_id: uuid.UUID) -> Supervisor:
        """Soft delete: marca `activo=False`.

        No se elimina la fila para preservar historial de OCs asociadas
        (la FK en `ordenes_compra` exige RESTRICT).
        """
        s = await self.get_supervisor(supervisor_id)
        if not s.activo:
            return s  # idempotente
        s.activo = False
        await self._session.commit()
        await self._session.refresh(s)
        log.info("supervisor.deactivated", supervisor_id=str(s.id))
        return s
