"""
Tests del módulo de inventario (movimientos de stock, Fase 0/1).

Cubre:
- POST /inventory/movements con movement_type=in → suma al stock.
- POST /inventory/movements con movement_type=out → resta del stock.
- POST /inventory/movements con movement_type=out sin stock → 409.
- POST /inventory/movements con movement_type=adjustment_in → suma.
- POST /inventory/movements con movement_type=adjustment_out → resta.
- GET /inventory/stock → distribución por bodega.
- GET /inventory/summary → resumen agregado.
- POST /inventory/movements con warehouse_id inexistente → 404.
- POST /inventory/movements con product_id inexistente → 404.
- POST /inventory/movements con quantity negativa/0 → 422 (Pydantic).
- POST /inventory/movements con movement_type inválido → 422.
- POST /inventory/movements sin auth → 401.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from uuid import uuid4

from app.db.session import utcnow
from app.main import create_app
from app.modules.auth.security import hash_password
from fastapi.testclient import TestClient


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "demo123"},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_warehouse(
    client: TestClient, headers: dict[str, str], code: str, wtype: str = "principal"
) -> str:
    r = client.post(
        "/api/v1/warehouses",
        json={"code": code, "name": code, "warehouse_type": wtype},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_product(
    client: TestClient, headers: dict[str, str], sku: str
) -> str:
    r = client.post(
        "/api/v1/products",
        json={"sku": sku, "name": sku, "unit": "unidad"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _post_movement(
    client: TestClient,
    headers: dict[str, str],
    warehouse_id: str,
    product_id: str,
    movement_type: str,
    quantity,
):
    return client.post(
        "/api/v1/inventory/movements",
        json={
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "movement_type": movement_type,
            "quantity": quantity,
        },
        headers=headers,
    )


class InventoryMovementsTestCase(unittest.TestCase):
    """Movimientos de stock: in, out, adjustment_in, adjustment_out."""

    def setUp(self) -> None:
        self.app = create_app(db_path=":memory:")
        self.client = TestClient(self.app)
        now = utcnow().isoformat()
        self.app.state.db.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                str(uuid4()),
                "admin",
                "Administrador Demo",
                "admin",
                hash_password("demo123"),
                now,
            ),
        )
        self.headers = _auth_headers(self.client)
        # Datos base.
        self.wh_id = _create_warehouse(self.client, self.headers, "WH-INV")
        self.product_id = _create_product(self.client, self.headers, "SKU-INV")

    def tearDown(self) -> None:
        self.app.state.db.close()

    # --- movement_type=in ---

    def test_movement_in_increases_stock(self) -> None:
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "in", 10
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        payload = resp.json()
        self.assertEqual(payload["movement_type"], "in")
        self.assertEqual(Decimal(str(payload["quantity"])), Decimal("10"))

        # El stock queda en 10.
        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": self.wh_id, "product_id": self.product_id},
            headers=self.headers,
        )
        self.assertEqual(stock.status_code, 200)
        rows = stock.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(str(rows[0]["quantity"])), Decimal("10"))

        # Otro IN acumula.
        resp2 = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "in", 5
        )
        self.assertEqual(resp2.status_code, 201)
        stock2 = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": self.wh_id, "product_id": self.product_id},
            headers=self.headers,
        )
        self.assertEqual(Decimal(str(stock2.json()[0]["quantity"])), Decimal("15"))

    # --- movement_type=out ---

    def test_movement_out_decreases_stock(self) -> None:
        _post_movement(self.client, self.headers, self.wh_id, self.product_id, "in", 20)
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "out", 7
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(resp.json()["movement_type"], "out")

        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": self.wh_id, "product_id": self.product_id},
            headers=self.headers,
        )
        self.assertEqual(Decimal(str(stock.json()[0]["quantity"])), Decimal("13"))

    def test_movement_out_insufficient_stock_returns_409(self) -> None:
        _post_movement(self.client, self.headers, self.wh_id, self.product_id, "in", 3)
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "out", 100
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(
            resp.json()["detail"]["code"], "insufficient_stock"
        )

        # El stock no cambió.
        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": self.wh_id, "product_id": self.product_id},
            headers=self.headers,
        )
        self.assertEqual(Decimal(str(stock.json()[0]["quantity"])), Decimal("3"))

    def test_movement_out_with_no_prior_stock_returns_409(self) -> None:
        # Sin IN previo, OUT no puede.
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "out", 1
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["code"], "insufficient_stock")

    # --- movement_type=adjustment_in ---

    def test_movement_adjustment_in_increases(self) -> None:
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "adjustment_in", 4
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(resp.json()["movement_type"], "adjustment_in")

        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": self.wh_id, "product_id": self.product_id},
            headers=self.headers,
        )
        self.assertEqual(Decimal(str(stock.json()[0]["quantity"])), Decimal("4"))

    # --- movement_type=adjustment_out ---

    def test_movement_adjustment_out_decreases(self) -> None:
        _post_movement(self.client, self.headers, self.wh_id, self.product_id, "in", 10)
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "adjustment_out", 6
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(resp.json()["movement_type"], "adjustment_out")

        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": self.wh_id, "product_id": self.product_id},
            headers=self.headers,
        )
        self.assertEqual(Decimal(str(stock.json()[0]["quantity"])), Decimal("4"))

    def test_movement_adjustment_out_insufficient_returns_409(self) -> None:
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "adjustment_out", 5
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["code"], "insufficient_stock")

    # --- Errores 404 ---

    def test_movement_with_nonexistent_warehouse_returns_404(self) -> None:
        resp = _post_movement(
            self.client,
            self.headers,
            str(uuid4()),
            self.product_id,
            "in",
            1,
        )
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertEqual(resp.json()["detail"]["code"], "warehouse_not_found")

    def test_movement_with_nonexistent_product_returns_404(self) -> None:
        resp = _post_movement(
            self.client,
            self.headers,
            self.wh_id,
            str(uuid4()),
            "in",
            1,
        )
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertEqual(resp.json()["detail"]["code"], "product_not_found")

    # --- Validación Pydantic (422) ---

    def test_movement_with_zero_quantity_returns_422(self) -> None:
        # Quantity usa `Annotated[Decimal, Field(gt=0, ...)]` → gt=0 rechaza 0.
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "in", 0
        )
        self.assertEqual(resp.status_code, 422)

    def test_movement_with_negative_quantity_returns_422(self) -> None:
        resp = _post_movement(
            self.client, self.headers, self.wh_id, self.product_id, "in", -5
        )
        self.assertEqual(resp.status_code, 422)

    def test_movement_with_invalid_type_returns_422(self) -> None:
        # MovementType es un StrEnum cerrado.
        resp = _post_movement(
            self.client,
            self.headers,
            self.wh_id,
            self.product_id,
            "sideways",
            1,
        )
        self.assertEqual(resp.status_code, 422)

    def test_movement_without_auth_returns_401(self) -> None:
        resp = self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": self.wh_id,
                "product_id": self.product_id,
                "movement_type": "in",
                "quantity": 1,
            },
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(
            resp.json()["detail"]["code"], "authentication_required"
        )


class InventoryStockTestCase(unittest.TestCase):
    """Listado de stock y summary."""

    def setUp(self) -> None:
        self.app = create_app(db_path=":memory:")
        self.client = TestClient(self.app)
        now = utcnow().isoformat()
        self.app.state.db.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                str(uuid4()),
                "admin",
                "Administrador Demo",
                "admin",
                hash_password("demo123"),
                now,
            ),
        )
        self.headers = _auth_headers(self.client)
        # 2 bodegas x 2 productos.
        self.wh_a = _create_warehouse(self.client, self.headers, "WH-A", "principal")
        self.wh_b = _create_warehouse(self.client, self.headers, "WH-B", "auxiliar")
        self.p1 = _create_product(self.client, self.headers, "PROD-1")
        self.p2 = _create_product(self.client, self.headers, "PROD-2")

    def tearDown(self) -> None:
        self.app.state.db.close()

    def test_stock_distribution_by_warehouse(self) -> None:
        # Llenar stock en ambas bodegas.
        _post_movement(self.client, self.headers, self.wh_a, self.p1, "in", 10)
        _post_movement(self.client, self.headers, self.wh_a, self.p2, "in", 5)
        _post_movement(self.client, self.headers, self.wh_b, self.p1, "in", 7)

        resp = self.client.get("/api/v1/inventory/stock", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        # 3 stock_levels (wh_a,p1), (wh_a,p2), (wh_b,p1).
        self.assertEqual(len(rows), 3)
        # Estructura del response.
        sample = rows[0]
        for key in (
            "warehouse_id",
            "warehouse_code",
            "warehouse_name",
            "product_id",
            "product_sku",
            "product_name",
            "quantity",
            "min_quantity",
            "updated_at",
        ):
            self.assertIn(key, sample)

    def test_stock_filtered_by_warehouse(self) -> None:
        _post_movement(self.client, self.headers, self.wh_a, self.p1, "in", 10)
        _post_movement(self.client, self.headers, self.wh_b, self.p1, "in", 7)

        resp = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": self.wh_a},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["warehouse_id"], self.wh_a)
        self.assertEqual(Decimal(str(rows[0]["quantity"])), Decimal("10"))

    def test_stock_filtered_by_sku(self) -> None:
        _post_movement(self.client, self.headers, self.wh_a, self.p1, "in", 10)
        _post_movement(self.client, self.headers, self.wh_b, self.p1, "in", 7)
        _post_movement(self.client, self.headers, self.wh_a, self.p2, "in", 5)

        resp = self.client.get(
            "/api/v1/inventory/stock",
            params={"sku": "PROD-1"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["product_sku"], "PROD-1")

    def test_summary_returns_aggregates(self) -> None:
        _post_movement(self.client, self.headers, self.wh_a, self.p1, "in", 5)

        resp = self.client.get("/api/v1/inventory/summary", headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        # Esperado:
        #   warehouses=2, products=2, stock_records=1, movements=1, low_stock_alerts=0
        self.assertEqual(payload["warehouses"], 2)
        self.assertEqual(payload["products"], 2)
        self.assertEqual(payload["stock_records"], 1)
        self.assertEqual(payload["movements"], 1)
        self.assertEqual(payload["low_stock_alerts"], 0)

    def test_movements_listing(self) -> None:
        # POST 2 IN, 1 OUT.
        _post_movement(self.client, self.headers, self.wh_a, self.p1, "in", 10)
        _post_movement(self.client, self.headers, self.wh_a, self.p1, "in", 3)
        _post_movement(self.client, self.headers, self.wh_a, self.p1, "out", 4)

        resp = self.client.get(
            "/api/v1/inventory/movements",
            params={"product_id": self.p1},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        self.assertEqual(len(rows), 3)

        # Filtro por movement_type.
        resp_in = self.client.get(
            "/api/v1/inventory/movements",
            params={"product_id": self.p1, "movement_type": "in"},
            headers=self.headers,
        )
        self.assertEqual(len(resp_in.json()), 2)

        resp_out = self.client.get(
            "/api/v1/inventory/movements",
            params={"product_id": self.p1, "movement_type": "out"},
            headers=self.headers,
        )
        self.assertEqual(len(resp_out.json()), 1)


if __name__ == "__main__":
    unittest.main()
