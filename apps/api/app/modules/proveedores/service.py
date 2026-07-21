"""CRUD de Proveedores (Fase 8).

Logica de negocio. La capa HTTP (router) solo traduce pydantic <-> ORM
y mapea errores de dominio a status codes via ``domain_error_handler``.

Reglas:
- ``nombre`` unico (case-insensitive): dos proveedores no pueden llamarse
  igual aunque difieran en mayusculas.
- ``rut`` unico cuando viene; opcional.
- Soft delete via ``activo=False`` (no se borra la fila) para preservar el
  historial de Ordenes de Compra que lo referencian.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.errors import (
    DuplicateProveedorNombreError,
    DuplicateProveedorRutError,
    ProveedorNotFoundError,
)
from app.core.logging import get_logger
from app.db.models.proveedores import Proveedor
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


class ProveedorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_proveedores(self, solo_activos: bool | None = None) -> list[Proveedor]:
        """Lista proveedores ordenados por nombre.

        Args:
            solo_activos: True => solo ``activo=True``; False => solo inactivos;
                None => todos.

        Returns:
            Lista de ``Proveedor`` (modelo ORM).
        """
        stmt = select(Proveedor).order_by(Proveedor.nombre)
        if solo_activos is True:
            stmt = stmt.where(Proveedor.activo == True)  # noqa: E712
        elif solo_activos is False:
            stmt = stmt.where(Proveedor.activo == False)  # noqa: E712
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_proveedor(self, proveedor_id: uuid.UUID) -> Proveedor:
        p = await self._session.get(Proveedor, proveedor_id)
        if p is None:
            raise ProveedorNotFoundError(str(proveedor_id))
        return p

    async def create_proveedor(self, data: dict[str, Any]) -> Proveedor:
        """Crea un proveedor validando nombre unico y rut opcional unico.

        Raises:
            DuplicateProveedorNombreError: si el nombre (case-insensitive) ya existe.
            DuplicateProveedorRutError: si el RUT ya existe.
        """
        nombre_norm = data["nombre"].strip()
        existing = (
            await self._session.execute(
                select(Proveedor).where(Proveedor.nombre.ilike(nombre_norm))
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateProveedorNombreError(nombre_norm)

        rut = data.get("rut")
        if rut:
            existing_rut = (
                await self._session.execute(select(Proveedor).where(Proveedor.rut == rut))
            ).scalar_one_or_none()
            if existing_rut is not None:
                raise DuplicateProveedorRutError(rut)

        p = Proveedor(
            id=uuid.uuid4(),
            nombre=nombre_norm,
            rut=rut,
            email=data.get("email"),
            telefono=data.get("telefono"),
            direccion=data.get("direccion"),
            contacto_nombre=data.get("contacto_nombre"),
            lead_time_dias=data.get("lead_time_dias", 7),
            activo=data.get("activo", True),
        )
        self._session.add(p)
        try:
            await self._session.commit()
        except IntegrityError as e:
            await self._session.rollback()
            # Carrera: UNIQUE constraint (nombre o RUT) violada entre check y commit.
            if rut and "rut" in str(e.orig).lower():
                raise DuplicateProveedorRutError(rut) from e
            raise DuplicateProveedorNombreError(nombre_norm) from e
        await self._session.refresh(p)
        log.info("proveedor.created", proveedor_id=str(p.id), nombre=nombre_norm)
        return p

    async def update_proveedor(self, proveedor_id: uuid.UUID, data: dict[str, Any]) -> Proveedor:
        """Actualiza campos parciales (PATCH)."""
        p = await self.get_proveedor(proveedor_id)

        # Validar nombre unico si se intenta renombrar.
        if "nombre" in data and data["nombre"] is not None:
            new_nombre = data["nombre"].strip()
            if new_nombre.lower() != p.nombre.lower():
                existing = (
                    await self._session.execute(
                        select(Proveedor).where(Proveedor.nombre.ilike(new_nombre))
                    )
                ).scalar_one_or_none()
                if existing is not None and existing.id != proveedor_id:
                    raise DuplicateProveedorNombreError(new_nombre)
                p.nombre = new_nombre

        # Validar RUT unico si se intenta cambiar.
        if "rut" in data and data["rut"] is not None:
            new_rut = data["rut"]
            existing_rut = (
                await self._session.execute(select(Proveedor).where(Proveedor.rut == new_rut))
            ).scalar_one_or_none()
            if existing_rut is not None and existing_rut.id != proveedor_id:
                raise DuplicateProveedorRutError(new_rut)
            p.rut = new_rut

        # Aplicar el resto de campos.
        for field, value in data.items():
            if field in ("nombre", "rut"):
                continue  # ya manejados
            if value is not None:
                setattr(p, field, value)

        try:
            await self._session.commit()
        except IntegrityError as e:
            await self._session.rollback()
            if "rut" in str(e.orig).lower():
                raise DuplicateProveedorRutError(data.get("rut", "")) from e
            raise DuplicateProveedorNombreError(data.get("nombre", p.nombre)) from e
        await self._session.refresh(p)
        log.info("proveedor.updated", proveedor_id=str(p.id), fields=list(data.keys()))
        return p

    async def soft_delete_proveedor(self, proveedor_id: uuid.UUID) -> Proveedor:
        """Soft delete: marca ``activo=False`` (no se elimina la fila).

        Idempotente: si ya estaba inactivo, retorna el mismo registro sin error.
        """
        p = await self.get_proveedor(proveedor_id)
        if not p.activo:
            return p
        p.activo = False
        await self._session.commit()
        await self._session.refresh(p)
        log.info("proveedor.deactivated", proveedor_id=str(p.id))
        return p
