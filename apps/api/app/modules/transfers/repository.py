from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.db.session import SQLiteDatabase, TransferRecord


def _to_transfer(row) -> TransferRecord:
    return TransferRecord(
        id=UUID(row["id"]),
        code=row["code"],
        from_warehouse_id=UUID(row["from_warehouse_id"]),
        to_warehouse_id=UUID(row["to_warehouse_id"]),
        product_id=UUID(row["product_id"]),
        quantity=Decimal(str(row["quantity"])),
        received_quantity=Decimal(str(row["received_quantity"])),
        status=row["status"],
        priority=row["priority"],
        notes=row["notes"],
        dispatch_notes=row["dispatch_notes"],
        receive_notes=row["receive_notes"],
        incident_type=row["incident_type"],
        incident_notes=row["incident_notes"],
        created_at=datetime.fromisoformat(row["created_at"]),
        approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
        dispatched_at=datetime.fromisoformat(row["dispatched_at"])
        if row["dispatched_at"]
        else None,
        received_at=datetime.fromisoformat(row["received_at"]) if row["received_at"] else None,
    )


class TransferRepository:
    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db

    def transaction(self) -> AbstractContextManager[SQLiteDatabase]:
        return self._db.transaction()

    def add_transfer(self, transfer: TransferRecord) -> TransferRecord:
        self._db.execute(
            """
            INSERT INTO transfers (
                id, code, from_warehouse_id, to_warehouse_id, product_id, quantity,
                received_quantity, status, priority, notes, dispatch_notes, receive_notes,
                incident_type, incident_notes, created_at, approved_at, dispatched_at, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(transfer.id),
                transfer.code,
                str(transfer.from_warehouse_id),
                str(transfer.to_warehouse_id),
                str(transfer.product_id),
                str(transfer.quantity),
                str(transfer.received_quantity),
                transfer.status,
                transfer.priority,
                transfer.notes,
                transfer.dispatch_notes,
                transfer.receive_notes,
                transfer.incident_type,
                transfer.incident_notes,
                transfer.created_at.isoformat(),
                transfer.approved_at.isoformat() if transfer.approved_at else None,
                transfer.dispatched_at.isoformat() if transfer.dispatched_at else None,
                transfer.received_at.isoformat() if transfer.received_at else None,
            ),
        )
        return transfer

    def get_by_id(self, transfer_id: UUID) -> TransferRecord | None:
        row = self._db.query_one("SELECT * FROM transfers WHERE id = ?", (str(transfer_id),))
        return _to_transfer(row) if row is not None else None

    def update_transfer(self, transfer: TransferRecord) -> TransferRecord:
        self._db.execute(
            """
            UPDATE transfers
            SET quantity = ?, received_quantity = ?, status = ?, priority = ?, notes = ?,
                dispatch_notes = ?, receive_notes = ?, incident_type = ?, incident_notes = ?,
                approved_at = ?, dispatched_at = ?, received_at = ?
            WHERE id = ?
            """,
            (
                str(transfer.quantity),
                str(transfer.received_quantity),
                transfer.status,
                transfer.priority,
                transfer.notes,
                transfer.dispatch_notes,
                transfer.receive_notes,
                transfer.incident_type,
                transfer.incident_notes,
                transfer.approved_at.isoformat() if transfer.approved_at else None,
                transfer.dispatched_at.isoformat() if transfer.dispatched_at else None,
                transfer.received_at.isoformat() if transfer.received_at else None,
                str(transfer.id),
            ),
        )
        return transfer

    def list_transfers(self) -> list[TransferRecord]:
        rows = self._db.query_all("SELECT * FROM transfers ORDER BY created_at DESC")
        return [_to_transfer(row) for row in rows]
