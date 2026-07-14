from __future__ import annotations

from uuid import UUID, uuid4

from app.core.errors import DuplicateWarehouseCodeError, WarehouseNotFoundError
from app.db.session import WarehouseRecord, utcnow
from app.modules.warehouses.repository import WarehouseRepository
from app.modules.warehouses.schemas import WarehouseCreate


class WarehouseService:
    def __init__(self, repository: WarehouseRepository) -> None:
        self._repository = repository

    def list_warehouses(self) -> list[WarehouseRecord]:
        return self._repository.list()

    def get_warehouse(self, warehouse_id: UUID) -> WarehouseRecord:
        warehouse = self._repository.get_by_id(warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError(str(warehouse_id))
        return warehouse

    def create_warehouse(self, payload: WarehouseCreate) -> WarehouseRecord:
        if self._repository.get_by_code(payload.code) is not None:
            raise DuplicateWarehouseCodeError(payload.code)

        now = utcnow()
        warehouse = WarehouseRecord(
            id=uuid4(),
            code=payload.code,
            name=payload.name,
            warehouse_type=payload.warehouse_type,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        return self._repository.add(warehouse)
