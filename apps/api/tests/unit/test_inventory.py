"""
Tests del módulo de inventario (movimientos de stock).

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

Migrado: usa el helper compartido ``AsyncTestBase`` que setea el
engine async y siembra el admin via AsyncSession.
"""

from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.unit._async_test_base import AsyncTestBase


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


class InventoryMovementsTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """Movimientos de stock: in, out, adjustment_in, adjustment_out."""

    def test_movement_in_increases_stock(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-IN")
        prod = _create_product(self.client, self.headers, "SKU-IN")
        r = _post_movement(self.client, self.headers, wh, prod, "in", 10)
        self.assertEqual(r.status_code, 201)
        # Verifica que el stock aumento via /stock
        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": wh, "product_id": prod},
            headers=self.headers,
        ).json()
        self.assertEqual(float(stock[0]["quantity"]), 10.0)

    def test_movement_out_decreases_stock(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-OUT")
        prod = _create_product(self.client, self.headers, "SKU-OUT")
        _post_movement(self.client, self.headers, wh, prod, "in", 10)
        r = _post_movement(self.client, self.headers, wh, prod, "out", 3)
        self.assertEqual(r.status_code, 201)
        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": wh, "product_id": prod},
            headers=self.headers,
        ).json()
        self.assertEqual(float(stock[0]["quantity"]), 7.0)

    def test_movement_out_insufficient_stock_returns_409(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-NOSTOCK")
        prod = _create_product(self.client, self.headers, "SKU-NS")
        r = _post_movement(self.client, self.headers, wh, prod, "out", 1)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["code"], "insufficient_stock")

    def test_movement_out_with_no_prior_stock_returns_409(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-NOPS")
        prod = _create_product(self.client, self.headers, "SKU-NPS")
        r = _post_movement(self.client, self.headers, wh, prod, "out", 5)
        self.assertEqual(r.status_code, 409)

    def test_movement_adjustment_in_increases(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-AIN")
        prod = _create_product(self.client, self.headers, "SKU-AIN")
        _post_movement(self.client, self.headers, wh, prod, "adjustment_in", 50)
        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": wh, "product_id": prod},
            headers=self.headers,
        ).json()
        self.assertEqual(float(stock[0]["quantity"]), 50.0)

    def test_movement_adjustment_out_decreases(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-AOUT")
        prod = _create_product(self.client, self.headers, "SKU-AOUT")
        _post_movement(self.client, self.headers, wh, prod, "in", 20)
        _post_movement(self.client, self.headers, wh, prod, "adjustment_out", 5)
        stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": wh, "product_id": prod},
            headers=self.headers,
        ).json()
        self.assertEqual(float(stock[0]["quantity"]), 15.0)

    def test_movement_adjustment_out_insufficient_returns_409(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-AON")
        prod = _create_product(self.client, self.headers, "SKU-AON")
        r = _post_movement(self.client, self.headers, wh, prod, "adjustment_out", 1)
        self.assertEqual(r.status_code, 409)

    def test_movement_with_nonexistent_warehouse_returns_404(self) -> None:
        prod = _create_product(self.client, self.headers, "SKU-NWH")
        r = _post_movement(
            self.client, self.headers, str(uuid4()), prod, "in", 1
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "warehouse_not_found")

    def test_movement_with_nonexistent_product_returns_404(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-NPR")
        r = _post_movement(
            self.client, self.headers, wh, str(uuid4()), "in", 1
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "product_not_found")

    def test_movement_with_negative_quantity_returns_422(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-NEG")
        prod = _create_product(self.client, self.headers, "SKU-NEG")
        r = _post_movement(self.client, self.headers, wh, prod, "in", -5)
        self.assertEqual(r.status_code, 422)

    def test_movement_with_zero_quantity_returns_422(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-ZERO")
        prod = _create_product(self.client, self.headers, "SKU-ZERO")
        r = _post_movement(self.client, self.headers, wh, prod, "in", 0)
        self.assertEqual(r.status_code, 422)

    def test_movement_with_invalid_type_returns_422(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-ITYPE")
        prod = _create_product(self.client, self.headers, "SKU-ITYPE")
        r = _post_movement(
            self.client, self.headers, wh, prod, "INVALID_TYPE", 1
        )
        self.assertEqual(r.status_code, 422)

    def test_movement_without_auth_returns_401(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-NOAUTH")
        prod = _create_product(self.client, self.headers, "SKU-NOAUTH")
        r = self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": wh,
                "product_id": prod,
                "movement_type": "in",
                "quantity": 1,
            },
        )
        self.assertEqual(r.status_code, 401)


class InventoryStockTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    def test_stock_filtered_by_warehouse(self) -> None:
        wh1 = _create_warehouse(self.client, self.headers, "WH-SW1")
        wh2 = _create_warehouse(self.client, self.headers, "WH-SW2")
        prod = _create_product(self.client, self.headers, "SKU-SW")
        _post_movement(self.client, self.headers, wh1, prod, "in", 5)
        _post_movement(self.client, self.headers, wh2, prod, "in", 7)
        r = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": wh1},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(float(r.json()[0]["quantity"]), 5.0)

    def test_stock_filtered_by_sku(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-SSKU")
        prod1 = _create_product(self.client, self.headers, "SKU-A")
        prod2 = _create_product(self.client, self.headers, "SKU-B")
        _post_movement(self.client, self.headers, wh, prod1, "in", 3)
        _post_movement(self.client, self.headers, wh, prod2, "in", 4)
        r = self.client.get(
            "/api/v1/inventory/stock",
            params={"sku": "SKU-A"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 1)
        self.assertEqual(r.json()[0]["product_sku"], "SKU-A")

    def test_stock_distribution_by_warehouse(self) -> None:
        wh1 = _create_warehouse(self.client, self.headers, "WH-D1")
        wh2 = _create_warehouse(self.client, self.headers, "WH-D2")
        prod = _create_product(self.client, self.headers, "SKU-D")
        _post_movement(self.client, self.headers, wh1, prod, "in", 10)
        _post_movement(self.client, self.headers, wh2, prod, "in", 5)
        r = self.client.get(
            "/api/v1/inventory/stock", headers=self.headers
        )
        self.assertEqual(r.status_code, 200)
        # 2 stock_levels rows (uno por bodega)
        self.assertEqual(len(r.json()), 2)

    def test_movements_listing(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-ML")
        prod = _create_product(self.client, self.headers, "SKU-ML")
        _post_movement(self.client, self.headers, wh, prod, "in", 1)
        _post_movement(self.client, self.headers, wh, prod, "in", 2)
        _post_movement(self.client, self.headers, wh, prod, "out", 1)
        r = self.client.get(
            "/api/v1/inventory/movements",
            params={"warehouse_id": wh, "product_id": prod},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 3)

    def test_summary_returns_aggregates(self) -> None:
        wh = _create_warehouse(self.client, self.headers, "WH-SUM")
        prod = _create_product(self.client, self.headers, "SKU-SUM")
        _post_movement(self.client, self.headers, wh, prod, "in", 5)
        r = self.client.get("/api/v1/inventory/summary", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("stock_records", body)
        self.assertIn("movements", body)
        self.assertIn("low_stock_alerts", body)
        self.assertIn("warehouses", body)
        self.assertIn("products", body)
        self.assertEqual(body["stock_records"], 1)
        self.assertEqual(body["movements"], 1)


if __name__ == "__main__":
    unittest.main()
