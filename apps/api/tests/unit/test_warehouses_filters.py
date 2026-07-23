"""
Tests del filtro de query params en ``GET /warehouses``.

Cubre el bug BUG-1 reportado por el usuario en pruebas manuales:
- ``?warehouse_type=auxiliar`` debe filtrar y NO devolver las principales.
- ``?warehouse_type=principal`` debe filtrar y NO devolver las auxiliares.
- ``?is_active=true`` filtra por activas.
- Sin filtros: comportamiento legacy (devuelve todas).
- ``?warehouse_type=invalido`` → 422 (Pydantic + FastAPI pattern).

Convencion: usa ``AsyncTestBase`` (engine async + admin sembrado).
"""

from __future__ import annotations

import unittest

from tests.unit._async_test_base import AsyncTestBase


class WarehouseFilterTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """Filtros de query params en ``GET /api/v1/warehouses``."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        # Sembramos 1 bodega principal primero para poder crear una mecanico_box
        # hija (CHECK: parent_warehouse_id NOT NULL cuando warehouse_type='mecanico_box').
        principal_resp = self.client.post(
            "/api/v1/warehouses",
            json={"code": "WH-FIL-PRIN", "name": "Filtrable Principal", "warehouse_type": "principal", "is_active": True},
            headers=self.headers,
        )
        self.assertEqual(
            principal_resp.status_code,
            201,
            f"seed principal fallo: {principal_resp.status_code} {principal_resp.text}",
        )
        principal_id = principal_resp.json()["id"]

        # Sembramos: 1 auxiliar activa, 1 mecanico_box inactiva (hija de la principal).
        self._seeded: list[str] = [principal_id]
        for code, name, wtype, is_active, parent_id in [
            ("WH-FIL-AUX", "Filtrable Auxiliar", "auxiliar", True, None),
            ("WH-FIL-MEC", "Filtrable Mecanico Inactivo", "mecanico_box", False, principal_id),
        ]:
            payload = {
                "code": code,
                "name": name,
                "warehouse_type": wtype,
                "is_active": is_active,
            }
            if parent_id is not None:
                payload["parent_warehouse_id"] = parent_id
            r = self.client.post(
                "/api/v1/warehouses",
                json=payload,
                headers=self.headers,
            )
            self.assertEqual(
                r.status_code,
                201,
                f"seed fallo: {r.status_code} {r.text}",
            )
            self._seeded.append(r.json()["id"])

    def test_filter_by_warehouse_type_principal(self) -> None:
        r = self.client.get(
            "/api/v1/warehouses",
            params={"warehouse_type": "principal"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        types = {w["warehouse_type"] for w in rows}
        self.assertEqual(types, {"principal"}, "Solo principal")
        # La principal que sembramos debe estar presente.
        self.assertIn(self._seeded[0], [w["id"] for w in rows])

    def test_filter_by_warehouse_type_auxiliar(self) -> None:
        r = self.client.get(
            "/api/v1/warehouses",
            params={"warehouse_type": "auxiliar"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        types = {w["warehouse_type"] for w in rows}
        self.assertEqual(types, {"auxiliar"}, "Solo auxiliar")
        self.assertIn(self._seeded[1], [w["id"] for w in rows])

    def test_filter_by_is_active_true_excludes_inactive(self) -> None:
        r = self.client.get(
            "/api/v1/warehouses",
            params={"is_active": "true"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        # Ninguna de las filas devueltas debe ser la inactiva.
        self.assertNotIn(self._seeded[2], [w["id"] for w in rows])
        self.assertTrue(all(w["is_active"] for w in rows))

    def test_filter_combined_type_and_is_active(self) -> None:
        r = self.client.get(
            "/api/v1/warehouses",
            params={"warehouse_type": "mecanico_box", "is_active": "false"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        ids = [w["id"] for w in rows]
        self.assertIn(self._seeded[2], ids)
        self.assertTrue(all(not w["is_active"] for w in rows))

    def test_no_filter_returns_all_legacy_behavior(self) -> None:
        r = self.client.get("/api/v1/warehouses", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        # Sin filtros, las 3 bodegas que sembramos deben estar.
        ids = [w["id"] for w in rows]
        for sid in self._seeded:
            self.assertIn(sid, ids)

    def test_invalid_warehouse_type_returns_422(self) -> None:
        r = self.client.get(
            "/api/v1/warehouses",
            params={"warehouse_type": "inventado"},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
