"""Tests para ReplenishmentEvaluator y stock multibodega (Fase 6)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.db.models.inventory import MovementType, StockLevel
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from app.modules.inventory.multibodega import StockMultibodegaService
from app.modules.solicitudes.replenishment import ReplenishmentEvaluator
from app.shared.movement_engine import MovementEngine, MovementRequest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


class TestReplenishmentEvaluator:
    """Genera solicitudes automaticas cuando stock < minimo."""

    @pytest.mark.asyncio
    async def test_creates_solicitud_when_below_minimum(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh_aux = Warehouse(id=uuid.uuid4(), code="AUX-R", name="Aux", warehouse_type="auxiliar")
        wh_princ = Warehouse(
            id=uuid.uuid4(), code="PRINC-R", name="Princ", warehouse_type="principal"
        )
        p = Product(id=uuid.uuid4(), sku="P-R", name="P R", unit="u")
        async_session.add_all([wh_aux, wh_princ, p])
        await async_session.commit()

        # Cargar 5 unidades, minimo 10, maximo 50 -> debe crear solicitud por 45
        engine = MovementEngine(async_session)
        await engine.apply(
            MovementRequest(
                warehouse_id=wh_aux.id,
                product_id=p.id,
                movement_type=MovementType.IN,
                quantity=Decimal("5"),
            )
        )
        async_session.add(
            StockLevel(
                id=uuid.uuid4(),
                warehouse_id=wh_aux.id,
                product_id=p.id,
                quantity=Decimal("5"),
                min_quantity=Decimal("10"),
                max_quantity=Decimal("50"),
            )
        )
        await async_session.commit()

        evaluator = ReplenishmentEvaluator(async_session)
        report = await evaluator.evaluate_all()

        assert report.solicitudes_creadas >= 1
        assert report.skus_bajo_minimo >= 1
        assert len(report.errores) == 0

    @pytest.mark.asyncio
    async def test_idempotent_pending(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        """No crea 2da solicitud si ya hay PENDING desde la misma bodega."""
        wh_aux = Warehouse(id=uuid.uuid4(), code="AUX-ID", name="Aux", warehouse_type="auxiliar")
        wh_princ = Warehouse(
            id=uuid.uuid4(), code="PRINC-ID", name="Princ", warehouse_type="principal"
        )
        p = Product(id=uuid.uuid4(), sku="P-ID", name="P ID", unit="u")
        async_session.add_all([wh_aux, wh_princ, p])
        await async_session.commit()

        # Stock bajo minimo
        async_session.add(
            StockLevel(
                id=uuid.uuid4(),
                warehouse_id=wh_aux.id,
                product_id=p.id,
                quantity=Decimal("0"),
                min_quantity=Decimal("10"),
                max_quantity=Decimal("50"),
            )
        )
        await async_session.commit()

        # Primera evaluacion
        evaluator = ReplenishmentEvaluator(async_session)
        r1 = await evaluator.evaluate_all()
        assert r1.solicitudes_creadas == 1

        # Segunda evaluacion: debe omitir por PENDING existente
        r2 = await evaluator.evaluate_all()
        assert r2.solicitudes_creadas == 0
        assert r2.solicitudes_omitidas_pendientes >= 1


class TestStockMultibodega:
    """Vista de distribucion por bodega."""

    @pytest.mark.asyncio
    async def test_distribucion_por_sku(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh1 = Warehouse(id=uuid.uuid4(), code="W1", name="W1", warehouse_type="principal")
        wh2 = Warehouse(id=uuid.uuid4(), code="W2", name="W2", warehouse_type="auxiliar")
        p = Product(id=uuid.uuid4(), sku="MULTI-001", name="Multi Test", unit="u")
        async_session.add_all([wh1, wh2, p])
        await async_session.commit()

        async_session.add_all(
            [
                StockLevel(
                    id=uuid.uuid4(),
                    warehouse_id=wh1.id,
                    product_id=p.id,
                    quantity=Decimal("100"),
                    min_quantity=Decimal("10"),
                    max_quantity=Decimal("500"),
                ),
                StockLevel(
                    id=uuid.uuid4(),
                    warehouse_id=wh2.id,
                    product_id=p.id,
                    quantity=Decimal("3"),
                    min_quantity=Decimal("10"),
                    max_quantity=Decimal("50"),
                ),
            ]
        )
        await async_session.commit()

        service = StockMultibodegaService(async_session)
        dist = await service.distribucion_por_sku("multi-001")
        assert dist is not None
        assert dist.sku == "MULTI-001"
        assert dist.total_global == Decimal("103")
        assert len(dist.bodegas) == 2

        # W2 debe estar en alerta (3 <= 10)
        w2 = next(b for b in dist.bodegas if b.bodega_code == "W2")
        assert w2.estado == "alerta"

    @pytest.mark.asyncio
    async def test_resumen_bodegas(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        wh = Warehouse(id=uuid.uuid4(), code="W-RES", name="W Res", warehouse_type="principal")
        async_session.add(wh)
        await async_session.commit()
        async_session.add(
            StockLevel(
                id=uuid.uuid4(),
                warehouse_id=wh.id,
                product_id=uuid.uuid4(),
                quantity=Decimal("0"),
                min_quantity=Decimal("5"),
            )
        )
        await async_session.commit()

        service = StockMultibodegaService(async_session)
        resumen = await service.resumen_bodegas()
        assert any(b["code"] == "W-RES" for b in resumen)
