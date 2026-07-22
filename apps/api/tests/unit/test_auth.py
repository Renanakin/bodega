"""
Tests del módulo de autenticación (Fase 0/1 + auth refactor).

Cubre:
- Login con credenciales válidas → 200 + token.
- Login con password incorrecto → 401.
- Login con usuario inexistente → 401.
- Login con body inválido (sin username/password) → 422.
- GET /auth/me con token válido → user actual.
- GET /auth/me sin token → 401.
- GET /auth/me con token inválido → 401.
- POST /auth/logout invalida el token (un GET /me posterior → 401).
- Token expirado/manipulado rechazado.
- Login con usuario inactivo (is_active=0) → 401.
- /auth/me no restringe por rol (admin, supervisor, etc. → 200).

FIX BUG-002: el ``AuthRepository`` ahora es híbrido — soporta tanto
``SQLiteDatabase`` legacy (modo tests con ``db_path``) como ``AsyncSession``
(modo producción con Postgres/SQLite async). El test sigue usando el
modo legacy para compatibilidad con el resto de la suite.
"""

from __future__ import annotations

import unittest
from uuid import uuid4

from app.db.session import utcnow
from app.main import create_app
from app.modules.auth.security import hash_password
from fastapi.testclient import TestClient


def _login(client: TestClient, username: str = "admin", password: str = "demo123"):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = _login(client)
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class AuthLoginTestCase(unittest.TestCase):
    """Tests de /auth/login y /auth/logout."""

    def setUp(self) -> None:
        self.app = create_app(db_path=":memory:")
        self.client = TestClient(self.app)
        self._create_admin()

    def tearDown(self) -> None:
        self.app.state.db.close()

    def _create_admin(self, is_active: int = 1) -> None:
        now = utcnow().isoformat()
        self.app.state.db.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                "admin",
                "Administrador Demo",
                "admin",
                hash_password("demo123"),
                is_active,
                now,
            ),
        )

    def test_login_valid_credentials_returns_token(self) -> None:
        response = _login(self.client, "admin", "demo123")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("token", payload)
        self.assertIsInstance(payload["token"], str)
        self.assertGreater(len(payload["token"]), 0)
        self.assertIn("expires_at", payload)

    def test_login_invalid_password_returns_401(self) -> None:
        response = _login(self.client, "admin", "wrong-password")
        self.assertEqual(response.status_code, 401)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "invalid_credentials")

    def test_login_nonexistent_user_returns_401(self) -> None:
        response = _login(self.client, "ghost", "demo123")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "invalid_credentials")

    def test_login_invalid_body_returns_422(self) -> None:
        no_pw = self.client.post(
            "/api/v1/auth/login", json={"username": "admin"}
        )
        self.assertEqual(no_pw.status_code, 422)
        no_user = self.client.post(
            "/api/v1/auth/login", json={"password": "demo123"}
        )
        self.assertEqual(no_user.status_code, 422)
        empty = self.client.post("/api/v1/auth/login", json={})
        self.assertEqual(empty.status_code, 422)

    def test_login_inactive_user_rejected(self) -> None:
        self.app.state.db.close()
        self.app = create_app(db_path=":memory:")
        self.client = TestClient(self.app)
        self._create_admin(is_active=0)

        response = _login(self.client, "admin", "demo123")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "invalid_credentials")

    def test_login_trims_and_lowercases_username(self) -> None:
        response = _login(self.client, "  Admin  ", "demo123")
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    def test_logout_invalidates_token(self) -> None:
        headers = _auth_headers(self.client)
        me_before = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(me_before.status_code, 200)

        logout_resp = self.client.post("/api/v1/auth/logout", headers=headers)
        self.assertEqual(logout_resp.status_code, 204)

        me_after = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(me_after.status_code, 401)
        self.assertEqual(
            me_after.json()["detail"]["code"], "authentication_required"
        )

    def test_logout_without_token_returns_204(self) -> None:
        response = self.client.post("/api/v1/auth/logout")
        self.assertEqual(response.status_code, 204)


class AuthMeTestCase(unittest.TestCase):
    """Tests de /auth/me y la dependency get_current_user."""

    def setUp(self) -> None:
        self.app = create_app(db_path=":memory:")
        self.client = TestClient(self.app)
        now = utcnow().isoformat()
        self.admin_id = str(uuid4())
        self.app.state.db.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                self.admin_id,
                "admin",
                "Administrador Demo",
                "admin",
                hash_password("demo123"),
                now,
            ),
        )
        self.supervisor_id = str(uuid4())
        self.app.state.db.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                self.supervisor_id,
                "juan",
                "Juan Supervisor",
                "supervisor",
                hash_password("demo123"),
                now,
            ),
        )
        self.admin_headers = _auth_headers(self.client)
        resp = _login(self.client, "juan", "demo123")
        self.supervisor_headers = {
            "Authorization": f"Bearer {resp.json()['token']}"
        }

    def tearDown(self) -> None:
        self.app.state.db.close()

    def test_me_with_valid_token_returns_user(self) -> None:
        response = self.client.get("/api/v1/auth/me", headers=self.admin_headers)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["username"], "admin")
        self.assertEqual(payload["role"], "admin")
        self.assertEqual(payload["full_name"], "Administrador Demo")
        self.assertTrue(payload["is_active"])
        self.assertEqual(payload["id"], self.admin_id)

    def test_me_without_token_returns_401(self) -> None:
        response = self.client.get("/api/v1/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"]["code"], "authentication_required"
        )

    def test_me_with_invalid_token_returns_401(self) -> None:
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer this-is-not-a-real-token"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"]["code"], "authentication_required"
        )

    def test_me_with_malformed_authorization_header_returns_401(self) -> None:
        response = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Token abc"},
        )
        self.assertEqual(response.status_code, 401)
        response2 = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": ""},
        )
        self.assertEqual(response2.status_code, 401)

    def test_me_does_not_restrict_by_role(self) -> None:
        admin_resp = self.client.get(
            "/api/v1/auth/me", headers=self.admin_headers
        )
        self.assertEqual(admin_resp.status_code, 200)
        self.assertEqual(admin_resp.json()["role"], "admin")

        sup_resp = self.client.get(
            "/api/v1/auth/me", headers=self.supervisor_headers
        )
        self.assertEqual(sup_resp.status_code, 200)
        self.assertEqual(sup_resp.json()["role"], "supervisor")
        self.assertEqual(sup_resp.json()["id"], self.supervisor_id)


if __name__ == "__main__":
    unittest.main()
