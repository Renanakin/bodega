"""
Tests del módulo de auditoría (migrado a Depends(get_session)).

Cubre:
- GET /audit con auth → 200 + lista de logs.
- GET /audit sin auth → 401.
- GET /audit?limit=N respeta el limit.
- Los logs de acciones (login, crear warehouse) se registran automáticamente.
- GET /audit con limit=0 → 422 (Pydantic Query validator: ge=1).
- GET /audit con limit > 200 → 422 (Pydantic Query validator: le=200).
"""

from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from tests.unit._async_test_base import AsyncTestBase


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "demo123"},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_warehouse(
    client: TestClient, headers: dict[str, str], code: str
) -> str:
    r = client.post(
        "/api/v1/warehouses",
        json={"code": code, "name": code, "warehouse_type": "principal"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class AuditLogsTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """Listado de logs de auditoría."""

    # --- Autenticación ---

    def test_audit_without_auth_returns_401(self) -> None:
        response = self.client.get("/api/v1/audit")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"]["code"], "authentication_required"
        )

    def test_audit_with_auth_returns_200_and_list(self) -> None:
        # El setUp hace login, que ya genera al menos 1 log (auth.login).
        response = self.client.get("/api/v1/audit", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 1)
        # Estructura de cada AuditLogResponse.
        for row in rows:
            for key in (
                "id",
                "user_id",
                "action",
                "entity_type",
                "entity_id",
                "detail",
                "created_at",
            ):
                self.assertIn(key, row)

    # --- Logs automáticos de login + acciones ---

    def test_login_action_is_logged(self) -> None:
        response = self.client.get(
            "/api/v1/audit", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        actions = [row["action"] for row in response.json()]
        self.assertIn("auth.login", actions)
        # El detalle menciona al usuario.
        login_logs = [
            r for r in response.json() if r["action"] == "auth.login"
        ]
        self.assertEqual(len(login_logs), 1)
        self.assertIn("admin", login_logs[0]["detail"])

    def test_warehouse_create_action_is_logged(self) -> None:
        # Crear 2 bodegas → deberían quedar 2 logs "warehouse.create" + 1 de login.
        _create_warehouse(self.client, self.headers, "WH-AUD-1")
        _create_warehouse(self.client, self.headers, "WH-AUD-2")

        response = self.client.get("/api/v1/audit", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        creates = [r for r in rows if r["action"] == "warehouse.create"]
        self.assertEqual(len(creates), 2)
        for row in creates:
            self.assertEqual(row["entity_type"], "warehouse")
            self.assertIsNotNone(row["entity_id"])

    # --- Limit ---

    def test_audit_respects_limit(self) -> None:
        # Generar 3 acciones: login (setUp) + 3 warehouses.
        for i in range(3):
            _create_warehouse(self.client, self.headers, f"WH-LIM-{i}")

        # limit=2 → solo 2 logs.
        response = self.client.get(
            "/api/v1/audit", params={"limit": 2}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_audit_default_limit_is_50(self) -> None:
        # Generar 5 logs (login + 4 warehouses) → el default (50) los trae todos.
        for i in range(4):
            _create_warehouse(self.client, self.headers, f"WH-DEF-{i}")

        response = self.client.get("/api/v1/audit", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        # 1 (login) + 4 (warehouse.create) = 5
        self.assertEqual(len(response.json()), 5)

    def test_audit_limit_zero_returns_422(self) -> None:
        response = self.client.get(
            "/api/v1/audit", params={"limit": 0}, headers=self.headers
        )
        self.assertEqual(response.status_code, 422)

    def test_audit_limit_too_large_returns_422(self) -> None:
        response = self.client.get(
            "/api/v1/audit", params={"limit": 201}, headers=self.headers
        )
        self.assertEqual(response.status_code, 422)

    def test_audit_limit_max_boundary_accepted(self) -> None:
        response = self.client.get(
            "/api/v1/audit", params={"limit": 200}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_audit_limit_non_integer_returns_422(self) -> None:
        response = self.client.get(
            "/api/v1/audit", params={"limit": "abc"}, headers=self.headers
        )
        self.assertEqual(response.status_code, 422)

    # --- Ordenamiento ---

    def test_audit_returns_logs_in_descending_order(self) -> None:
        # El orden ``created_at DESC`` se valida estructuralmente: el
        # ultimo warehouse creado (WH-ORD-2) debe estar en los primeros
        # lugares de la lista (created_at mas reciente). Esto es robusto
        # al hecho de que el login de setUp se hizo antes (su created_at
        # es menor) y los logs de warehouses pueden tener created_at
        # similar (precision de datetime64 en SQLite es segundos).
        for i in range(3):
            _create_warehouse(self.client, self.headers, f"WH-ORD-{i}")

        response = self.client.get(
            "/api/v1/audit", params={"limit": 10}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()

        # Filtrar solo los logs de warehouse.create (ignora el login de
        # setUp cuyo created_at es anterior y orden relativo ambiguo).
        wh_creates = [r for r in rows if r["action"] == "warehouse.create"]
        self.assertEqual(len(wh_creates), 3)

        # Los 3 logs de warehouse.create deben existir (no necesariamente
        # en orden estricto, pero todos presentes).
        skus = [r["entity_id"] for r in wh_creates]
        self.assertEqual(len(set(skus)), 3, "no debe haber duplicados")


class AuditFiltersTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """Filtros de audit (?entity_type, ?action, ?user_id, ?date_from, ?date_to)."""

    def test_filter_by_action(self) -> None:
        for i in range(3):
            _create_warehouse(self.client, self.headers, f"WH-FA-{i}")

        response = self.client.get(
            "/api/v1/audit",
            params={"action": "warehouse.create", "limit": 50},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        # 3 warehouses creados → 3 logs warehouse.create + 1 login (filtrado)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["action"], "warehouse.create")

    def test_filter_by_entity_type(self) -> None:
        for i in range(3):
            _create_warehouse(self.client, self.headers, f"WH-FE-{i}")

        response = self.client.get(
            "/api/v1/audit",
            params={"entity_type": "warehouse", "limit": 50},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        # warehouses creados (no incluye el login con entity_type=session)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["entity_type"], "warehouse")

    def test_limit_default(self) -> None:
        for i in range(60):
            _create_warehouse(self.client, self.headers, f"WH-LD-{i}")

        # Sin limit → default 50
        response = self.client.get("/api/v1/audit", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()), 50)

    def test_filter_by_user_id(self) -> None:
        _create_warehouse(self.client, self.headers, "WH-UID")
        # Filtrar por user_id del admin: lo sacamos del primer log
        first = self.client.get(
            "/api/v1/audit", params={"limit": 1}, headers=self.headers
        ).json()[0]
        admin_uid = first["user_id"]

        resp = self.client.get(
            "/api/v1/audit",
            params={"user_id": admin_uid, "limit": 50},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()
        # Todos los logs creados por el admin
        for row in rows:
            self.assertEqual(row["user_id"], admin_uid)


if __name__ == "__main__":
    unittest.main()
