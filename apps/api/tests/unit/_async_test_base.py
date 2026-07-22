"""
Helper compartido para tests de módulos migrados a ``Depends(get_session)``.

Este módulo provee ``AsyncTestBase``, una clase base para
``unittest.IsolatedAsyncioTestCase`` que:

- Setea ``DATABASE_URL=sqlite+aiosqlite:///<archivo temporal>``
  antes de instanciar la app.
- Resetea caches (``reset_settings_cache()``, ``reset_engine_cache()``).
- Crea el schema async via ``Base.metadata.create_all``.
- Siembra el admin (``username=admin``, ``password=demo123``) via
  AsyncSession para que los tests puedan loguearse.
- Crea el ``TestClient`` y los ``admin_headers`` con Bearer token.

Uso::

    from tests.unit._async_test_base import AsyncTestBase

    class MyTestCase(AsyncTestBase):
        async def test_x(self) -> None:
            resp = self.client.get("/api/v1/...")
            ...

Notas:
- Usar archivo temporal (no ``:memory:``) es necesario para que
  ``app.create_app()`` (que crea su propio engine desde
  ``settings.database_url``) y la sesión del test apunten al MISMO
  archivo. Con ``:memory:`` cada llamada crearía un engine con su
  propia conexión privada.
- El ``AsyncTestBase`` siembra SOLO el admin. Tests que necesiten más
  usuarios / datos pueden hacer ``self.client.post(...)`` después
  del setUp, o usar ``self.factory`` (session factory) para inserts
  directos via SQLAlchemy ORM.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from typing import Any

from app.core.config import reset_settings_cache
from app.db import models  # noqa: F401  -- importa modelos para Base.metadata
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


class AsyncTestBase:
    """Mixin para IsolatedAsyncioTestCase. NO usar unittest.TestCase.

    Requiere que la clase hija herede de
    ``unittest.IsolatedAsyncioTestCase`` además de este mixin.
    """

    _tmpdir: str
    _db_path: str
    _saved_env: dict[str, str | None]
    app: Any
    client: TestClient
    headers: dict[str, str]
    factory: Any

    async def asyncSetUp(self) -> None:
        # C5.2: resetear el rate limiter para que tests no se contaminen
        # entre si (el limiter es un singleton del modulo).
        try:
            from app.core.rate_limit import reset_rate_limiter_for_tests
            reset_rate_limiter_for_tests()
        except Exception:
            pass

        self._tmpdir = tempfile.mkdtemp(prefix="bodega-async-test-")
        self._db_path = os.path.join(self._tmpdir, "test.db")
        db_url = f"sqlite+aiosqlite:///{self._db_path}"

        self._saved_env = {}
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

        self.factory = get_session_factory()
        async with self.factory() as session:
            session.add(
                User(
                    id=uuid.uuid4(),
                    username="admin",
                    full_name="Administrador Demo",
                    role="admin",
                    password_hash=hash_password("demo123"),
                    is_active=True,
                    created_at=utcnow(),
                )
            )
            await session.commit()

        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "demo123"},
        )
        self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}

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

    async def seed_user(
        self,
        username: str,
        full_name: str,
        role: str,
    ) -> User:
        """Helper para sembrar usuarios adicionales via AsyncSession."""
        async with self.factory() as session:
            user = User(
                id=uuid.uuid4(),
                username=username,
                full_name=full_name,
                role=role,
                password_hash=hash_password("demo123"),
                is_active=True,
                created_at=utcnow(),
            )
            session.add(user)
            await session.commit()
        return user

    def login_as(self, username: str) -> dict[str, str]:
        """Hace login y retorna headers con Bearer token."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": "demo123"},
        )
        return {"Authorization": f"Bearer {resp.json()['token']}"}
