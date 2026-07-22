"""
Tests del módulo de stock por ubicación (migrado a Depends(get_session)).

Cubre:
- Upsert de stock por ubicación (idempotente).
- Listado granular con filtro warehouse_id y product_id.
- Distribución multibodega con formato spec §4.1.
- Bajo mínimo: respeta el filtro de bodega.

Migrado: usa ``DATABASE_URL=sqlite+aiosqlite:///<archivo>`` + schema async
+ seed del admin via AsyncSession. El UPDATE a stock_levels (para el
test de bajo mínimo) se hace via SQLAlchemy ORM, no SQL crudo.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid

from app.core.config import reset_settings_cache
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models.inventory import StockLevel
from app.db.models.users import User
from app.db.session import (
    get_engine,
    get_session_factory,
    reset_engine_cache,
    utcnow,
)
from app.main import create_app
from app.modules.auth.security import hash_password
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession


def _auth_headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "demo123"},
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _create_warehouse(client: TestClient, headers: dict[str, str], code: str) -> str:
    r = client.post(
        "/api/v1/warehouses",
        json={"code": code, "name": code, "warehouse_type": "principal"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_product(client: TestClient, headers: dict[str, str], sku: str) -> str:
    r = client.post(
        "/api/v1/products",
        json={"sku": sku, "name": sku, "unit": "unidad"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_ubicacion(
    client: TestClient, headers: dict[str, str], bodega_id: str, pasillo: int = 1
) -> str:
    r = client.post(
        f"/api/v1/bodegas/{bodega_id}/ubicaciones",
        json={"pasillo": pasillo, "estanteria": 1, "altura": 1},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _register_movement(
    client: TestClient,
    headers: dict[str, str],
    bodega_id: str,
    product_id: str,
    quantity: int,
    movement_type: str = "in",
) -> None:
    r = client.post(
        "/api/v1/inventory/movements",
        json={
            "warehouse_id": bodega_id,
            "product_id": product_id,
            "movement_type": movement_type,
            "quantity": quantity,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text


class _AsyncTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="bodega-stock-")
        self._db_path = os.path.join(self._tmpdir, "test.db")
        db_url = f"sqlite+aiosqlite:///{self._db_path}"

        self._saved_env: dict[str, str | None] = {}
        for key in (
            "DATABASE_URL",
            "ENVIRONMENT",
            "JWT_SECRET",
            "SECRET_KEY",
            "REDIS_URL",
        ):
            self._saved_env[key] = os.environ.get(key)
        os.environ["DATABASE_URL"] = db_url
        os.environ["ENVIRONMENT"] = "development"
        os.environ.setdefault("JWT_SECRET", "x" * 32)
        os.environ.setdefault("SECRET_KEY", "x" * 32)
        os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
        reset_settings_cache()
        reset_engine_cache()

        self.app = create_app()
        self.client = TestClient(self.app)

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        factory = get_session_factory()
        async with factory() as session:
            session.add(
                User(
                    id=uuid.uuid4(),
                    username="admin",
                    full_name="Admin",
                    role="admin",
                    password_hash=hash_password("demo123"),
                    is_active=True,
                    created_at=utcnow(),
                )
            )
            await session.commit()

        self.headers = _auth_headers(self.client)
        self.factory = factory

    async def asyncTearDown(self) -> None:
        await get_engine().dispose()
        reset_engine_cache()
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_settings_cache()
        try:
            os.remove(self._db_path)
            os.rmdir(self._tmpdir)
        except OSError:
            pass


class StockRealTestCase(_AsyncTestBase):
    async def _set_min_quantity(
        self, warehouse_id: str, product_id: str, min_q: int
    ) -> None:
        """Setea min_quantity via SQLAlchemy ORM (no SQL crudo)."""
        async with self.factory() as session:  # type: AsyncSession
            stmt = (
                update(StockLevel)
                .where(
                    StockLevel.warehouse_id == uuid.UUID(warehouse_id),
                    StockLevel.product_id == uuid.UUID(product_id),
                )
                .values(min_quantity=min_q)
            )
            await session.execute(stmt)
            await session.commit()

    def test_upsert_idempotente(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-UPS")
        prod = _create_product(self.client, self.headers, "SKU-UPS")
        ub = _create_ubicacion(self.client, self.headers, wh)

        first = self.client.post(
            "/api/v1/inventario/real",
            json={
                "id_producto": prod,
                "id_ubicacion": ub,
                "cantidad": 10,
            },
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(float(first.json()["cantidad"]), 10.0)

        # UPSERT: misma PK, nueva cantidad
        second = self.client.post(
            "/api/v1/inventario/real",
            json={
                "id_producto": prod,
                "id_ubicacion": ub,
                "cantidad": 25,
            },
            headers=self.headers,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(float(second.json()["cantidad"]), 25.0)

    def test_list_con_filtros(self) -> None:
        wh1 = _create_warehouse(self.client, self.headers, "WH-LST1")
        wh2 = _create_warehouse(self.client, self.headers, "WH-LST2")
        prod = _create_product(self.client, self.headers, "SKU-LST")
        ub1 = _create_ubicacion(self.client, self.headers, wh1, pasillo=1)
        ub2 = _create_ubicacion(self.client, self.headers, wh2, pasillo=2)

        for ub, qty in [(ub1, 5), (ub2, 10)]:
            r = self.client.post(
                "/api/v1/inventario/real",
                json={
                    "id_producto": prod,
                    "id_ubicacion": ub,
                    "cantidad": qty,
                },
                headers=self.headers,
            )
            self.assertEqual(r.status_code, 200)

        all_resp = self.client.get(
            "/api/v1/inventario/real",
            params={"product_id": prod},
            headers=self.headers,
        )
        self.assertEqual(all_resp.status_code, 200)
        self.assertEqual(len(all_resp.json()), 2)

        filtered = self.client.get(
            "/api/v1/inventario/real",
            params={"warehouse_id": wh1, "product_id": prod},
            headers=self.headers,
        )
        self.assertEqual(len(filtered.json()), 1)
        self.assertEqual(filtered.json()[0]["id_ubicacion"], ub1)

    def test_distribucion_multibodega_formato_spec(self) -> None:
        wh_principal = _create_warehouse(self.client, self.headers, "PRINCIPAL")
        wh_aux = _create_warehouse(self.client, self.headers, "AUX-1")
        prod = _create_product(self.client, self.headers, "SKU-MULTI")

        # Stock: principal 140, aux 12
        _register_movement(self.client, self.headers, wh_principal, prod, 140)
        _register_movement(self.client, self.headers, wh_aux, prod, 12)

        r = self.client.get(
            "/api/v1/inventario/real/distribucion",
            params={"sku": "SKU-MULTI"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["sku"], "SKU-MULTI")
        self.assertEqual(float(body["total_global"]), 152.0)
        self.assertEqual(len(body["bodegas"]), 2)

        # Verifica formato spec: bodega_code + estado
        codes = {b["bodega_code"]: b for b in body["bodegas"]}
        self.assertIn("PRINCIPAL", codes)
        self.assertIn("AUX-1", codes)
        self.assertEqual(codes["PRINCIPAL"]["estado"], "normal")
        self.assertEqual(codes["AUX-1"]["estado"], "normal")

    def test_bajo_minimo_respects_filter(self) -> None:
        wh1 = _create_warehouse(self.client, self.headers, "WH-BM1")
        wh2 = _create_warehouse(self.client, self.headers, "WH-BM2")
        prod = _create_product(self.client, self.headers, "SKU-BM")

        # WH1: 5 unidades con min=10 (bajo mínimo)
        _register_movement(self.client, self.headers, wh1, prod, 5)
        # WH2: 50 unidades con min=10 (OK)
        _register_movement(self.client, self.headers, wh2, prod, 50)

        # Setear min_quantity via SQLAlchemy ORM (no app.state.db legacy)
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            self._set_min_quantity(wh1, prod, 10)
        )
        asyncio.get_event_loop().run_until_complete(
            self._set_min_quantity(wh2, prod, 10)
        )

        # Sin filtro → ambos
        all_bm = self.client.get("/api/v1/inventario/real/bajo-minimo", headers=self.headers).json()
        self.assertEqual(len(all_bm), 1)  # Solo WH1 está bajo mínimo
        self.assertEqual(all_bm[0]["bodega_code"], "WH-BM1")

        # Con filtro bodega → solo esa
        only_wh1 = self.client.get(
            "/api/v1/inventario/real/bajo-minimo",
            params={"bodega_id": wh1},
            headers=self.headers,
        ).json()
        self.assertEqual(len(only_wh1), 1)

        only_wh2 = self.client.get(
            "/api/v1/inventario/real/bajo-minimo",
            params={"bodega_id": wh2},
            headers=self.headers,
        ).json()
        self.assertEqual(len(only_wh2), 0)

    def test_ubicacion_no_existe_en_upsert(self) -> None:
        _create_warehouse(self.client, self.headers, "WH-NOUB")
        prod = _create_product(self.client, self.headers, "SKU-NOUB")

        r = self.client.post(
            "/api/v1/inventario/real",
            json={
                "id_producto": prod,
                "id_ubicacion": str(uuid.uuid4()),
                "cantidad": 1,
            },
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "ubicacion_not_found")


if __name__ == "__main__":
    unittest.main()
