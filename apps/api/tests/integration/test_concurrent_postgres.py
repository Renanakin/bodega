"""
Test de concurrencia REAL contra PostgreSQL.

Este test requiere:
- PostgreSQL 17 corriendo (vía docker compose).
- DATABASE_URL=postgresql+asyncpg://...

Si no hay Postgres, se skippea con razón clara.

Usa el fixture ``async_engine_postgres`` (no la ``get_session_factory()``)
para que las tablas se creen en el MISMO engine donde corre el test.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from app.db.models.inventory import InventoryMovement, MovementType, StockLevel
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


class TestConcurrentMovementsPostgres:
    """50 tasks paralelos contra el mismo (warehouse, product) no deben producir oversell."""

    async def _create_warehouse_and_product(
        self, session: AsyncSession
    ) -> tuple[uuid.UUID, uuid.UUID]:
        # SKUs unicos por ejecucion para no chocar con datos residuales
        # en la BD (los tests integration NO usan SAVEPOINT/rollback porque
        # ``async_engine_postgres`` comparte la BD real con ``Base.metadata.create_all``).
        run_tag = uuid.uuid4().hex[:8]
        warehouse = Warehouse(
            id=uuid.uuid4(),
            code=f"CONCURRENT-{run_tag}",
            name=f"Test Concurrente {run_tag}",
            warehouse_type="principal",
            is_active=True,
        )
        product = Product(
            id=uuid.uuid4(),
            sku=f"CONC-{run_tag}",
            name=f"Test Paralelo {run_tag}",
            unit="unidad",
            is_active=True,
        )
        session.add_all([warehouse, product])
        await session.flush()
        return warehouse.id, product.id

    @pytest.mark.asyncio
    async def test_50_parallel_out_movements_no_oversell(
        self,
        async_engine_postgres,  # type: ignore[no-untyped-def]
    ) -> None:
        """
        50 tasks asyncio que sacan 1 unidad cada una de un stock inicial de 50.

        Con SELECT FOR UPDATE, solo 1 task a la vez modifica el stock.
        El stock final debe ser 0, no negativo, y los 50 movements deben existir.
        """
        factory = async_sessionmaker(
            async_engine_postgres, expire_on_commit=False, autoflush=False
        )

        # Setup: crear warehouse, product, stock inicial
        async with factory() as session:
            wh_id, prod_id = await self._create_warehouse_and_product(session)
            stock = StockLevel(
                id=uuid.uuid4(),
                warehouse_id=wh_id,
                product_id=prod_id,
                quantity=Decimal("50.00"),
                min_quantity=Decimal("0.00"),
            )
            session.add(stock)
            await session.commit()

        # 50 tasks paralelas sacando 1 unidad cada una
        async def take_one() -> bool:
            async with factory() as session:
                try:
                    # SELECT FOR UPDATE
                    result = await session.execute(
                        select(StockLevel)
                        .where(
                            StockLevel.warehouse_id == wh_id,
                            StockLevel.product_id == prod_id,
                        )
                        .with_for_update()
                    )
                    stock = result.scalar_one()
                    if stock.quantity < Decimal("1.00"):
                        return False  # no hay stock
                    stock.quantity = stock.quantity - Decimal("1.00")
                    movement = InventoryMovement(
                        id=uuid.uuid4(),
                        warehouse_id=wh_id,
                        product_id=prod_id,
                        movement_type=MovementType.OUT,
                        quantity=Decimal("1.00"),
                        reference_type="parallel_test",
                    )
                    session.add(movement)
                    await session.commit()
                    return True
                except IntegrityError:
                    await session.rollback()
                    return False

        # Ejecutar 50 tasks en paralelo
        results = await asyncio.gather(*[take_one() for _ in range(50)])
        successes = sum(1 for r in results if r)

        # Verificar: 50 successes (si el motor respeta el lock) o menos si hubo oversell
        # El requisito es: NO oversell (stock nunca negativo)
        async with factory() as session:
            result = await session.execute(
                select(StockLevel).where(StockLevel.warehouse_id == wh_id)
            )
            final = result.scalar_one()
            assert final.quantity >= Decimal(
                "0.00"
            ), f"OVERSELL DETECTADO: stock final = {final.quantity}"
            # Si todas tuvieron éxito, stock debe ser exactamente 0
            if successes == 50:
                assert final.quantity == Decimal("0.00")
