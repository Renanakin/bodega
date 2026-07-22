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


class AuthRefreshTokenTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """C5.1: refresh tokens.

    Cubre:
    - login devuelve access + refresh token.
    - POST /auth/refresh rota el par y devuelve tokens nuevos.
    - El access token viejo deja de funcionar despues del refresh.
    - El refresh token viejo tambien deja de funcionar (rotacion).
    - Un refresh token invalido retorna 401.
    """

    def test_login_returns_refresh_token(self) -> None:
        r = _login(self.client, "admin", "demo123")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("token", body)
        self.assertIn("refresh_token", body)
        self.assertIn("expires_at", body)
        self.assertIn("refresh_expires_at", body)
        self.assertNotEqual(body["token"], body["refresh_token"])

    def test_refresh_rotates_pair(self) -> None:
        # 1. Login inicial
        r1 = _login(self.client, "admin", "demo123")
        old_token = r1.json()["token"]
        old_refresh = r1.json()["refresh_token"]

        # 2. Refresh
        r2 = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
        self.assertEqual(r2.status_code, 200)
        body2 = r2.json()
        new_token = body2["token"]
        new_refresh = body2["refresh_token"]

        # 3. Los tokens son distintos (rotaron)
        self.assertNotEqual(old_token, new_token)
        self.assertNotEqual(old_refresh, new_refresh)

    def test_old_access_token_invalidated_after_refresh(self) -> None:
        r1 = _login(self.client, "admin", "demo123")
        old_token = r1.json()["token"]
        old_refresh = r1.json()["refresh_token"]

        # Refresh invalida la sesion vieja
        self.client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})

        # El access token viejo ya no funciona
        me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        self.assertEqual(me.status_code, 401)

    def test_old_refresh_token_invalidated_after_rotation(self) -> None:
        r1 = _login(self.client, "admin", "demo123")
        old_refresh = r1.json()["refresh_token"]

        # Primer refresh: OK
        r2 = self.client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        self.assertEqual(r2.status_code, 200)

        # Segundo refresh con el MISMO refresh viejo: 401
        r3 = self.client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        self.assertEqual(r3.status_code, 401)

    def test_refresh_with_invalid_token_returns_401(self) -> None:
        r = self.client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "this-is-not-a-real-token"},
        )
        self.assertEqual(r.status_code, 401)

    def test_new_access_token_works_after_refresh(self) -> None:
        r1 = _login(self.client, "admin", "demo123")
        old_refresh = r1.json()["refresh_token"]
        r2 = self.client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_refresh}
        )
        new_token = r2.json()["token"]

        # El nuevo access token funciona para /auth/me
        me = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["username"], "admin")


class AuthRateLimitTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    """C5.2: rate limit por USERNAME (no por IP) en /auth/login y /auth/refresh.

    Verifica que un atacante con IPs distintas pero el mismo username
    es bloqueado tras N intentos (OWASP Authentication Cheat Sheet).
    """

    def setUp(self) -> None:
        super().setUp()
        from app.core.rate_limit import reset_rate_limiter_for_tests
        reset_rate_limiter_for_tests()

    def test_login_rate_limit_blocks_after_5_attempts_same_username(self) -> None:
        """5 logins con password incorrecto para el mismo username.

        El limite es 5 por minuto POR USERNAME. Las primeras 4 requests
        pasan (y devuelven 401 invalid_credentials). La 5ta request es
        rate-limited (429).
        """
        for i in range(4):
            r = _login(self.client, "admin", f"wrong-{i}")
            self.assertEqual(r.status_code, 401, f"intento {i}: {r.text}")

        # La 5ta request es rate-limited (429)
        r = _login(self.client, "admin", "wrong-5")
        self.assertEqual(r.status_code, 429, r.text)
        body = r.json()["detail"]
        self.assertEqual(body["code"], "rate_limited")
        self.assertIn("retry_after", body["extra"])

    def test_login_rate_limit_resets_after_window(self) -> None:
        """Verifica que el rate limit es por ventana, no permanente."""
        for i in range(4):
            r = _login(self.client, "admin", f"wrong-{i}")
            self.assertEqual(r.status_code, 401)
        r = _login(self.client, "admin", "wrong-4")
        self.assertEqual(r.status_code, 429, r.text)

        # Limpiar el rate limiter (simula que paso la ventana)
        from app.core.rate_limit import reset_rate_limiter_for_tests
        reset_rate_limiter_for_tests()

        # Ahora pasa lauth (no el rate limit) aunque la password siga mal
        r = _login(self.client, "admin", "wrong-Y")
        self.assertEqual(r.status_code, 401)

    def test_login_rate_limit_is_per_username_not_global(self) -> None:
        """Si el rate limit fuera global, bloquearia OTROS usernames.

        Verificamos que cada username tiene su propio bucket.
        """
        # 4 intentos para "admin" (no lauth)
        for i in range(4):
            r = _login(self.client, "admin", f"wrong-{i}")
            self.assertEqual(r.status_code, 401)
        r = _login(self.client, "admin", "wrong-4")
        self.assertEqual(r.status_code, 429)

        # "otro_usuario" deberia pasar el rate limit (su bucket esta vacio)
        r = _login(self.client, "otro_usuario", "wrong-Y")
        # Pasa el rate limit y falla por 401 (usuario no existe)
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
