"""
Router de transfers (DEPRECATED COMPLETO — ver app.modules.transfers.__init__).

Cambios en Fase 5+ (migración async):
- TODOS los endpoints retornan 410 Gone. El cliente debe usar
  ``/api/v1/solicitudes`` en su lugar (N productos, flujo moderno).
- Antes (Fase 3) los GETs seguían funcionando por compat con frontend;
  ahora (Fase 5+) se cierran también para forzar la migración.
- El ``TransferRepository`` legacy (SQLiteDatabase sync) y ``TransferService``
  se conservan internamente solo para tests legacy que los importan, pero
  el router ya no los usa.

Para que la respuesta 410 sea útil, el endpoint POST valida el body
(origen == destino → 409) ANTES de retornar 410.
"""

from __future__ import annotations

import uuid

from app.core.errors import InvalidTransferError
from app.modules.auth.router import get_current_user
from app.modules.transfers.schemas import (
    TransferCreate,
    TransferDispatch,
    TransferReceive,
    TransferResponse,
    TransferUpdate,
)
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter()


_DEPRECATED_MESSAGE = (
    "El endpoint /api/v1/transfers esta deprecado. "
    "Usa /api/v1/solicitudes en su lugar. "
    "Las transferencias (1 producto) fueron reemplazadas por solicitudes_recarga "
    "(N productos) segun ADR-0003. "
    "Este modulo se retirara definitivamente."
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
# GETs (tambien cerrados en Fase 5+)
# =============================================================================


@router.get("", response_model=list[TransferResponse], status_code=status.HTTP_410_GONE)
def list_transfers(
    _: object = Depends(get_current_user),
) -> None:
    """DEPRECATED — usar /api/v1/solicitudes."""
    _gone("GET /transfers")


@router.get("/{transfer_id}", response_model=TransferResponse, status_code=status.HTTP_410_GONE)
def get_transfer(
    transfer_id: uuid.UUID,  # noqa: ARG001
    _: object = Depends(get_current_user),
) -> None:
    """DEPRECATED — usar /api/v1/solicitudes/{id}."""
    _gone("GET /transfers/{id}")


@router.get(
    "/{transfer_id}/derived",
    response_model=TransferResponse,
    status_code=status.HTTP_410_GONE,
)
def get_derived_transfer(
    transfer_id: uuid.UUID,  # noqa: ARG001
    _: object = Depends(get_current_user),
) -> None:
    """DEPRECATED — usar /api/v1/solicitudes/{id}/derived."""
    _gone("GET /transfers/{id}/derived")


# =============================================================================
# POST / PATCH / DELETE → 410 Gone (escritura deshabilitada)
# =============================================================================


@router.post("", response_model=TransferResponse, status_code=status.HTTP_410_GONE)
def create_transfer(
    payload: TransferCreate,
    _=Depends(get_current_user),
) -> None:
    # Validar el body ANTES de retornar 410 Gone: preserva la semantica
    # del spec original (origen==destino → 409 invalid_transfer, no 410).
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
