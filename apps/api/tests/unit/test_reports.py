"""Tests del modulo de reports (Fase 8).

Cubre:
- GET /api/v1/reports/ejecutivo retorna todos los KPIs.
- El snapshot incluye alertas_criticas_count cuando hay SKUs bajo minimo.
- Los rankings (top 5 mas/menos movidos) respetan el parametro top_n.
"""
from __future__ import annotations

import os
import unittest
from decimal import Decimal
from uuid import uuid4

# Configurar el AsyncEngine antes de importar la app.
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
from app.db.models.inventory import InventoryMovement, MovementType, StockLevel
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


reset_settings_cache()


def _create_test_engine() -> AsyncEngine:
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


async def _seed_minimo_bajo(async_session: AsyncSession) -> None:
    """Inserta 1 bodega + 1 producto + 1 stock_level bajo minimo.

    Inserta en orden (warehouse -> product -> stock_level) con flush entre
    cada uno para que las FKs se satisfagan antes del siguiente INSERT.
    `session.add_all` no respeta el orden cuando hay FKs complejas.
    """
    from app.db.session import utcnow  # noqa: PLC0415

    w = Warehouse(
        id=uuid4(),
        code="CENTRAL",
        name="Bodega Central",
        warehouse_type="principal",
        is_active=True,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    async_session.add(w)
    await async_session.flush()

    p = Product(
        id=uuid4(),
        sku="SKU-001",
        name="Producto Test",
        unit="unit",
        is_active=True,
        created_at=utcnow(),
        updated_at=utcnow(),
        precio_costo=Decimal("1000"),
    )
    async_session.add(p)
    await async_session.flush()

    s = StockLevel(
        id=uuid4(),
        warehouse_id=w.id,
        product_id=p.id,
        quantity=Decimal("2"),
        min_quantity=Decimal("10"),
        updated_at=utcnow(),
    )
    async_session.add(s)
    await async_session.commit()


class ReportesTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.core.security import hash_password
        from app.db.session import create_database, utcnow
        from app.db.session import reset_engine_cache

        reset_engine_cache()
        self.engine = _create_test_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        import app.db.session as session_module
        session_module._engine = self.engine
        session_module._session_factory = self.session_factory

        self.app = create_app()
        from app.db.session import get_session

        async def _override_get_session():
            async with self.session_factory() as s:
                try:
                    yield s
                except Exception:
                    await s.rollback()
                    raise
        self.app.dependency_overrides[get_session] = _override_get_session

        legacy_db = create_database(":memory:")
        now = utcnow().isoformat()
        legacy_db.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (str(uuid4()), "admin", "Admin", "admin", hash_password("demo123"), now),
        )
        self.legacy_db = legacy_db
        self.app.state.db = legacy_db

        self.client = TestClient(self.app)
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "demo123"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.legacy_db.close()
        from app.db.session import reset_engine_cache
        reset_engine_cache()

    # ----------------------------------------------------------------- tests

    async def test_report_ejecutivo_retorna_kpis(self) -> None:
        async with self.session_factory() as s:
            await _seed_minimo_bajo(s)
        resp = self.client.get(
            "/api/v1/reports/ejecutivo", headers=self.headers
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        # Campos esperados del snapshot ejecutivo.
        for field in (
            "generado_en",
            "stock_total_activo_valorizado",
            "alertas_criticas_count",
            "transferencias_en_ruta_count",
            "solicitudes_por_estado",
            "top_productos_mas_movidos",
            "top_productos_menos_movidos",
            "valor_por_bodega",
            "total_productos_activos",
            "total_bodegas",
            "config",
        ):
            self.assertIn(field, body, f"falta campo {field} en el snapshot")
        # El ranking es una lista (puede estar vacia si no hay movimientos).
        self.assertIsInstance(body["top_productos_mas_movidos"], list)
        self.assertIsInstance(body["top_productos_menos_movidos"], list)
        # config.top_n default 5.
        self.assertEqual(body["config"]["top_n"], 5)

    async def test_report_ejecutivo_incluye_alertas_criticas(self) -> None:
        async with self.session_factory() as s:
            await _seed_minimo_bajo(s)
        resp = self.client.get(
            "/api/v1/reports/ejecutivo", headers=self.headers
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        # La seed creo un stock_level bajo minimo.
        self.assertEqual(body["alertas_criticas_count"], 1)
        # El stock valorizado incluye 2 unidades * $1000 = $2000.
        self.assertEqual(
            Decimal(str(body["stock_total_activo_valorizado"])),
            Decimal("2000"),
        )
        # Hay 1 bodega activa.
        self.assertEqual(body["total_bodegas"], 1)
        # Hay 1 producto activo.
        self.assertEqual(body["total_productos_activos"], 1)

    async def test_report_ejecutivo_respeta_top_n(self) -> None:
        # Insertamos 6 productos con 1 movimiento cada uno. top_n=3
        # deberia devolver solo 3 items en cada ranking.
        from sqlalchemy import select
        from app.db.session import utcnow  # noqa: PLC0415

        async with self.session_factory() as s:
            await _seed_minimo_bajo(s)
            w = (
                await s.execute(select(Warehouse))
            ).scalars().first()
            for i in range(5):
                p = Product(
                    id=uuid4(),
                    sku=f"SKU-{100 + i}",
                    name=f"Producto {i}",
                    unit="unit",
                    is_active=True,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                    precio_costo=Decimal("500"),
                )
                s.add(p)
                await s.flush()
                m = InventoryMovement(
                    id=uuid4(),
                    warehouse_id=w.id,
                    product_id=p.id,
                    movement_type=MovementType.IN,
                    quantity=Decimal(str(10 + i)),
                    created_at=utcnow(),
                )
                s.add(m)
            await s.commit()

        resp = self.client.get(
            "/api/v1/reports/ejecutivo?top_n=3", headers=self.headers
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        # Cada ranking limitado a 3.
        self.assertLessEqual(len(body["top_productos_mas_movidos"]), 3)
        self.assertLessEqual(len(body["top_productos_menos_movidos"]), 3)
        self.assertEqual(body["config"]["top_n"], 3)


if __name__ == "__main__":
    unittest.main()
