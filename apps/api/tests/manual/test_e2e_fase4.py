"""
E2E verification: cargar 3 productos bajo minimo en una bodega,
correr ``evaluate_all``, verificar que se crea 1 solicitud con 3 lineas.

Usado como smoke test de aceptacion para Fase 4. Se corre con
``python -m pytest tests/manual/test_e2e_fase4.py -v -s``.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault(
    "JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import reset_settings_cache  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.db.models.inventory import StockLevel  # noqa: E402
from app.db.models.products import Product  # noqa: E402
from app.db.models.solicitudes import (  # noqa: E402
    DetalleSolicitudRecarga,
    SolicitudRecarga,
)
from app.db.models.warehouses import Warehouse  # noqa: E402
from app.modules.solicitudes.replenishment import ReplenishmentEvaluator  # noqa: E402


reset_settings_cache()


def _make_engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


async def run_e2e() -> None:
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    principal_id = uuid4()
    aux1_id = uuid4()

    print("\n=== SETUP: 1 Principal + 1 Auxiliar + 3 productos bajo minimo ===")
    async with session_factory() as session:
        session.add_all([
            Warehouse(
                id=principal_id, code="PRINCIPAL", name="Bodega Principal",
                warehouse_type="principal", is_active=True,
            ),
            Warehouse(
                id=aux1_id, code="AUX-1", name="Auxiliar Taller 1",
                warehouse_type="auxiliar", is_active=True,
            ),
        ])
        await session.flush()

        p1 = uuid4()
        p2 = uuid4()
        p3 = uuid4()
        session.add_all([
            Product(id=p1, sku="F-001", name="Filtro", unit="unidad", is_active=True),
            Product(id=p2, sku="A-002", name="Aceite", unit="litro", is_active=True),
            Product(id=p3, sku="B-003", name="Bujia", unit="unidad", is_active=True),
        ])
        await session.flush()

        now = datetime.now(UTC)
        # 3 productos bajo minimo en AUX-1
        session.add_all([
            StockLevel(warehouse_id=aux1_id, product_id=p1,
                       quantity=Decimal("3"), min_quantity=Decimal("10"),
                       max_quantity=Decimal("50"), updated_at=now),
            StockLevel(warehouse_id=aux1_id, product_id=p2,
                       quantity=Decimal("1"), min_quantity=Decimal("5"),
                       max_quantity=None, updated_at=now),
            StockLevel(warehouse_id=aux1_id, product_id=p3,
                       quantity=Decimal("4"), min_quantity=Decimal("8"),
                       max_quantity=Decimal("20"), updated_at=now),
        ])
        await session.commit()
        print(f"  principal_id = {principal_id}")
        print(f"  aux1_id      = {aux1_id}")

    print("\n=== RUN: evaluate_all() ===")
    async with session_factory() as session:
        evaluator = ReplenishmentEvaluator(session)
        report = await evaluator.evaluate_all()
        await session.commit()

    print(f"  bodegas_evaluadas              = {report.bodegas_evaluadas}")
    print(f"  skus_bajo_minimo               = {report.skus_bajo_minimo}")
    print(f"  solicitudes_creadas            = {report.solicitudes_creadas}")
    print(f"  solicitudes_omitidas_pendientes= {report.solicitudes_omitidas_pendientes}")
    print(f"  errores                        = {report.errores}")

    assert report.bodegas_evaluadas == 1, "Debio evaluar 1 bodega"
    assert report.solicitudes_creadas == 1, "Debio crear 1 solicitud"
    assert report.skus_bajo_minimo == 3, "3 SKUs bajo minimo"
    assert report.solicitudes_omitidas_pendientes == 0

    print("\n=== VERIFY: 1 solicitud con 3 lineas ===")
    async with session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(SolicitudRecarga))
        solicitudes = list(result.scalars().all())
        assert len(solicitudes) == 1, f"Esperaba 1 solicitud, hay {len(solicitudes)}"
        sol = solicitudes[0]
        print(f"  codigo           = {sol.codigo}")
        print(f"  estado           = {sol.estado.value}")
        print(f"  origen           = {sol.id_bodega_origen} (debe ser {aux1_id})")
        print(f"  destino          = {sol.id_bodega_destino} (debe ser {principal_id})")
        print(f"  prioridad        = {sol.prioridad}")
        print(f"  notas            = {sol.notas}")
        assert sol.id_bodega_origen == aux1_id
        assert sol.id_bodega_destino == principal_id
        assert sol.estado.value == "pending"
        assert sol.prioridad == "alta"  # p3 ratio 0.5 es borderline, p1 y p2 son < 0.5

        result2 = await session.execute(
            select(DetalleSolicitudRecarga).where(
                DetalleSolicitudRecarga.id_solicitud == sol.id
            )
        )
        detalles = list(result2.scalars().all())
        assert len(detalles) == 3, f"Esperaba 3 lineas, hay {len(detalles)}"

        # Verificar cantidades: p1 max=50 actual=3 → 47; p2 min*2=10 actual=1 → 9; p3 max=20 actual=4 → 16
        from app.db.models.products import Product as P
        detalles_por_producto = {d.id_producto: d for d in detalles}
        productos = {
            p.id: p for p in (await session.execute(select(P).where(P.id.in_([d.id_producto for d in detalles])))).scalars().all()
        }
        print("\n  Detalles:")
        for pid, d in detalles_por_producto.items():
            print(f"    {productos[pid].sku:8s}  cantidad_solicitada = {d.cantidad_solicitada}")

        assert detalles_por_producto[p1].cantidad_solicitada == Decimal("47")
        assert detalles_por_producto[p2].cantidad_solicitada == Decimal("9")
        assert detalles_por_producto[p3].cantidad_solicitada == Decimal("16")

    print("\n=== IDEMPOTENCIA: re-correr evaluate_all() ===")
    async with session_factory() as session:
        evaluator = ReplenishmentEvaluator(session)
        report2 = await evaluator.evaluate_all()
        await session.commit()
        print(f"  solicitudes_creadas            = {report2.solicitudes_creadas}")
        print(f"  solicitudes_omitidas_pendientes= {report2.solicitudes_omitidas_pendientes}")
        assert report2.solicitudes_creadas == 0
        assert report2.solicitudes_omitidas_pendientes == 1

    print("\n[OK] E2E Fase 4: PASS")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_e2e())
