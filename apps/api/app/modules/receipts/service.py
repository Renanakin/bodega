"""Service: receipts (Recepciones de mercaderia, FIX FASE POST-E2E).

Implementa la logica de negocio del modulo de Recepciones documentado en
el manual de usuario seccion 8:

1. Crear recepcion (estado pending). NO toca stock.
2. Confirmar recepcion. Genera movimientos ``in`` por cada linea.
   Si la recepcion tiene una OC asociada, la OC pasa a ``received``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.db.models.inventory import MovementType
from app.db.models.ordenes_compra import OrdenCompra, OrdenCompraEstado
from app.db.models.products import Product
from app.db.models.receipts import Receipt, ReceiptLine
from app.db.models.warehouses import Warehouse
from app.shared.movement_engine import MovementEngine, MovementRequest

log = get_logger(__name__)


class ReceiptService:
    """Service de Recepciones."""

    def __init__(
        self,
        session: AsyncSession,
        movement: MovementEngine | None = None,
    ) -> None:
        self._session = session
        self._movement = movement or MovementEngine(session)

    async def list_receipts(
        self,
        *,
        estado: str | None = None,
        id_bodega_destino: uuid.UUID | None = None,
        id_proveedor: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        """Lista recepciones con filtros."""
        stmt = select(Receipt).options(
            selectinload(Receipt.lineas),
            selectinload(Receipt.bodega_destino),
            selectinload(Receipt.proveedor),
            selectinload(Receipt.orden_compra),
        )
        if estado:
            stmt = stmt.where(Receipt.estado == estado)
        if id_bodega_destino:
            stmt = stmt.where(Receipt.id_bodega_destino == id_bodega_destino)
        if id_proveedor:
            stmt = stmt.where(Receipt.id_proveedor == id_proveedor)
        stmt = stmt.order_by(Receipt.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_receipt(self, receipt_id: uuid.UUID) -> Receipt | None:
        stmt = select(Receipt).where(Receipt.id == receipt_id).options(
            selectinload(Receipt.lineas),
            selectinload(Receipt.bodega_destino),
            selectinload(Receipt.proveedor),
            selectinload(Receipt.orden_compra),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_receipt(
        self,
        *,
        id_bodega_destino: uuid.UUID,
        id_proveedor: uuid.UUID | None,
        id_orden_compra: uuid.UUID | None,
        numero_documento: str | None,
        notas: str | None,
        lineas: list[dict],
        user_id: uuid.UUID,
    ) -> Receipt:
        """Crea una recepcion en estado ``pending``. NO toca stock todavia.

        ``lineas`` es una lista de dicts con: id_producto, cantidad,
        precio_unitario.
        """
        # Validar bodega destino existe
        wh = await self._session.get(Warehouse, id_bodega_destino)
        if wh is None:
            raise ValueError(f"Bodega destino {id_bodega_destino} no existe")
        if not wh.is_active:
            raise ValueError(f"Bodega destino {wh.code} no esta activa")

        # Validar productos
        product_ids = [linea["id_producto"] for linea in lineas]
        stmt = select(Product).where(Product.id.in_(product_ids))
        result = await self._session.execute(stmt)
        productos = {p.id: p for p in result.scalars().all()}
        for linea in lineas:
            if linea["id_producto"] not in productos:
                raise ValueError(f"Producto {linea['id_producto']} no existe")

        # Generar codigo unico: REC-YYYYMMDD-NNNN
        codigo = await self._next_codigo()

        receipt = Receipt(
            id=uuid.uuid4(),
            codigo=codigo,
            id_bodega_destino=id_bodega_destino,
            id_proveedor=id_proveedor,
            id_orden_compra=id_orden_compra,
            numero_documento=numero_documento,
            estado="pending",
            notas=notas,
            created_by=user_id,
            # created_at se setea via server_default en la BD.
        )
        self._session.add(receipt)
        await self._session.flush()

        for linea in lineas:
            rl = ReceiptLine(
                id=uuid.uuid4(),
                id_receipt=receipt.id,
                id_producto=linea["id_producto"],
                cantidad=Decimal(str(linea["cantidad"])),
                precio_unitario=Decimal(str(linea.get("precio_unitario", 0))),
            )
            self._session.add(rl)
        await self._session.commit()
        await self._session.refresh(receipt)

        log.info(
            "receipt.created",
            receipt_id=str(receipt.id),
            codigo=codigo,
            id_bodega_destino=str(id_bodega_destino),
            total_lineas=len(lineas),
            user_id=str(user_id),
        )
        return await self.get_receipt(receipt.id)

    async def confirm_receipt(
        self,
        receipt_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Receipt:
        """Confirma una recepcion: crea movimientos ``in`` y la OC pasa a received.

        Solo se puede confirmar una recepcion en estado ``pending``.
        Es idempotente en el sentido de que NO se puede confirmar dos veces.
        """
        receipt = await self.get_receipt(receipt_id)
        if receipt is None:
            raise ValueError(f"Recepcion {receipt_id} no existe")
        if receipt.estado != "pending":
            raise ValueError(
                f"Recepcion {receipt.codigo} no se puede confirmar "
                f"(estado={receipt.estado})"
            )
        if not receipt.lineas:
            raise ValueError(f"Recepcion {receipt.codigo} no tiene lineas")

        now = datetime.now()
        for linea in receipt.lineas:
            # Generar movimiento de inventario tipo "in"
            result = await self._movement.apply(
                MovementRequest(
                    warehouse_id=receipt.id_bodega_destino,
                    product_id=linea.id_producto,
                    movement_type=MovementType.IN,
                    quantity=linea.cantidad,
                    reference_type="receipt",
                    reference_id=receipt.codigo,
                    notes=(
                        f"Recepcion {receipt.codigo} "
                        f"(doc: {receipt.numero_documento or 'N/A'})"
                    ),
                    user_id=user_id,
                )
            )
            linea.movement_id = result.movement_id

        # Si la recepcion tiene OC, marcarla como received
        if receipt.id_orden_compra is not None:
            oc = await self._session.get(OrdenCompra, receipt.id_orden_compra)
            if oc is not None and oc.estado != OrdenCompraEstado.COMPRADO.value:
                oc.estado = OrdenCompraEstado.COMPRADO.value
                oc.comprado_at = now

        receipt.estado = "confirmed"
        receipt.confirmed_at = now
        receipt.confirmed_by = user_id
        await self._session.commit()
        await self._session.refresh(receipt)

        log.info(
            "receipt.confirmed",
            receipt_id=str(receipt.id),
            codigo=receipt.codigo,
            movimientos_creados=len(receipt.lineas),
            user_id=str(user_id),
        )
        return await self.get_receipt(receipt.id)

    async def cancel_receipt(
        self,
        receipt_id: uuid.UUID,
        user_id: uuid.UUID,
        motivo: str | None = None,
    ) -> Receipt:
        """Cancela una recepcion en estado ``pending``."""
        receipt = await self.get_receipt(receipt_id)
        if receipt is None:
            raise ValueError(f"Recepcion {receipt_id} no existe")
        if receipt.estado != "pending":
            raise ValueError(
                f"Recepcion {receipt.codigo} no se puede cancelar "
                f"(estado={receipt.estado})"
            )
        receipt.estado = "cancelled"
        if motivo:
            receipt.notas = (
                (receipt.notas or "") + f" | CANCELADA: {motivo}"
            ).strip(" |")
        await self._session.commit()
        await self._session.refresh(receipt)

        log.info(
            "receipt.cancelled",
            receipt_id=str(receipt.id),
            codigo=receipt.codigo,
            motivo=motivo,
            user_id=str(user_id),
        )
        return await self.get_receipt(receipt.id)

    async def _next_codigo(self) -> str:
        """Genera el siguiente codigo de recepcion: REC-YYYYMMDD-NNNN."""
        today = datetime.now().strftime("%Y%m%d")
        prefix = f"REC-{today}-"
        # Buscar el ultimo codigo con este prefijo
        stmt = (
            select(Receipt.codigo)
            .where(Receipt.codigo.like(f"{prefix}%"))
            .order_by(Receipt.codigo.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        last = result.scalar_one_or_none()
        if last is None:
            seq = 1
        else:
            try:
                seq = int(last[len(prefix):]) + 1
            except ValueError:
                seq = 1
        return f"{prefix}{seq:04d}"
