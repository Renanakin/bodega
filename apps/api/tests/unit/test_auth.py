"""
Tests del módulo de autenticación (migrado a Depends(get_session)).

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

Migrado a async puro: usa ``DATABASE_URL=sqlite+aiosqlite:///<archivo>``
+ schema async + seed del admin via AsyncSession. El
``SQLiteDatabase`` legacy ya no se usa (auth detecta el modo por el
tipo de session, AsyncSession para tests con este patron).
"""

from __future__ import annotations

import unittest
import uuid

from tests.unit._async_test_base import AsyncTestBase


def _login(client, username: str = "admin", password: str = "demo123"):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def _auth_headers(client) -> dict[str, str]:
    response = _login(client)
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class AuthLoginTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """Tests de /auth/login y /auth/logout."""

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

    async def test_login_inactive_user_returns_401(self) -> None:
        # Sobrescribir el admin sembrado por setUp con uno inactivo.
        from app.db.session import utcnow
        from app.modules.auth.security import hash_password

        async with self.factory() as session:
            # Borrar el admin activo primero
            from app.db.models.users import User

            from sqlalchemy import delete
            await session.execute(delete(User).where(User.username == "admin"))
            session.add(
                User(
                    id=uuid.uuid4(),
                    username="admin",
                    full_name="Admin Inactivo",
                    role="admin",
                    password_hash=hash_password("demo123"),
                    is_active=False,
                    created_at=utcnow(),
                )
            )
            await session.commit()

        response = _login(self.client, "admin", "demo123")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["code"], "invalid_credentials")

    async def test_login_trims_and_lowercases_username(self) -> None:
        # Crear un usuario con username lowercase
        from app.db.session import utcnow
        from app.modules.auth.security import hash_password

        async with self.factory() as session:
            from app.db.models.users import User

            from sqlalchemy import delete
            await session.execute(delete(User).where(User.username == "admin"))
            session.add(
                User(
                    id=uuid.uuid4(),
                    username="admin",
                    full_name="Admin Trim",
                    role="admin",
                    password_hash=hash_password("demo123"),
                    is_active=True,
                    created_at=utcnow(),
                )
            )
            await session.commit()

        # Login con espacios y mayusculas debe normalizarse
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "  ADMIN  ", "password": "demo123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.json())

    def test_logout_invalidates_token(self) -> None:
        headers = _auth_headers(self.client)
        logout = self.client.post("/api/v1/auth/logout", headers=headers)
        self.assertEqual(logout.status_code, 204)
        # El token ya no funciona
        me = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(me.status_code, 401)

    def test_logout_without_token_returns_204(self) -> None:
        logout = self.client.post("/api/v1/auth/logout")
        self.assertEqual(logout.status_code, 204)


class AuthMeTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """Tests de /auth/me."""

    def test_me_with_valid_token_returns_user(self) -> None:
        headers = _auth_headers(self.client)
        me = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(me.status_code, 200)
        body = me.json()
        self.assertEqual(body["username"], "admin")
        self.assertEqual(body["role"], "admin")
        self.assertTrue(body["is_active"])

    def test_me_without_token_returns_401(self) -> None:
        me = self.client.get("/api/v1/auth/me")
        self.assertEqual(me.status_code, 401)
        self.assertEqual(me.json()["detail"]["code"], "authentication_required")

    def test_me_with_invalid_token_returns_401(self) -> None:
        me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token-here"},
        )
        self.assertEqual(me.status_code, 401)

    def test_me_with_malformed_authorization_header_returns_401(self) -> None:
        me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "NoBearerScheme"},
        )
        self.assertEqual(me.status_code, 401)

    async def test_me_does_not_restrict_by_role(self) -> None:
        # /me acepta cualquier rol logueado.
        from app.db.session import utcnow
        from app.modules.auth.security import hash_password

        async with self.factory() as session:
            from app.db.models.users import User

            from sqlalchemy import delete
            await session.execute(delete(User).where(User.username == "sup"))
            session.add(
                User(
                    id=uuid.uuid4(),
                    username="sup",
                    full_name="Sup",
                    role="supervisor",
                    password_hash=hash_password("demo123"),
                    is_active=True,
                    created_at=utcnow(),
                )
            )
            await session.commit()

        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "sup", "password": "demo123"},
        )
        self.assertEqual(response.status_code, 200)
        token = response.json()["token"]
        me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "supervisor")


if __name__ == "__main__":
    unittest.main()
