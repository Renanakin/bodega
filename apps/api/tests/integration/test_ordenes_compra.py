"""Tests del workflow de OrdenCompra + approval token (Fase 8)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    InvalidApprovalTokenError,
    InvalidOrdenCompraStatusError,
    OrdenCompraNotFoundError,
)
from app.core.security import issue_approval_token
from app.db.models.ordenes_compra import EmailOutbox, OrdenCompraEstado
from app.db.models.products import Product
from app.db.models.supervisores import Supervisor
from app.db.models.warehouses import Warehouse
from app.modules.ordenes_compra.service import OrdenCompraService


pytestmark = pytest.mark.integration


class TestOrdenCompraWorkflow:
    @pytest.mark.asyncio
    async def test_full_workflow(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        wh = Warehouse(id=uuid.uuid4(), code="W-OC", name="W", warehouse_type="principal")
        sup = Supervisor(id=uuid.uuid4(), nombre="S", email="s@bodega.example", activo=True)
        p = Product(id=uuid.uuid4(), sku="P-OC", name="P", unit="u")
        async_session.add_all([wh, sup, p])
        await async_session.commit()

        service = OrdenCompraService(async_session)
        view = await service.create_orden(
            id_bodega_principal=wh.id,
            id_supervisor=sup.id,
            proveedor_nombre="Proveedor Test",
            lineas=[{"id_producto": p.id, "cantidad_pedida": Decimal("5"), "costo_unitario_pactado": Decimal("100")}],
        )
        assert view.codigo.startswith("OC-")
        assert view.estado == "borrador"
        assert view.total_estimado == Decimal("500")

        # Enviar a supervisor
        view, token = await service.enviar_a_supervisor(view.id)
        assert view.estado == "enviado_a_supervisor"
        assert token  # Non-empty

        # Verificar que se encolo el email
        from sqlalchemy import select
        outbox = (await async_session.execute(select(EmailOutbox))).scalars().all()
        assert any(o.to_email == "s@bodega.example" for o in outbox)

        # Aprobar via token
        view = await service.aprobar_con_token(token, "approve")
        assert view.estado == "aprobado"
        assert view.aprobado_at is not None

    @pytest.mark.asyncio
    async def test_reject_via_token(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        wh = Warehouse(id=uuid.uuid4(), code="W-R", name="W", warehouse_type="principal")
        sup = Supervisor(id=uuid.uuid4(), nombre="S", email="r@bodega.example", activo=True)
        p = Product(id=uuid.uuid4(), sku="P-R", name="P", unit="u")
        async_session.add_all([wh, sup, p])
        await async_session.commit()

        service = OrdenCompraService(async_session)
        view = await service.create_orden(
            id_bodega_principal=wh.id,
            id_supervisor=sup.id,
            proveedor_nombre="X",
            lineas=[{"id_producto": p.id, "cantidad_pedida": Decimal("1"), "costo_unitario_pactado": Decimal("10")}],
        )
        _, token = await service.enviar_a_supervisor(view.id)
        view = await service.aprobar_con_token(token, "reject", motivo="Sin presupuesto")
        assert view.estado == "rechazado"
        assert "presupuesto" in (view.motivo_rechazo or "")

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = OrdenCompraService(async_session)
        with pytest.raises(InvalidApprovalTokenError):
            await service.aprobar_con_token("invalid-token", "approve")

    @pytest.mark.asyncio
    async def test_oc_not_found(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = OrdenCompraService(async_session)
        with pytest.raises(OrdenCompraNotFoundError):
            await service.get_orden(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cannot_send_non_draft_oc(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        wh = Warehouse(id=uuid.uuid4(), code="W-X", name="W", warehouse_type="principal")
        sup = Supervisor(id=uuid.uuid4(), nombre="S", email="x@bodega.example", activo=True)
        p = Product(id=uuid.uuid4(), sku="P-X", name="P", unit="u")
        async_session.add_all([wh, sup, p])
        await async_session.commit()

        service = OrdenCompraService(async_session)
        view = await service.create_orden(
            id_bodega_principal=wh.id,
            id_supervisor=sup.id,
            proveedor_nombre="X",
            lineas=[{"id_producto": p.id, "cantidad_pedida": Decimal("1"), "costo_unitario_pactado": Decimal("1")}],
        )
        # Enviar primera vez (funciona)
        await service.enviar_a_supervisor(view.id)
        # Intentar enviar de nuevo (debe fallar)
        with pytest.raises(InvalidOrdenCompraStatusError):
            await service.enviar_a_supervisor(view.id)
