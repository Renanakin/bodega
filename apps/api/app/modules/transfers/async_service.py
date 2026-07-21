"""
TransferService async (Fase 3): usa MovementEngine.

Versión async del TransferService legacy. Las operaciones de stock
(despacho, recepción) pasan por MovementEngine.
La versión sync (service.py) se mantiene por compat hasta Fase 5
cuando se introduzca SolicitudService que reemplazará Transfer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.errors import (
    InvalidTransferQuantityError,
    InvalidTransferStatusError,
    ProductNotFoundError,
    TransferNotFoundError,
    WarehouseNotFoundError,
)
from app.core.logging import get_logger
from app.db.models.inventory import MovementType
from app.db.models.products import Product
from app.db.models.transfers import Transfer, TransferStatus
from app.db.models.warehouses import Warehouse
from app.shared.movement_engine import MovementEngine, MovementRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.transfers.schemas import TransferCreate


log = get_logger(__name__)


@dataclass(slots=True)
class TransferView:
    id: uuid.UUID
    code: str
    from_warehouse_id: uuid.UUID
    from_warehouse_code: str
    to_warehouse_id: uuid.UUID
    to_warehouse_code: str
    product_id: uuid.UUID
    product_sku: str
    product_name: str
    quantity: Decimal
    received_quantity: Decimal
    status: TransferStatus
    created_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    received_at: datetime | None


class TransferServiceAsync:
    """Versión async del TransferService (Fase 3+).

    Reglas:
    - R4: el service NO llama a db.execute; usa repos via SQLAlchemy ORM.
    - R6: todo cambio de stock pasa por MovementEngine.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_transfer(
        self, payload: TransferCreate, user_id: uuid.UUID | None = None
    ) -> Transfer:
        """Crea una solicitud de transferencia (estado: requested)."""
        if payload.from_warehouse_id == payload.to_warehouse_id:
            from app.core.errors import InvalidTransferError

            raise InvalidTransferError()

        # Validar warehouse y product existen
        from_wh = await self._session.get(Warehouse, payload.from_warehouse_id)
        if from_wh is None:
            raise WarehouseNotFoundError(str(payload.from_warehouse_id))
        to_wh = await self._session.get(Warehouse, payload.to_warehouse_id)
        if to_wh is None:
            raise WarehouseNotFoundError(str(payload.to_warehouse_id))
        product = await self._session.get(Product, payload.product_id)
        if product is None:
            raise ProductNotFoundError(str(payload.product_id))

        # Generar código único (TR-NNNN)
        count_stmt = select(Transfer)
        result = await self._session.execute(count_stmt)
        next_code = f"TR-{len(result.scalars().all()) + 1:04d}"

        transfer = Transfer(
            id=uuid.uuid4(),
            code=next_code,
            from_warehouse_id=payload.from_warehouse_id,
            to_warehouse_id=payload.to_warehouse_id,
            product_id=payload.product_id,
            quantity=payload.quantity,
            received_quantity=Decimal("0"),
            status=TransferStatus.REQUESTED,
            priority=payload.priority,
            notes=payload.notes,
        )
        self._session.add(transfer)
        await self._session.commit()
        await self._session.refresh(transfer)

        log.info(
            "transfer.requested",
            transfer_id=str(transfer.id),
            code=transfer.code,
            from_warehouse_code=from_wh.code,
            to_warehouse_code=to_wh.code,
            product_sku=product.sku,
            quantity=str(transfer.quantity),
            user_id=str(user_id) if user_id else None,
        )
        return transfer

    async def dispatch_transfer(self, transfer_id: uuid.UUID, notes: str | None = None) -> Transfer:
        """Despacha la transferencia (status: approved → dispatched).

        Usa MovementEngine para descontar stock de la bodega origen.
        """
        transfer = await self._require_transfer(transfer_id)
        if transfer.status != TransferStatus.APPROVED:
            raise InvalidTransferStatusError(
                current_status=transfer.status.value,
                expected_status=TransferStatus.APPROVED.value,
            )

        engine = MovementEngine(self._session)
        result = await engine.apply(
            MovementRequest(
                warehouse_id=transfer.from_warehouse_id,
                product_id=transfer.product_id,
                movement_type=MovementType.OUT,
                quantity=transfer.quantity,
                reference_type="transfer",
                reference_id=transfer.code,
                notes=notes or transfer.notes or f"Despacho a {transfer.to_warehouse_id}",
            )
        )

        transfer.status = TransferStatus.DISPATCHED
        transfer.dispatched_at = _utcnow()
        if notes:
            transfer.dispatch_notes = notes
        await self._session.commit()
        await self._session.refresh(transfer)

        log.info(
            "transfer.dispatched",
            transfer_id=str(transfer.id),
            code=transfer.code,
            previous_quantity=str(result.previous_quantity),
            new_quantity=str(result.new_quantity),
        )
        return transfer

    async def receive_transfer(
        self,
        transfer_id: uuid.UUID,
        received_qty: Decimal,
        notes: str | None = None,
    ) -> Transfer:
        """Recibe la transferencia (status: dispatched → received)."""
        transfer = await self._require_transfer(transfer_id)
        if transfer.status not in (TransferStatus.DISPATCHED, TransferStatus.PARTIALLY_RECEIVED):
            raise InvalidTransferStatusError(
                current_status=transfer.status.value,
                expected_status=TransferStatus.DISPATCHED.value,
            )

        pending = transfer.quantity - transfer.received_quantity
        if received_qty <= 0 or received_qty > pending:
            raise InvalidTransferQuantityError()

        engine = MovementEngine(self._session)
        await engine.apply(
            MovementRequest(
                warehouse_id=transfer.to_warehouse_id,
                product_id=transfer.product_id,
                movement_type=MovementType.IN,
                quantity=received_qty,
                reference_type="transfer",
                reference_id=transfer.code,
                notes=notes or transfer.notes or f"Recepción desde {transfer.from_warehouse_id}",
            )
        )

        transfer.received_quantity = transfer.received_quantity + received_qty
        if transfer.received_quantity == transfer.quantity:
            transfer.status = TransferStatus.RECEIVED
            transfer.received_at = _utcnow()
        else:
            transfer.status = TransferStatus.PARTIALLY_RECEIVED
        if notes:
            transfer.receive_notes = notes
        await self._session.commit()
        await self._session.refresh(transfer)
        return transfer

    async def approve_transfer(self, transfer_id: uuid.UUID) -> Transfer:
        """Aprueba una transferencia (status: requested → approved)."""
        transfer = await self._require_transfer(transfer_id)
        if transfer.status != TransferStatus.REQUESTED:
            raise InvalidTransferStatusError(
                current_status=transfer.status.value,
                expected_status=TransferStatus.REQUESTED.value,
            )
        transfer.status = TransferStatus.APPROVED
        transfer.approved_at = _utcnow()
        await self._session.commit()
        await self._session.refresh(transfer)
        return transfer

    async def cancel_transfer(self, transfer_id: uuid.UUID) -> Transfer:
        """Cancela una transferencia (status: requested → cancelled)."""
        transfer = await self._require_transfer(transfer_id)
        if transfer.status != TransferStatus.REQUESTED:
            raise InvalidTransferStatusError(
                current_status=transfer.status.value,
                expected_status=TransferStatus.REQUESTED.value,
            )
        transfer.status = TransferStatus.CANCELLED
        await self._session.commit()
        await self._session.refresh(transfer)
        return transfer

    async def _require_transfer(self, transfer_id: uuid.UUID) -> Transfer:
        transfer = await self._session.get(Transfer, transfer_id)
        if transfer is None:
            raise TransferNotFoundError(str(transfer_id))
        return transfer


def _utcnow() -> datetime:
    from datetime import UTC, datetime

    return datetime.now(UTC)
