"""
Smoke tests E2E de la API HTTP (Fase 1, refactorizado a async).

Estos tests montan la app FastAPI contra una BD SQLite async (aiosqlite)
y ejercitan los endpoints principales de la API: auth, warehouses,
products, inventory, transfers (deprecado), reports.

Migrado de Fase 0/1 (sync ``SQLiteDatabase`` legacy) a Fase 3+:
- ``DATABASE_URL=sqlite+aiosqlite:///<archivo temporal>``
- Schema async + seed de admin/supervisor/origen/destino via AsyncSession.
- El ``app.state.db`` legacy NO se usa.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid

from app.core.config import reset_settings_cache
from app.db import models  # noqa: F401  -- importa modelos
from app.db.base import Base
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


def auth_headers(
    client: TestClient, username: str = "admin", password: str = "demo123"
) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class ApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="bodega-api-")
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
        now = utcnow()
        async with factory() as session:
            for username, full_name, role in [
                ("admin", "Administrador Demo", "admin"),
                ("supervisor", "Supervisor Demo", "supervisor"),
                ("origen", "Operador Origen Demo", "origin_operator"),
                ("destino", "Operador Destino Demo", "destination_operator"),
            ]:
                session.add(
                    User(
                        id=uuid.uuid4(),
                        username=username,
                        full_name=full_name,
                        role=role,
                        password_hash=hash_password("demo123"),
                        is_active=True,
                        created_at=now,
                    )
                )
            await session.commit()

        self.admin_headers = auth_headers(self.client)
        self.supervisor_headers = auth_headers(self.client, "supervisor")
        self.origin_headers = auth_headers(self.client, "origen")
        self.destination_headers = auth_headers(self.client, "destino")

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

    def test_healthcheck_returns_ok(self) -> None:
        # FIX Deuda #4: el endpoint ``/api/v1/health`` (readiness) verifica
        # BD + Redis + worker. En tests sin esos servicios retorna 503.
        # El endpoint ``/api/v1/health/live`` (liveness) es un simple
        # ping que retorna 200 con ``{"status": "alive"}``.
        response = self.client.get("/api/v1/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "alive"})

    def test_create_and_list_warehouses(self) -> None:
        create_response = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "central",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        )
        list_response = self.client.get("/api/v1/warehouses", headers=self.admin_headers)

        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertEqual(payload["code"], "CENTRAL")
        self.assertEqual(payload["warehouse_type"], "principal")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

    def test_create_and_list_products(self) -> None:
        create_response = self.client.post(
            "/api/v1/products",
            json={
                "sku": "sku-001",
                "name": "Producto Inicial",
                "unit": "Unit",
            },
            headers=self.supervisor_headers,
        )
        list_response = self.client.get("/api/v1/products", headers=self.admin_headers)

        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertEqual(payload["sku"], "SKU-001")
        self.assertEqual(payload["unit"], "unit")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

    def test_register_movements_and_read_stock(self) -> None:
        warehouse_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-001",
                "name": "Producto Inicial",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]

        incoming_response = self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "movement_type": "in",
                "quantity": 10,
                "reference_type": "manual",
                "reference_id": "ingreso-001",
                "notes": "Carga inicial",
            },
            headers=self.admin_headers,
        )
        outgoing_response = self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "movement_type": "out",
                "quantity": 3,
                "reference_type": "manual",
                "reference_id": "salida-001",
                "notes": "Salida parcial",
            },
            headers=self.admin_headers,
        )
        stock_response = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=self.admin_headers,
        )
        movement_response = self.client.get(
            "/api/v1/inventory/movements",
            params={"product_id": product_id},
            headers=self.admin_headers,
        )
        summary_response = self.client.get("/api/v1/inventory/summary", headers=self.admin_headers)

        self.assertEqual(incoming_response.status_code, 201)
        self.assertEqual(outgoing_response.status_code, 201)
        self.assertEqual(stock_response.status_code, 200)
        stock_payload = stock_response.json()
        self.assertEqual(len(stock_payload), 1)
        self.assertEqual(float(stock_payload[0]["quantity"]), 7.0)
        self.assertEqual(movement_response.status_code, 200)
        self.assertEqual(len(movement_response.json()), 2)
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()["movements"], 2)

    def test_rejects_outgoing_movement_with_insufficient_stock(self) -> None:
        warehouse_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-002",
                "name": "Producto Sin Stock",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]

        response = self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "movement_type": "out",
                "quantity": 1,
            },
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "insufficient_stock")

    @unittest.skip(
        "FIX Deuda #4: POST /transfers esta deprecado en ADR-0003. "
        "El flujo de 1 producto se migro a /api/v1/solicitudes (N productos). "
        "El flujo end-to-end equivalente se valida con el smoke_e2e_full.py."
    )
    def test_create_transfer_updates_both_warehouses(self) -> None:
        origin_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        destination_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "NORTE",
                "name": "Sucursal Norte",
                "warehouse_type": "auxiliar",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-100",
                "name": "Producto Transferible",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]

        self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": origin_id,
                "product_id": product_id,
                "movement_type": "in",
                "quantity": 10,
            },
            headers=self.admin_headers,
        )

        transfer_response = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": origin_id,
                "to_warehouse_id": destination_id,
                "product_id": product_id,
                "quantity": 4,
                "priority": "Alta",
                "notes": "Reabastecimiento interno",
            },
            headers=self.origin_headers,
        )
        transfer_id = transfer_response.json()["id"]
        approve_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/approve", headers=self.supervisor_headers
        )
        dispatch_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/dispatch",
            headers=self.origin_headers,
            json={"notes": "Salida hacia sucursal"},
        )
        receive_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/receive",
            headers=self.destination_headers,
            json={"quantity": 4, "notes": "Recepcion completa"},
        )
        list_response = self.client.get("/api/v1/transfers", headers=self.admin_headers)
        origin_stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": origin_id, "product_id": product_id},
            headers=self.admin_headers,
        )
        destination_stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": destination_id, "product_id": product_id},
            headers=self.admin_headers,
        )

        self.assertEqual(transfer_response.status_code, 201)
        self.assertEqual(transfer_response.json()["status"], "requested")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(dispatch_response.status_code, 200)
        self.assertEqual(receive_response.status_code, 200)
        self.assertEqual(receive_response.json()["status"], "received")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(float(origin_stock.json()[0]["quantity"]), 6.0)
        self.assertEqual(float(destination_stock.json()[0]["quantity"]), 4.0)

    def test_rejects_transfer_with_same_origin_and_destination(self) -> None:
        warehouse_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-200",
                "name": "Producto",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]

        response = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": warehouse_id,
                "to_warehouse_id": warehouse_id,
                "product_id": product_id,
                "quantity": 1,
            },
            headers=self.origin_headers,
        )

        # POST /transfers retorna 409 (validation error: same origin/dest)
        # o 410 si ya esta deprecado. Aceptamos ambos durante la migracion
        # a async; en la rama final solo 410.
        self.assertIn(response.status_code, (409, 410))

    def test_rejects_warehouse_with_invalid_type(self) -> None:
        response = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "INVALID",
                "name": "Bodega Invalida",
                "warehouse_type": "no_existe",
            },
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertIn("warehouse_type", str(body))

    def test_rejects_duplicate_warehouse_code(self) -> None:
        self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "DUPLICADA",
                "name": "Bodega Uno",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        )
        response = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "DUPLICADA",
                "name": "Bodega Dos",
                "warehouse_type": "auxiliar",
            },
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["detail"]["code"], "duplicate_warehouse_code"
        )

    def test_warehouse_box_requires_parent(self) -> None:
        # Crear un box sin parent → 422 (CheckConstraint parent_warehouse_id NOT NULL
        # para mecanico_box) o 400 (validacion service).
        response = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "BOX1",
                "name": "Box sin padre",
                "warehouse_type": "mecanico_box",
            },
            headers=self.admin_headers,
        )
        # El CHECK constraint dispara IntegrityError → 400/422 según
        # el handler; en ambos casos NO es 201.
        self.assertIn(response.status_code, (400, 422))
        self.assertNotEqual(response.status_code, 201)

    def test_rejects_login_with_wrong_password(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "WRONG"},
        )
        self.assertEqual(response.status_code, 401)

    @unittest.skip(
        "FIX Deuda #4: POST /transfers esta deprecado en ADR-0003."
    )
    def test_rejects_creating_transfer_with_insufficient_stock(self) -> None:
        origin_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "A",
                "name": "A",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        destination_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "B",
                "name": "B",
                "warehouse_type": "auxiliar",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={"sku": "X", "name": "X", "unit": "unit"},
            headers=self.admin_headers,
        ).json()["id"]
        # NO hay stock en origin.
        response = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": origin_id,
                "to_warehouse_id": destination_id,
                "product_id": product_id,
                "quantity": 5,
            },
            headers=self.origin_headers,
        )
        self.assertEqual(response.status_code, 201)
        transfer_id = response.json()["id"]
        approve_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/approve", headers=self.supervisor_headers
        )
        dispatch_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/dispatch",
            headers=self.origin_headers,
            json={},
        )
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(dispatch_response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
