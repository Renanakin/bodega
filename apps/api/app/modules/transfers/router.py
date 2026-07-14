from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.db.session import SQLiteDatabase, get_database
from app.modules.auth.dependencies import require_roles
from app.modules.auth.repository import AuthRepository
from app.modules.auth.router import get_current_user
from app.modules.auth.service import AuthService
from app.modules.inventory.repository import InventoryRepository
from app.modules.products.repository import ProductRepository
from app.modules.transfers.repository import TransferRepository
from app.modules.transfers.schemas import (
    TransferCreate,
    TransferDispatch,
    TransferReceive,
    TransferResponse,
    TransferUpdate,
)
from app.modules.transfers.service import TransferService
from app.modules.warehouses.repository import WarehouseRepository

router = APIRouter()


def get_transfer_service(db: SQLiteDatabase = Depends(get_database)) -> TransferService:
    return TransferService(
        transfer_repository=TransferRepository(db),
        inventory_repository=InventoryRepository(db),
        warehouse_repository=WarehouseRepository(db),
        product_repository=ProductRepository(db),
    )


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


@router.get("", response_model=list[TransferResponse])
def list_transfers(
    _: object = Depends(get_current_user),
    service: TransferService = Depends(get_transfer_service),
) -> list[TransferResponse]:
    return service.list_transfers()


@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
def create_transfer(
    payload: TransferCreate,
    user=Depends(require_roles("admin", "supervisor", "origin_operator")),
    service: TransferService = Depends(get_transfer_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> TransferResponse:
    transfer = service.create_transfer(payload)
    auth_service.audit(
        user_id=user.id,
        action="transfer.request",
        entity_type="transfer",
        entity_id=str(transfer.id),
        detail=f"Transferencia {transfer.code} solicitada",
    )
    return transfer


@router.patch("/{transfer_id}", response_model=TransferResponse)
def update_transfer(
    transfer_id: UUID,
    payload: TransferUpdate,
    user=Depends(require_roles("admin", "supervisor", "origin_operator")),
    service: TransferService = Depends(get_transfer_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> TransferResponse:
    transfer = service.update_transfer(transfer_id, payload)
    auth_service.audit(
        user_id=user.id,
        action="transfer.update",
        entity_type="transfer",
        entity_id=str(transfer.id),
        detail=f"Transferencia {transfer.code} editada",
    )
    return transfer


@router.post("/{transfer_id}/cancel", response_model=TransferResponse)
def cancel_transfer(
    transfer_id: UUID,
    user=Depends(require_roles("admin", "supervisor", "origin_operator")),
    service: TransferService = Depends(get_transfer_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> TransferResponse:
    transfer = service.cancel_transfer(transfer_id)
    auth_service.audit(
        user_id=user.id,
        action="transfer.cancel",
        entity_type="transfer",
        entity_id=str(transfer.id),
        detail=f"Transferencia {transfer.code} cancelada",
    )
    return transfer


@router.post("/{transfer_id}/approve", response_model=TransferResponse)
def approve_transfer(
    transfer_id: UUID,
    user=Depends(require_roles("admin", "supervisor")),
    service: TransferService = Depends(get_transfer_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> TransferResponse:
    transfer = service.approve_transfer(transfer_id)
    auth_service.audit(
        user_id=user.id,
        action="transfer.approve",
        entity_type="transfer",
        entity_id=str(transfer.id),
        detail=f"Transferencia {transfer.code} aprobada",
    )
    return transfer


@router.post("/{transfer_id}/dispatch", response_model=TransferResponse)
def dispatch_transfer(
    transfer_id: UUID,
    payload: TransferDispatch,
    user=Depends(require_roles("admin", "supervisor", "origin_operator")),
    service: TransferService = Depends(get_transfer_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> TransferResponse:
    transfer = service.dispatch_transfer(transfer_id, payload)
    auth_service.audit(
        user_id=user.id,
        action="transfer.dispatch",
        entity_type="transfer",
        entity_id=str(transfer.id),
        detail=f"Transferencia {transfer.code} despachada",
    )
    return transfer


@router.post("/{transfer_id}/receive", response_model=TransferResponse)
def receive_transfer(
    transfer_id: UUID,
    payload: TransferReceive,
    user=Depends(require_roles("admin", "supervisor", "destination_operator")),
    service: TransferService = Depends(get_transfer_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> TransferResponse:
    transfer = service.receive_transfer(transfer_id, payload)
    auth_service.audit(
        user_id=user.id,
        action="transfer.receive",
        entity_type="transfer",
        entity_id=str(transfer.id),
        detail=f"Transferencia {transfer.code} recibida",
    )
    return transfer
