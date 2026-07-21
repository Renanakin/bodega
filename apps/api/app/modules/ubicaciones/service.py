"""
Service de ubicaciones físicas (Fase 2).

Reglas de negocio:
- UNIQUE constraint (id_bodega, pasillo, estanteria, altura) — validado
  antes de INSERT para devolver 409 limpio (duplicate_ubicacion) en vez
  de explotar con sqlite3.IntegrityError.
- id_bodega debe apuntar a una bodega activa.
- DELETE es soft: marca ``is_active=False``.
"""

from __future__ import annotations

import uuid

from app.core.errors import DuplicateUbicacionError, UbicacionNotFoundError
from app.db.session import utcnow
from app.modules.ubicaciones.repository import UbicacionRecord, UbicacionRepository
from app.modules.ubicaciones.schemas import UbicacionCreate, UbicacionUpdate
from app.modules.warehouses.repository import WarehouseRepository


class UbicacionService:
    def __init__(
        self,
        repository: UbicacionRepository,
        warehouse_repository: WarehouseRepository,
    ) -> None:
        self._repository = repository
        self._warehouses = warehouse_repository

    def list_by_bodega(self, id_bodega: uuid.UUID) -> list[UbicacionRecord]:
        if self._warehouses.get_by_id(id_bodega) is None:
            raise UbicacionNotFoundError(str(id_bodega))
        return self._repository.list_by_bodega(id_bodega)

    def get_ubicacion(self, ubicacion_id: uuid.UUID) -> UbicacionRecord:
        ubicacion = self._repository.get_by_id(ubicacion_id)
        if ubicacion is None:
            raise UbicacionNotFoundError(str(ubicacion_id))
        return ubicacion

    def create_ubicacion(self, id_bodega: uuid.UUID, payload: UbicacionCreate) -> UbicacionRecord:
        if self._warehouses.get_by_id(id_bodega) is None:
            raise UbicacionNotFoundError(str(id_bodega))

        if (
            self._repository.find_by_slot(
                id_bodega, payload.pasillo, payload.estanteria, payload.altura
            )
            is not None
        ):
            raise DuplicateUbicacionError(
                f"Bodega {id_bodega} ya tiene la ubicación "
                f"P-{payload.pasillo:02d}/E-{payload.estanteria:02d}/"
                f"A-{payload.altura:02d}"
            )

        now = utcnow()
        ubicacion = UbicacionRecord(
            id=uuid.uuid4(),
            id_bodega=id_bodega,
            pasillo=payload.pasillo,
            estanteria=payload.estanteria,
            altura=payload.altura,
            descripcion=payload.descripcion,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        return self._repository.add(ubicacion)

    def update_ubicacion(
        self, ubicacion_id: uuid.UUID, payload: UbicacionUpdate
    ) -> UbicacionRecord:
        self.get_ubicacion(ubicacion_id)  # 404 si no existe
        now = utcnow()
        self._repository.update(
            ubicacion_id,
            descripcion=payload.descripcion,
            is_active=payload.is_active,
            updated_at=now,
        )
        return self.get_ubicacion(ubicacion_id)

    def delete_ubicacion(self, ubicacion_id: uuid.UUID) -> None:
        self.get_ubicacion(ubicacion_id)  # 404 si no existe
        self._repository.soft_delete(ubicacion_id, utcnow())
