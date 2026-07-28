"""Router FastAPI para recepciones (FIX FASE POST-E2E).

Endpoints:
- ``GET    /api/v1/receipts``                  — listar
- ``POST   /api/v1/receipts``                  — crear (estado pending, NO toca stock)
- ``GET    /api/v1/receipts/{id}``             — obtener
- ``POST   /api/v1/receipts/{id}/confirm``     — confirmar (genera movimientos in)
- ``POST   /api/v1/receipts/{id}/cancel``      — cancelar (solo pending)

Roles:
- admin, supervisor, destination_operator: crear, listar, confirmar, cancelar.
"""
from __future__ import annotations

import uuid

from app.core.audit import record_audit
from app.db.session import get_session
from app.modules.auth.dependencies import require_roles
from app.modules.auth.router import get_current_user
from app.modules.receipts.schemas import (
    ReceiptCreate,
    ReceiptLineResponse,
    ReceiptResponse,
)
from app.modules.receipts.service import ReceiptService
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def _to_line_response(line) -> ReceiptLineResponse:
    """Convierte una ReceiptLine ORM a su response enriched."""
    return ReceiptLineResponse(
        id=line.id,
        id_receipt=line.id_receipt,
        id_producto=line.id_producto,
        cantidad=line.cantidad,
        precio_unitario=line.precio_unitario,
        movement_id=line.movement_id,
    )


def _to_receipt_response(r) -> ReceiptResponse:
    """Convierte un Receipt ORM a su response enriched."""
    # Enriquecer lineas con SKU + nombre
    lineas = []
    total_cantidad = 0
    total_monto = 0
    for line in (r.lineas or []):
        lineas.append(_to_line_response(line))
        total_cantidad += float(line.cantidad or 0)
        total_monto += float(line.cantidad or 0) * float(line.precio_unitario or 0)

    return ReceiptResponse(
        id=r.id,
        codigo=r.codigo,
        id_bodega_destino=r.id_bodega_destino,
        id_proveedor=r.id_proveedor,
        id_orden_compra=r.id_orden_compra,
        numero_documento=r.numero_documento,
        estado=r.estado,
        notas=r.notas,
        created_by=r.created_by,
        created_at=r.created_at,
        confirmed_at=r.confirmed_at,
        confirmed_by=r.confirmed_by,
        bodega_codigo=r.bodega_destino.code if r.bodega_destino else None,
        bodega_nombre=r.bodega_destino.name if r.bodega_destino else None,
        proveedor_nombre=r.proveedor.nombre if r.proveedor else None,
        orden_compra_codigo=r.orden_compra.codigo if r.orden_compra else None,
        total_cantidad=total_cantidad,
        total_monto=total_monto,
        lineas=lineas,
    )


def get_receipt_service(
    session: AsyncSession = Depends(get_session),
) -> ReceiptService:
    return ReceiptService(session=session)


@router.get("", response_model=list[ReceiptResponse])
async def list_receipts(
    estado: str | None = Query(
        default=None,
        description="Filtrar por estado: pending | confirmed | cancelled",
    ),
    id_bodega_destino: uuid.UUID | None = Query(default=None),
    id_proveedor: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user=Depends(get_current_user),
    service: ReceiptService = Depends(get_receipt_service),
) -> list[ReceiptResponse]:
    receipts = await service.list_receipts(
        estado=estado,
        id_bodega_destino=id_bodega_destino,
        id_proveedor=id_proveedor,
        limit=limit,
        offset=offset,
    )
    return [_to_receipt_response(r) for r in receipts]


@router.post("", response_model=ReceiptResponse, status_code=status.HTTP_201_CREATED)
async def create_receipt(
    payload: ReceiptCreate,
    user=Depends(require_roles("admin", "supervisor", "destination_operator")),
    service: ReceiptService = Depends(get_receipt_service),
    session: AsyncSession = Depends(get_session),
) -> ReceiptResponse:
    receipt = await service.create_receipt(
        id_bodega_destino=payload.id_bodega_destino,
        id_proveedor=payload.id_proveedor,
        id_orden_compra=payload.id_orden_compra,
        numero_documento=payload.numero_documento,
        notas=payload.notas,
        lineas=[line.model_dump() for line in payload.lineas],
        user_id=user.id,
    )
    await record_audit(
        session=session,
        user_id=user.id,
        action="receipt.create",
        entity_type="receipt",
        entity_id=str(receipt.id),
        detail=f"Recepcion {receipt.codigo} creada (pending, {len(payload.lineas)} lineas)",
    )
    return _to_receipt_response(receipt)


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: uuid.UUID,
    _user=Depends(get_current_user),
    service: ReceiptService = Depends(get_receipt_service),
) -> ReceiptResponse:
    receipt = await service.get_receipt(receipt_id)
    if receipt is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail={"code": "receipt_not_found", "message": f"Recepcion {receipt_id} no existe"},
        )
    return _to_receipt_response(receipt)


@router.post("/{receipt_id}/confirm", response_model=ReceiptResponse)
async def confirm_receipt(
    receipt_id: uuid.UUID,
    user=Depends(require_roles("admin", "supervisor", "destination_operator")),
    service: ReceiptService = Depends(get_receipt_service),
    session: AsyncSession = Depends(get_session),
) -> ReceiptResponse:
    try:
        receipt = await service.confirm_receipt(receipt_id, user_id=user.id)
    except ValueError as e:
        from fastapi import HTTPException
        msg = str(e)
        if "no existe" in msg:
            raise HTTPException(
                status_code=404,
                detail={"code": "receipt_not_found", "message": msg},
            )
        raise HTTPException(
            status_code=409,
            detail={"code": "receipt_invalid_state", "message": msg},
        )

    await record_audit(
        session=session,
        user_id=user.id,
        action="receipt.confirm",
        entity_type="receipt",
        entity_id=str(receipt.id),
        detail=f"Recepcion {receipt.codigo} confirmada: {len(receipt.lineas)} movimientos in",
    )
    return _to_receipt_response(receipt)


@router.post("/{receipt_id}/cancel", response_model=ReceiptResponse)
async def cancel_receipt(
    receipt_id: uuid.UUID,
    motivo: str | None = Query(default=None, max_length=200),
    user=Depends(require_roles("admin", "supervisor")),
    service: ReceiptService = Depends(get_receipt_service),
    session: AsyncSession = Depends(get_session),
) -> ReceiptResponse:
    try:
        receipt = await service.cancel_receipt(receipt_id, user_id=user.id, motivo=motivo)
    except ValueError as e:
        from fastapi import HTTPException
        msg = str(e)
        if "no existe" in msg:
            raise HTTPException(
                status_code=404,
                detail={"code": "receipt_not_found", "message": msg},
            )
        raise HTTPException(
            status_code=409,
            detail={"code": "receipt_invalid_state", "message": msg},
        )

    await record_audit(
        session=session,
        user_id=user.id,
        action="receipt.cancel",
        entity_type="receipt",
        entity_id=str(receipt.id),
        detail=f"Recepcion {receipt.codigo} cancelada (motivo: {motivo or 'N/A'})",
    )
    return _to_receipt_response(receipt)
