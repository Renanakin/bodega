"""
Tests unitarios de MovementEngine (Fase 3).

Cubre:
- Aplicación de movimiento IN (entrada).
- Aplicación de movimiento OUT (salida).
- Rechazo por oversell (InsufficientStockError).
- Validación de warehouse/product no existentes.
- Cálculo de delta correcto por movement_type.
- Log estructurado emitido con todos los campos.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.core.errors import (
    InsufficientStockError,
    ProductNotFoundError,
    WarehouseNotFoundError,
)
from app.db.models.inventory import MovementType
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from app.shared.movement_engine import MovementEngine, MovementRequest
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.unit, pytest.mark.concurrency]


class TestMovementEngineDelta:
    """Cálculo de delta según tipo de movimiento."""

    def test_in_positive(self) -> None:
        delta = MovementEngine._compute_delta(MovementType.IN, Decimal("10"))
        assert delta == Decimal("10")

    def test_out_negative(self) -> None:
        delta = MovementEngine._compute_delta(MovementType.OUT, Decimal("5"))
        assert delta == Decimal("-5")

    def test_adjustment_in_positive(self) -> None:
        delta = MovementEngine._compute_delta(MovementType.ADJUSTMENT_IN, Decimal("3"))
        assert delta == Decimal("3")

    def test_adjustment_out_negative(self) -> None:
        delta = MovementEngine._compute_delta(MovementType.ADJUSTMENT_OUT, Decimal("7"))
        assert delta == Decimal("-7")


class TestMovementEngineApply:
    """Aplicación de movimientos con SQLite async (sin lock real pero sí patrón)."""

    @pytest.mark.asyncio
    async def test_in_movement_creates_stock(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        warehouse = Warehouse(
            id=uuid.uuid4(),
            code="W1",
            name="W1",
            warehouse_type="principal",
            is_active=True,
        )
        product = Product(
            id=uuid.uuid4(),
            sku="P1",
            name="P1",
            unit="unidad",
            is_active=True,
        )
        async_session.add_all([warehouse, product])
        await async_session.commit()

        engine = MovementEngine(async_session)
        result = await engine.apply(
            MovementRequest(
                warehouse_id=warehouse.id,
                product_id=product.id,
                movement_type=MovementType.IN,
                quantity=Decimal("50"),
                reference_type="test",
                reference_id="t-001",
                user_id=uuid.uuid4(),
            )
        )

        assert result.previous_quantity == Decimal("0")
        assert result.new_quantity == Decimal("50")
        assert result.delta == Decimal("50")

    @pytest.mark.asyncio
    async def test_out_movement_decrements_stock(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        warehouse = Warehouse(
            id=uuid.uuid4(),
            code="W1",
            name="W1",
            warehouse_type="principal",
            is_active=True,
        )
        product = Product(
            id=uuid.uuid4(),
            sku="P1",
            name="P1",
            unit="unidad",
            is_active=True,
        )
        async_session.add_all([warehouse, product])
        await async_session.commit()

        engine = MovementEngine(async_session)
        # Primero cargar stock
        await engine.apply(
            MovementRequest(
                warehouse_id=warehouse.id,
                product_id=product.id,
                movement_type=MovementType.IN,
                quantity=Decimal("100"),
            )
        )
        await async_session.commit()

        # Luego salida
        result = await engine.apply(
            MovementRequest(
                warehouse_id=warehouse.id,
                product_id=product.id,
                movement_type=MovementType.OUT,
                quantity=Decimal("30"),
            )
        )
        assert result.previous_quantity == Decimal("100")
        assert result.new_quantity == Decimal("70")
        assert result.delta == Decimal("-30")

    @pytest.mark.asyncio
    async def test_oversell_raises_insufficient_stock(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        warehouse = Warehouse(
            id=uuid.uuid4(),
            code="W1",
            name="W1",
            warehouse_type="principal",
            is_active=True,
        )
        product = Product(
            id=uuid.uuid4(),
            sku="P1",
            name="P1",
            unit="unidad",
            is_active=True,
        )
        async_session.add_all([warehouse, product])
        await async_session.commit()

        engine = MovementEngine(async_session)
        # Stock inicial = 10
        await engine.apply(
            MovementRequest(
                warehouse_id=warehouse.id,
                product_id=product.id,
                movement_type=MovementType.IN,
                quantity=Decimal("10"),
            )
        )
        await async_session.commit()

        # Intentar sacar 20 → debe fallar
        with pytest.raises(InsufficientStockError) as exc_info:
            await engine.apply(
                MovementRequest(
                    warehouse_id=warehouse.id,
                    product_id=product.id,
                    movement_type=MovementType.OUT,
                    quantity=Decimal("20"),
                )
            )

        assert exc_info.value.status_code == 409
        assert "insufficient_stock" in str(exc_info.value.code)

    @pytest.mark.asyncio
    async def test_warehouse_not_found(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        engine = MovementEngine(async_session)
        with pytest.raises(WarehouseNotFoundError):
            await engine.apply(
                MovementRequest(
                    warehouse_id=uuid.uuid4(),  # bodega inexistente
                    product_id=uuid.uuid4(),
                    movement_type=MovementType.IN,
                    quantity=Decimal("1"),
                )
            )

    @pytest.mark.asyncio
    async def test_product_not_found(
        self,
        async_engine,
        async_session: AsyncSession,  # type: ignore[no-untyped-def]
    ) -> None:
        warehouse = Warehouse(
            id=uuid.uuid4(),
            code="W1",
            name="W1",
            warehouse_type="principal",
            is_active=True,
        )
        async_session.add(warehouse)
        await async_session.commit()

        engine = MovementEngine(async_session)
        with pytest.raises(ProductNotFoundError):
            await engine.apply(
                MovementRequest(
                    warehouse_id=warehouse.id,
                    product_id=uuid.uuid4(),  # producto inexistente
                    movement_type=MovementType.IN,
                    quantity=Decimal("1"),
                )
            )


class TestMovementEngineEmitsLog:
    """Cada movimiento emite un log info (R8).

    La verificación detallada de campos está en
    tests/integration/test_concurrent_movement_engine.py con mock.
    Aquí solo verificamos que se llama a log.info.
    """

    @pytest.mark.asyncio
    async def test_movement_emits_log_info(
        self,
        async_engine,  # type: ignore[no-untyped-def]
        async_session: AsyncSession,
    ) -> None:
        from unittest.mock import patch

        warehouse = Warehouse(
            id=uuid.uuid4(),
            code="W_LOG",
            name="W Log",
            warehouse_type="principal",
            is_active=True,
        )
        product = Product(
            id=uuid.uuid4(),
            sku="P_LOG",
            name="P Log",
            unit="unidad",
            is_active=True,
        )
        async_session.add_all([warehouse, product])
        await async_session.commit()

        with patch("app.shared.movement_engine.log") as mock_log:
            engine = MovementEngine(async_session)
            await engine.apply(
                MovementRequest(
                    warehouse_id=warehouse.id,
                    product_id=product.id,
                    movement_type=MovementType.IN,
                    quantity=Decimal("1"),
                )
            )
            # Verificar que se llamó log.info con "movement.applied"
            assert any(
                call_args and call_args[0] and call_args[0][0] == "movement.applied"
                for call_args in mock_log.info.call_args_list
            ), f"Expected movement.applied log, got: {mock_log.info.call_args_list}"
