from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID
from uuid import uuid4

from app.core.errors import (
    InsufficientStockError,
    InvalidTransferError,
    InvalidTransferQuantityError,
    InvalidTransferStatusError,
    ProductNotFoundError,
    TransferNotFoundError,
    WarehouseNotFoundError,
)
from app.db.session import InventoryMovementRecord, StockLevelRecord, TransferRecord, utcnow
from app.modules.inventory.repository import InventoryRepository
from app.modules.products.repository import ProductRepository
from app.modules.transfers.repository import TransferRepository
from app.modules.transfers.schemas import TransferCreate, TransferDispatch, TransferReceive, TransferUpdate
from app.modules.warehouses.repository import WarehouseRepository


@dataclass(slots=True)
class TransferView:
    id: UUID
    code: str
    from_warehouse_id: UUID
    from_warehouse_code: str
    from_warehouse_name: str
    to_warehouse_id: UUID
    to_warehouse_code: str
    to_warehouse_name: str
    product_id: UUID
    product_sku: str
    product_name: str
    quantity: Decimal
    received_quantity: Decimal
    status: str
    priority: str | None
    notes: str | None
    dispatch_notes: str | None
    receive_notes: str | None
    incident_type: str | None
    incident_notes: str | None
    created_at: object
    approved_at: object
    dispatched_at: object
    received_at: object


