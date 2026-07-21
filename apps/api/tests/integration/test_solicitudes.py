"""
Tests E2E del workflow de solicitudes (Fase 5).

Cubre el flujo completo:
  crear -> aprobar -> despachar -> recibir -> estado final
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.core.errors import (
    InvalidSolicitudDirectionError,
    SolicitudNotFoundError,
)
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from app.modules.solicitudes.service import SolicitudService
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


class TestSolicitudWorkflow:
    """Flujo completo de una solicitud."""

    @pytest.mark.asyncio
    async def test_create_solicitud(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh_aux = Warehouse(id=uuid.uuid4(), code="AUX", name="Aux", warehouse_type="auxiliar")
        wh_princ = Warehouse(
            id=uuid.uuid4(), code="PRINC", name="Princ", warehouse_type="principal"
        )
        p1 = Product(id=uuid.uuid4(), sku="P1", name="P1", unit="u")
        p2 = Product(id=uuid.uuid4(), sku="P2", name="P2", unit="u")
        async_session.add_all([wh_aux, wh_princ, p1, p2])
        await async_session.commit()

        service = SolicitudService(async_session)
        view = await service.create_solicitud(
            id_bodega_origen=wh_aux.id,
            id_bodega_destino=wh_princ.id,
            lineas=[
                {"id_producto": p1.id, "cantidad_solicitada": Decimal("10")},
                {"id_producto": p2.id, "cantidad_solicitada": Decimal("20")},
            ],
            prioridad="Alta",
        )
        assert view.codigo.startswith("SOL-")
        assert view.estado == "pending"
        assert len(view.detalles) == 2

    @pytest.mark.asyncio
    async def test_full_workflow(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh_aux = Warehouse(id=uuid.uuid4(), code="AUX2", name="Aux2", warehouse_type="auxiliar")
        wh_princ = Warehouse(
            id=uuid.uuid4(), code="PRINC2", name="Princ2", warehouse_type="principal"
        )
        p = Product(id=uuid.uuid4(), sku="P-WF", name="P WF", unit="u")
        async_session.add_all([wh_aux, wh_princ, p])
        await async_session.commit()

        # Stock inicial en Principal (donde dispatch descuenta segun spec §3.1 / ADR-0003).
        from app.db.models.inventory import MovementType
        from app.shared.movement_engine import MovementEngine, MovementRequest

        engine = MovementEngine(async_session)
        await engine.apply(
            MovementRequest(
                warehouse_id=wh_princ.id,
                product_id=p.id,
                movement_type=MovementType.IN,
                quantity=Decimal("50"),
            )
        )
        await async_session.commit()

        # Crear -> Aprobar -> Despachar -> Recibir
        service = SolicitudService(async_session)
        view = await service.create_solicitud(
            id_bodega_origen=wh_aux.id,
            id_bodega_destino=wh_princ.id,
            lineas=[{"id_producto": p.id, "cantidad_solicitada": Decimal("30")}],
        )
        sid = view.id

        view = await service.approve_solicitud(sid)
        assert view.estado == "approved"

        view = await service.dispatch_solicitud(sid)
        assert view.estado == "in_transit"

        view = await service.receive_solicitud(
            sid, lineas=[{"id_producto": p.id, "cantidad_recibida": Decimal("30")}]
        )
        assert view.estado == "received"

    @pytest.mark.asyncio
    async def test_partial_receive(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh_aux = Warehouse(id=uuid.uuid4(), code="AUX3", name="Aux3", warehouse_type="auxiliar")
        wh_princ = Warehouse(
            id=uuid.uuid4(), code="PRINC3", name="Princ3", warehouse_type="principal"
        )
        p = Product(id=uuid.uuid4(), sku="P-PR", name="P PR", unit="u")
        async_session.add_all([wh_aux, wh_princ, p])
        await async_session.commit()

        from app.db.models.inventory import MovementType
        from app.shared.movement_engine import MovementEngine, MovementRequest

        engine = MovementEngine(async_session)
        await engine.apply(
            MovementRequest(
                warehouse_id=wh_princ.id,  # dispatch descuenta de Principal
                product_id=p.id,
                movement_type=MovementType.IN,
                quantity=Decimal("100"),
            )
        )
        await async_session.commit()

        service = SolicitudService(async_session)
        view = await service.create_solicitud(
            id_bodega_origen=wh_aux.id,
            id_bodega_destino=wh_princ.id,
            lineas=[{"id_producto": p.id, "cantidad_solicitada": Decimal("80")}],
        )
        sid = view.id
        await service.approve_solicitud(sid)
        await service.dispatch_solicitud(sid)

        # Recibir solo 30 -> debe quedar partially_received
        view = await service.receive_solicitud(
            sid, lineas=[{"id_producto": p.id, "cantidad_recibida": Decimal("30")}]
        )
        assert view.estado == "partially_received"

        # Recibir el resto
        view = await service.receive_solicitud(
            sid, lineas=[{"id_producto": p.id, "cantidad_recibida": Decimal("50")}]
        )
        assert view.estado == "received"


class TestSolicitudValidation:
    """Reglas de direccion (ADR-0002)."""

    @pytest.mark.asyncio
    async def test_rejects_origen_principal(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh_aux = Warehouse(id=uuid.uuid4(), code="AUX-V", name="Aux", warehouse_type="auxiliar")
        wh_princ = Warehouse(
            id=uuid.uuid4(), code="PRINC-V", name="Princ", warehouse_type="principal"
        )
        p = Product(id=uuid.uuid4(), sku="P-V", name="P", unit="u")
        async_session.add_all([wh_aux, wh_princ, p])
        await async_session.commit()

        service = SolicitudService(async_session)
        with pytest.raises(InvalidSolicitudDirectionError):
            await service.create_solicitud(
                id_bodega_origen=wh_princ.id,  # Principal NO puede ser origen
                id_bodega_destino=wh_aux.id,
                lineas=[{"id_producto": p.id, "cantidad_solicitada": Decimal("1")}],
            )

    @pytest.mark.asyncio
    async def test_rejects_mecanico_box_as_origin(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh_box = Warehouse(
            id=uuid.uuid4(),
            code="BOX",
            name="Box",
            warehouse_type="mecanico_box",
            parent_warehouse_id=uuid.uuid4(),
        )
        wh_aux = Warehouse(id=uuid.uuid4(), code="AUX-B", name="Aux", warehouse_type="auxiliar")
        p = Product(id=uuid.uuid4(), sku="P-B", name="P", unit="u")
        async_session.add_all([wh_box, wh_aux, p])
        await async_session.commit()

        service = SolicitudService(async_session)
        with pytest.raises(InvalidSolicitudDirectionError):
            await service.create_solicitud(
                id_bodega_origen=wh_box.id,
                id_bodega_destino=wh_aux.id,
                lineas=[{"id_producto": p.id, "cantidad_solicitada": Decimal("1")}],
            )

    @pytest.mark.asyncio
    async def test_rejects_same_origin_destination(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh = Warehouse(id=uuid.uuid4(), code="SAME", name="Same", warehouse_type="auxiliar")
        p = Product(id=uuid.uuid4(), sku="P-S", name="P", unit="u")
        async_session.add_all([wh, p])
        await async_session.commit()

        service = SolicitudService(async_session)
        with pytest.raises(InvalidSolicitudDirectionError):
            await service.create_solicitud(
                id_bodega_origen=wh.id,
                id_bodega_destino=wh.id,
                lineas=[{"id_producto": p.id, "cantidad_solicitada": Decimal("1")}],
            )

    @pytest.mark.asyncio
    async def test_rejects_empty_lines(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        from app.core.errors import InvalidTransferQuantityError

        wh_aux = Warehouse(id=uuid.uuid4(), code="AUX-E", name="Aux", warehouse_type="auxiliar")
        wh_princ = Warehouse(
            id=uuid.uuid4(), code="PRINC-E", name="Princ", warehouse_type="principal"
        )
        async_session.add_all([wh_aux, wh_princ])
        await async_session.commit()

        service = SolicitudService(async_session)
        with pytest.raises(InvalidTransferQuantityError):
            await service.create_solicitud(
                id_bodega_origen=wh_aux.id,
                id_bodega_destino=wh_princ.id,
                lineas=[],
            )

    @pytest.mark.asyncio
    async def test_solicitud_not_found(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        service = SolicitudService(async_session)
        with pytest.raises(SolicitudNotFoundError):
            await service.get_solicitud(uuid.uuid4())
