"""
Tests del constraint UNIQUE en ``warehouses.name`` (C1.1).

Cubre:
- POST /warehouses con ``code`` duplicado → 409 ``duplicate_warehouse_code``.
- POST /warehouses con ``name`` duplicado → 409 ``duplicate_warehouse_name``
  (C1.1: el constraint UNIQUE existe en BD desde migración 0001; este test
  verifica que el service lo enforza también a nivel aplicación para evitar
  un 500 IntegrityError bajo concurrencia).
- POST /warehouses con ``code`` y ``name`` únicos → 201.

Migrado: usa el helper compartido ``AsyncTestBase`` que setea el
engine async y siembra el admin via AsyncSession.
"""

from __future__ import annotations

import unittest

from tests.unit._async_test_base import AsyncTestBase


class WarehouseUniquenessTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """Conflictos de unicidad en warehouses."""

    def test_duplicate_code_returns_409(self) -> None:
        r1 = self.client.post(
            "/api/v1/warehouses",
            json={"code": "WH-DUP-CODE", "name": "Alpha", "warehouse_type": "principal"},
            headers=self.headers,
        )
        self.assertEqual(r1.status_code, 201, r1.text)
        r2 = self.client.post(
            "/api/v1/warehouses",
            json={"code": "WH-DUP-CODE", "name": "Beta", "warehouse_type": "principal"},
            headers=self.headers,
        )
        self.assertEqual(r2.status_code, 409, r2.text)
        self.assertEqual(r2.json()["detail"]["code"], "duplicate_warehouse_code")

    def test_duplicate_name_returns_409(self) -> None:
        """C1.1: el service debe devolver 409 limpio en lugar de un 500."""
        r1 = self.client.post(
            "/api/v1/warehouses",
            json={"code": "WH-A", "name": "Same Name", "warehouse_type": "principal"},
            headers=self.headers,
        )
        self.assertEqual(r1.status_code, 201, r1.text)
        r2 = self.client.post(
            "/api/v1/warehouses",
            json={"code": "WH-B", "name": "Same Name", "warehouse_type": "principal"},
            headers=self.headers,
        )
        self.assertEqual(r2.status_code, 409, r2.text)
        body = r2.json()
        self.assertEqual(body["detail"]["code"], "duplicate_warehouse_name")
        # El extra incluye field + value para que el cliente sepa qué campo
        # corregir sin tener que parsear el mensaje en español.
        self.assertEqual(body["detail"]["extra"]["field"], "name")
        self.assertEqual(body["detail"]["extra"]["value"], "Same Name")

    def test_unique_code_and_name_returns_201(self) -> None:
        """Happy path: code y name distintos → 201."""
        r = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "WH-UNIQ-1",
                "name": "Unique Warehouse",
                "warehouse_type": "auxiliar",
            },
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["code"], "WH-UNIQ-1")
        self.assertEqual(body["name"], "Unique Warehouse")
        self.assertEqual(body["warehouse_type"], "auxiliar")


if __name__ == "__main__":
    unittest.main()
