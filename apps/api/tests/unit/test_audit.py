"""
Tests del módulo de auditoría (Fase 0/1 + auth refactor).

Cubre:
- GET /audit con auth → 200 + lista de logs.
- GET /audit sin auth → 401.
- GET /audit?limit=N respeta el limit.
- Los logs de acciones (login, crear warehouse) se registran automáticamente.
- GET /audit con limit=0 → 422 (Pydantic Query validator: ge=1).
- GET /audit con limit > 200 → 422 (Pydantic Query validator: le=200).

Notas de diseño detectadas en `audit/router.py`:
- El router SOLO acepta `limit` como query param (default 50, ge=1, le=200).
- NO expone filtros por entity_type, action, user_id ni rango de fechas.
  Si el spec exige esos filtros, hay que extender el router (ver
  observación al final del archivo).
"""

from __future__ import annotations

import unittest
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
    client: TestClient, headers: dict[str, str], code: str
) -> str:
    r = client.post(
        "/api/v1/warehouses",
        json={"code": code, "name": code, "warehouse_type": "principal"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class AuditLogsTestCase(unittest.TestCase):
    """Listado de logs de auditoría."""

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

    def tearDown(self) -> None:
        self.app.state.db.close()

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
        # El setUp ya disparó un login → buscar el log "auth.login".
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
        # El router valida `Query(default=50, ge=1, le=200)`.
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
        # 200 es el máximo permitido por el router.
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
        # Crear 3 warehouses; el más reciente debería aparecer primero.
        for i in range(3):
            _create_warehouse(self.client, self.headers, f"WH-ORD-{i}")

        response = self.client.get(
            "/api/v1/audit", params={"limit": 3}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        # Por la implementación (`ORDER BY created_at DESC`), el último
        # insertado va primero.
        first_action = rows[0]["action"]
        self.assertIn(first_action, ("warehouse.create", "auth.login"))
        # Verificar orden cronológico: created_at decreciente o estable.
        timestamps = [r["created_at"] for r in rows]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))


class AuditFiltersTestCase(unittest.TestCase):
    """Filtros de GET /audit (Fase 10, Issue #2).

    El router expone filtros por:
    - ``entity_type`` (ej. 'warehouse', 'product')
    - ``action`` (ej. 'create', 'approve', 'login')
    - ``user_id`` (UUID)
    - ``date_from`` / ``date_to`` (rango ISO 8601)
    """

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

    def tearDown(self) -> None:
        self.app.state.db.close()

    def test_filter_by_entity_type(self) -> None:
        """Filtro por entity_type devuelve solo logs de ese tipo."""
        # Crear 1 warehouse (genera log de entity_type='warehouse')
        _create_warehouse(self.client, self.headers, "WH-FILT1")
        # El login genero 1 log de entity_type='session' (o similar)
        response = self.client.get(
            "/api/v1/audit",
            params={"entity_type": "warehouse", "limit": 50},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        # Solo deben venir logs de warehouses
        for row in rows:
            self.assertEqual(row["entity_type"], "warehouse")
        self.assertGreaterEqual(len(rows), 1)

    def test_filter_by_action(self) -> None:
        """Filtro por action devuelve solo logs con esa accion."""
        _create_warehouse(self.client, self.headers, "WH-FILT2")
        response = self.client.get(
            "/api/v1/audit",
            params={"action": "warehouse.create", "limit": 50},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        for row in rows:
            self.assertEqual(row["action"], "warehouse.create")
        self.assertGreaterEqual(len(rows), 1)

    def test_limit_default(self) -> None:
        """Sin params, devuelve hasta 50 logs."""
        _create_warehouse(self.client, self.headers, "WH-LIMIT")
        response = self.client.get("/api/v1/audit", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertLessEqual(len(rows), 50)


if __name__ == "__main__":
    unittest.main()