class TransferService:
    def __init__(
        self,
        transfer_repository: TransferRepository,
        inventory_repository: InventoryRepository,
        warehouse_repository: WarehouseRepository,
        product_repository: ProductRepository,
    ) -> None:
        self._transfer_repository = transfer_repository
        self._inventory_repository = inventory_repository
        self._warehouse_repository = warehouse_repository
        self._product_repository = product_repository

    def list_transfers(self) -> list[TransferView]:
        views: list[TransferView] = []
        for item in self._transfer_repository.list_transfers():
            origin = self._warehouse_repository.get_by_id(item.from_warehouse_id)
            destination = self._warehouse_repository.get_by_id(item.to_warehouse_id)
            product = self._product_repository.get_by_id(item.product_id)
            if origin is None or destination is None or product is None:
                continue
            views.append(
                TransferView(
                    id=item.id,
                    code=item.code,
                    from_warehouse_id=item.from_warehouse_id,
                    from_warehouse_code=origin.code,
                    from_warehouse_name=origin.name,
                    to_warehouse_id=item.to_warehouse_id,
                    to_warehouse_code=destination.code,
                    to_warehouse_name=destination.name,
                    product_id=item.product_id,
                    product_sku=product.sku,
                    product_name=product.name,
                    quantity=item.quantity,
                    received_quantity=item.received_quantity,
                    status=item.status,
                    priority=item.priority,
                    notes=item.notes,
                    dispatch_notes=item.dispatch_notes,
                    receive_notes=item.receive_notes,
                    incident_type=item.incident_type,
                    incident_notes=item.incident_notes,
                    created_at=item.created_at,
                    approved_at=item.approved_at,
                    dispatched_at=item.dispatched_at,
                    received_at=item.received_at,
                )
            )
        return views

    def create_transfer(self, payload: TransferCreate) -> TransferView:
        if payload.from_warehouse_id == payload.to_warehouse_id:
            raise InvalidTransferError()

        with self._transfer_repository.transaction():
            origin = self._warehouse_repository.get_by_id(payload.from_warehouse_id)
            if origin is None:
                raise WarehouseNotFoundError(str(payload.from_warehouse_id))

            destination = self._warehouse_repository.get_by_id(payload.to_warehouse_id)
            if destination is None:
                raise WarehouseNotFoundError(str(payload.to_warehouse_id))

            product = self._product_repository.get_by_id(payload.product_id)
            if product is None:
                raise ProductNotFoundError(str(payload.product_id))

            current_stock = self._inventory_repository.get_stock_level(
                payload.from_warehouse_id,
                payload.product_id,
            )
            current_quantity = current_stock.quantity if current_stock is not None else Decimal("0")
            if current_quantity < payload.quantity:
                raise InsufficientStockError(
                    product_id=str(payload.product_id),
                    warehouse_id=str(payload.from_warehouse_id),
                )

            now = utcnow()
            next_code = f"TR-{len(self._transfer_repository.list_transfers()) + 1:04d}"
            transfer = TransferRecord(
                id=uuid4(),
                code=next_code,
                from_warehouse_id=payload.from_warehouse_id,
                to_warehouse_id=payload.to_warehouse_id,
                product_id=payload.product_id,
                quantity=payload.quantity,
                received_quantity=Decimal("0"),
                status="requested",
                priority=payload.priority,
                notes=payload.notes,
                dispatch_notes=None,
                receive_notes=None,
                incident_type=None,
                incident_notes=None,
                created_at=now,
                approved_at=None,
                dispatched_at=None,
                received_at=None,
            )
            self._transfer_repository.add_transfer(transfer)

            return self._to_view(transfer)

    def update_transfer(self, transfer_id: UUID, payload: TransferUpdate) -> TransferView:
        with self._transfer_repository.transaction():
            transfer = self._require_transfer(transfer_id)
            if transfer.status != "requested":
                raise InvalidTransferStatusError(transfer.status, "requested")
            transfer.quantity = payload.quantity
            transfer.priority = payload.priority
            transfer.notes = payload.notes
            self._transfer_repository.update_transfer(transfer)
            return self._to_view(transfer)

    def cancel_transfer(self, transfer_id: UUID) -> TransferView:
        with self._transfer_repository.transaction():
            transfer = self._require_transfer(transfer_id)
            if transfer.status != "requested":
                raise InvalidTransferStatusError(transfer.status, "requested")
            transfer.status = "cancelled"
            self._transfer_repository.update_transfer(transfer)
            return self._to_view(transfer)

    def approve_transfer(self, transfer_id: UUID) -> TransferView:
        with self._transfer_repository.transaction():
            transfer = self._require_transfer(transfer_id)
            if transfer.status != "requested":
                raise InvalidTransferStatusError(transfer.status, "requested")
            transfer.status = "approved"
            transfer.approved_at = utcnow()
            self._transfer_repository.update_transfer(transfer)
            return self._to_view(transfer)

    def dispatch_transfer(self, transfer_id: UUID, payload: TransferDispatch | None = None) -> TransferView:
        with self._transfer_repository.transaction():
            transfer = self._require_transfer(transfer_id)
            if transfer.status != "approved":
                raise InvalidTransferStatusError(transfer.status, "approved")

            origin = self._require_warehouse(transfer.from_warehouse_id)
            self._require_warehouse(transfer.to_warehouse_id)
            self._require_product(transfer.product_id)

            current_stock = self._inventory_repository.get_stock_level(
                transfer.from_warehouse_id,
                transfer.product_id,
            )
            current_quantity = current_stock.quantity if current_stock is not None else Decimal("0")
            if current_quantity < transfer.quantity:
                raise InsufficientStockError(
                    product_id=str(transfer.product_id),
                    warehouse_id=str(transfer.from_warehouse_id),
                )

            now = utcnow()
            self._register_movement(
                warehouse_id=transfer.from_warehouse_id,
                product_id=transfer.product_id,
                movement_type="out",
                quantity=transfer.quantity,
                reference_id=transfer.code,
                notes=(payload.notes if payload and payload.notes else transfer.notes)
                or f"Despacho a {self._require_warehouse(transfer.to_warehouse_id).code}",
                now=now,
            )
            transfer.status = "dispatched"
            transfer.dispatched_at = now
            transfer.dispatch_notes = payload.notes if payload else transfer.dispatch_notes
            self._transfer_repository.update_transfer(transfer)
            return self._to_view(transfer)

    def receive_transfer(self, transfer_id: UUID, payload: TransferReceive) -> TransferView:
        with self._transfer_repository.transaction():
            transfer = self._require_transfer(transfer_id)
            if transfer.status not in ("dispatched", "partially_received"):
                raise InvalidTransferStatusError(transfer.status, "dispatched")

            self._require_warehouse(transfer.from_warehouse_id)
            self._require_warehouse(transfer.to_warehouse_id)
            self._require_product(transfer.product_id)

            pending_quantity = transfer.quantity - transfer.received_quantity
            if payload.quantity <= 0 or payload.quantity > pending_quantity:
                raise InvalidTransferQuantityError()

            now = utcnow()
            self._register_movement(
                warehouse_id=transfer.to_warehouse_id,
                product_id=transfer.product_id,
                movement_type="in",
                quantity=payload.quantity,
                reference_id=transfer.code,
                notes=payload.notes
                or transfer.notes
                or f"Recepcion desde {self._require_warehouse(transfer.from_warehouse_id).code}",
                now=now,
            )
            transfer.received_quantity += payload.quantity
            transfer.receive_notes = payload.notes
            transfer.incident_type = payload.incident_type
            transfer.incident_notes = payload.incident_notes
            if transfer.received_quantity == transfer.quantity:
                transfer.status = "received"
                transfer.received_at = now
            else:
                transfer.status = "partially_received"
            self._transfer_repository.update_transfer(transfer)
            return self._to_view(transfer)

    def _register_movement(
        self,
        *,
        warehouse_id,
        product_id,
        movement_type: str,
        quantity: Decimal,
        reference_id: str,
        notes: str | None,
        now,
    ) -> None:
        current_stock = self._inventory_repository.get_stock_level(warehouse_id, product_id)
        current_quantity = current_stock.quantity if current_stock is not None else Decimal("0")
        delta = quantity if movement_type == "in" else -quantity
        stock_level = StockLevelRecord(
            id=current_stock.id if current_stock is not None else uuid4(),
            warehouse_id=warehouse_id,
            product_id=product_id,
            quantity=current_quantity + delta,
            min_quantity=current_stock.min_quantity if current_stock is not None else Decimal("0"),
            updated_at=now,
        )
        self._inventory_repository.upsert_stock_level(stock_level)

        movement = InventoryMovementRecord(
            id=uuid4(),
            warehouse_id=warehouse_id,
            product_id=product_id,
            movement_type=movement_type,
            quantity=quantity,
            reference_type="transfer",
            reference_id=reference_id,
            notes=notes,
            created_at=now,
        )
        self._inventory_repository.add_movement(movement)

    def _require_transfer(self, transfer_id: UUID) -> TransferRecord:
        transfer = self._transfer_repository.get_by_id(transfer_id)
        if transfer is None:
            raise TransferNotFoundError(str(transfer_id))
        return transfer

    def _require_warehouse(self, warehouse_id: UUID):
        warehouse = self._warehouse_repository.get_by_id(warehouse_id)
        if warehouse is None:
            raise WarehouseNotFoundError(str(warehouse_id))
        return warehouse

    def _require_product(self, product_id: UUID):
        product = self._product_repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))
        return product

    def _to_view(self, transfer: TransferRecord) -> TransferView:
        origin = self._require_warehouse(transfer.from_warehouse_id)
        destination = self._require_warehouse(transfer.to_warehouse_id)
        product = self._require_product(transfer.product_id)
        return TransferView(
            id=transfer.id,
            code=transfer.code,
            from_warehouse_id=origin.id,
            from_warehouse_code=origin.code,
            from_warehouse_name=origin.name,
            to_warehouse_id=destination.id,
            to_warehouse_code=destination.code,
            to_warehouse_name=destination.name,
            product_id=product.id,
            product_sku=product.sku,
            product_name=product.name,
            quantity=transfer.quantity,
            received_quantity=transfer.received_quantity,
            status=transfer.status,
            priority=transfer.priority,
            notes=transfer.notes,
            dispatch_notes=transfer.dispatch_notes,
            receive_notes=transfer.receive_notes,
            incident_type=transfer.incident_type,
            incident_notes=transfer.incident_notes,
            created_at=transfer.created_at,
            approved_at=transfer.approved_at,
            dispatched_at=transfer.dispatched_at,
            received_at=transfer.received_at,
        )
