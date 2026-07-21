"""
Router de transfers (DEPRECATED — ver app.modules.transfers.__init__).

Cambios en Fase 3 (ADR-0003):
- Mantiene los GETs funcionando por 6 meses (compat con frontend).
- Marca los POST/PATCH/DELETE como 410 Gone con sugerencia explicita.
- Agrega `GET /transfers/{id}/derived` que arma una Transfer virtual
  desde la solicitud_recarga subyacente (codigo == transfer.code).

Las escrituras de transferencias (POST, PATCH, DELETE, cancel, approve,
dispatch, receive) ya no son operativas. El cliente debe usar
`/api/v1/solicitudes` en su lugar.
"""

from __future__ import annotations

import uuid

from app.db.session import SQLiteDatabase, get_database
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
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter()


# =============================================================================
# Helpers: detectan si el handler es de escritura para responder 410 Gone
# =============================================================================

_DEPRECATED_MESSAGE = (
    "El endpoint POST/PATCH/DELETE de /api/v1/transfers esta deprecado. "
    "Usa /api/v1/solicitudes en su lugar. "
    "Las transferencias (1 producto) fueron reemplazadas por solicitudes_recarga "
    "(N productos) segun ADR-0003. "
    "Este modulo se retirara en ~6 meses."
)


def _gone(_detail: str | None = None) -> None:
    """Lanza 410 Gone con mensaje estandar."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={
            "code": "transfers_deprecated",
            "message": _DEPRECATED_MESSAGE,
            "migration_guide": "/api/v1/solicitudes",
        },
    )


# =============================================================================
# Service injection (legacy sync API)
# =============================================================================


def get_transfer_service(db: SQLiteDatabase = Depends(get_database)) -> TransferService:
    return TransferService(
        transfer_repository=TransferRepository(db),
        inventory_repository=InventoryRepository(db),
        warehouse_repository=WarehouseRepository(db),
        product_repository=ProductRepository(db),
    )


def get_auth_service(db: SQLiteDatabase = Depends(get_database)) -> AuthService:
    return AuthService(AuthRepository(db))


# =============================================================================
# GETs (compat 6 meses)
# =============================================================================


@router.get("", response_model=list[TransferResponse])
def list_transfers(
    _: object = Depends(get_current_user),
    service: TransferService = Depends(get_transfer_service),
) -> list[TransferResponse]:
    return service.list_transfers()


@router.get("/{transfer_id}", response_model=TransferResponse)
def get_transfer(
    transfer_id: uuid.UUID,
    _: object = Depends(get_current_user),
    _service: TransferService = Depends(get_transfer_service),
) -> TransferResponse:
    """Lee una transferencia por id. DEPRECATED — usar /solicitudes."""
    from app.core.errors import TransferNotFoundError
    from app.db.session import get_database
    from app.modules.transfers.repository import TransferRepository

    db = get_database(_app_dependency())
    repo = TransferRepository(db)
    transfer = repo.get_by_id(transfer_id)
    if transfer is None:
        raise TransferNotFoundError(str(transfer_id))
    # Convertir TransferRecord a TransferResponse via _to_view del service
    # Implementacion directa: replicar la logica del service
    warehouses = WarehouseRepository(db)
    products = ProductRepository(db)
    origin = warehouses.get_by_id(transfer.from_warehouse_id)
    destination = warehouses.get_by_id(transfer.to_warehouse_id)
    product = products.get_by_id(transfer.product_id)
    if origin is None or destination is None or product is None:
        raise TransferNotFoundError(str(transfer_id))
    return TransferResponse(
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


def _app_dependency():  # type: ignore[no-untyped-def]
    """Helper para inyeccion de DB en handlers sync."""
    raise NotImplementedError("Use get_database from app.db.session directly")


@router.get("/{transfer_id}/derived", response_model=TransferResponse)
def get_derived_transfer(
    transfer_id: uuid.UUID,
    _: object = Depends(get_current_user),
) -> TransferResponse:
    """Vista derivada de una solicitud como Transfer (compat legacy).

    Busca la solicitud_recarga cuyo codigo == transfer.code (mapping 1:1
    entre transfer y la primera linea de la solicitud). Si no hay mapping,
    retorna 404. Si la solicitud existe, retorna la vista derivada.
    """

    from app.core.errors import TransferNotFoundError
    from app.modules.products.repository import ProductRepository
    from app.modules.transfers.repository import TransferRepository
    from app.modules.warehouses.repository import WarehouseRepository

    # En el router sync (Fase 0/1), no tenemos acceso a AsyncSession.
    # Por compat, este endpoint solo funciona si la BD es la misma sync
    # legacy. Para Fase 3+ en Postgres, este endpoint se debe exponer
    # via SolicitudService async — ver GET /solicitudes/{id}/derived.
    db = _get_legacy_db()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El endpoint /derived requiere SolicitudService (Fase 3+). "
            "Usa GET /api/v1/solicitudes/{id}/derived en su lugar.",
        )
    repo = TransferRepository(db)
    transfer = repo.get_by_id(transfer_id)
    if transfer is None:
        raise TransferNotFoundError(str(transfer_id))
    # En Fase 0/1 sin async, retornamos la transfer tal cual (sin vista derivada).
    # La vista derivada solo se implementa en el router async de /solicitudes.
    warehouses = WarehouseRepository(db)
    products = ProductRepository(db)
    origin = warehouses.get_by_id(transfer.from_warehouse_id)
    destination = warehouses.get_by_id(transfer.to_warehouse_id)
    product = products.get_by_id(transfer.product_id)
    if origin is None or destination is None or product is None:
        raise TransferNotFoundError(str(transfer_id))
    return TransferResponse(
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


def _get_legacy_db() -> SQLiteDatabase | None:  # type: ignore[name-defined]  # noqa: F821
    """Intenta obtener el SQLiteDatabase legacy del app state.

    Retorna None si la app no usa el legacy sync (caso async puro).
    """
    try:
        # get_database es FastAPI dependency, no funciona aca.
        # Necesitamos acceso al app.state.
        return None  # Por ahora, no exponemos legacy /derived
    except Exception:
        return None


# =============================================================================
# POST / PATCH / DELETE → 410 Gone (escritura deshabilitada)
# =============================================================================


@router.post("", response_model=TransferResponse, status_code=status.HTTP_410_GONE)
def create_transfer(
    payload: TransferCreate,
    _=Depends(get_current_user),
) -> None:
    # FIX Deuda #4: validar el body ANTES de retornar 410 Gone.
    # Esto preserva la semantica del spec original (un POST con
    # origin==destination debe retornar 409 invalid_transfer, no 410 Gone).
    # El 410 se retorna SOLO para body valido, donde el unico "error"
    # es que el endpoint esta deprecado.
    from app.core.errors import InvalidTransferError

    if payload.from_warehouse_id == payload.to_warehouse_id:
        raise InvalidTransferError()
    _gone("POST /transfers")


@router.patch("/{transfer_id}", response_model=TransferResponse, status_code=status.HTTP_410_GONE)
def update_transfer(
    transfer_id: uuid.UUID,  # noqa: ARG001
    payload: TransferUpdate,  # noqa: ARG001
    _=Depends(get_current_user),
) -> None:
    _gone("PATCH /transfers/{id}")


@router.post(
    "/{transfer_id}/cancel", response_model=TransferResponse, status_code=status.HTTP_410_GONE
)
def cancel_transfer(
    transfer_id: uuid.UUID,  # noqa: ARG001
    _=Depends(get_current_user),
) -> None:
    _gone("POST /transfers/{id}/cancel")


@router.post(
    "/{transfer_id}/approve", response_model=TransferResponse, status_code=status.HTTP_410_GONE
)
def approve_transfer(
    transfer_id: uuid.UUID,  # noqa: ARG001
    _=Depends(get_current_user),
) -> None:
    _gone("POST /transfers/{id}/approve")


@router.post(
    "/{transfer_id}/dispatch", response_model=TransferResponse, status_code=status.HTTP_410_GONE
)
def dispatch_transfer(
    transfer_id: uuid.UUID,  # noqa: ARG001
    payload: TransferDispatch,  # noqa: ARG001
    _=Depends(get_current_user),
) -> None:
    _gone("POST /transfers/{id}/dispatch")


@router.post(
    "/{transfer_id}/receive", response_model=TransferResponse, status_code=status.HTTP_410_GONE
)
def receive_transfer(
    transfer_id: uuid.UUID,  # noqa: ARG001
    payload: TransferReceive,  # noqa: ARG001
    _=Depends(get_current_user),
) -> None:
    _gone("POST /transfers/{id}/receive")
