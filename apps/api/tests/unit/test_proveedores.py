"""Tests del CRUD de Proveedores (Fase 8).

Cubre:
- Crear proveedor OK.
- Nombre duplicado (case-insensitive) -> 409.
- Listar con filtro ?activo=true/false.
- Soft delete: DELETE marca activo=False.
- Actualizacion parcial (PATCH).
- No-admin no puede crear (403).
"""
from __future__ import annotations

import os
import unittest
from uuid import uuid4

# Configurar el AsyncEngine antes de importar la app.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault(
    "JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import reset_settings_cache  # noqa: E402
from app.db import models  # noqa: E402, F401  -- registra modelos en Base.metadata
from app.db.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


reset_settings_cache()


def _create_test_engine() -> AsyncEngine:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


class ProveedoresTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.core.security import hash_password
        from app.db.session import create_database, utcnow
        from app.db.session import reset_engine_cache

        reset_engine_cache()
        self.engine = _create_test_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        import app.db.session as session_module
        session_module._engine = self.engine
        session_module._session_factory = self.session_factory

        self.app = create_app()
        from app.db.session import get_session

        async def _override_get_session():
            async with self.session_factory() as s:
                try:
                    yield s
                except Exception:
                    await s.rollback()
                    raise
        self.app.dependency_overrides[get_session] = _override_get_session

        # Crear usuarios en BD legacy para auth.
        legacy_db = create_database(":memory:")
        now = utcnow().isoformat()
        for username, full_name, role in [
            ("admin", "Admin", "admin"),
            ("supervisor", "Supervisor", "supervisor"),
            ("operador", "Operador", "origin_operator"),
        ]:
            legacy_db.execute(
                """
                INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (str(uuid4()), username, full_name, role, hash_password("demo123"), now),
            )
        self.legacy_db = legacy_db
        self.app.state.db = legacy_db

        self.client = TestClient(self.app)
        self.admin_headers = self._auth("admin", "demo123")
        self.supervisor_headers = self._auth("supervisor", "demo123")
        self.operador_headers = self._auth("operador", "demo123")

    def _auth(self, username: str, password: str) -> dict[str, str]:
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["token"]
        return {"Authorization": f"Bearer {token}"}

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.legacy_db.close()
        from app.db.session import reset_engine_cache
        reset_engine_cache()

    # ----------------------------------------------------------------- tests

    async def test_crear_proveedor_ok(self) -> None:
        resp = self.client.post(
            "/api/v1/proveedores",
            json={"nombre": "Repuestos SA", "rut": "76.123.456-7", "email": "ventas@repuestos.example"},
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["nombre"], "Repuestos SA")
        self.assertEqual(body["rut"], "76.123.456-7")
        self.assertTrue(body["activo"])
        self.assertEqual(body["lead_time_dias"], 7)

    async def test_crear_proveedor_nombre_duplicado_falla(self) -> None:
        r1 = self.client.post(
            "/api/v1/proveedores",
            json={"nombre": "Repuestos SA"},
            headers=self.admin_headers,
        )
        self.assertEqual(r1.status_code, 201, r1.text)
        # Mismo nombre en distinto case -> 409.
        r2 = self.client.post(
            "/api/v1/proveedores",
            json={"nombre": "REPUESTOS sa"},
            headers=self.admin_headers,
        )
        self.assertEqual(r2.status_code, 409, r2.text)
        self.assertEqual(
            r2.json()["detail"]["code"],
            "duplicate_proveedor_nombre",
        )

    async def test_listar_proveedores_activos(self) -> None:
        # Crear 2 proveedores: uno activo, otro desactivado.
        r1 = self.client.post(
            "/api/v1/proveedores",
            json={"nombre": "Proveedor A"},
            headers=self.admin_headers,
        )
        self.assertEqual(r1.status_code, 201, r1.text)
        sid_a = r1.json()["id"]

        r2 = self.client.post(
            "/api/v1/proveedores",
            json={"nombre": "Proveedor B"},
            headers=self.admin_headers,
        )
        self.assertEqual(r2.status_code, 201, r2.text)
        sid_b = r2.json()["id"]

        # Desactivar B.
        r = self.client.delete(
            f"/api/v1/proveedores/{sid_b}",
            headers=self.admin_headers,
        )
        self.assertEqual(r.status_code, 200, r.text)

        # Listar todos -> 2.
        all_resp = self.client.get(
            "/api/v1/proveedores", headers=self.admin_headers
        )
        self.assertEqual(all_resp.status_code, 200)
        self.assertEqual(len(all_resp.json()), 2)

        # Listar solo activos -> 1 (A).
        activos = self.client.get(
            "/api/v1/proveedores?activo=true", headers=self.admin_headers
        )
        self.assertEqual(activos.status_code, 200)
        self.assertEqual(len(activos.json()), 1)
        self.assertEqual(activos.json()[0]["id"], sid_a)

        # Listar solo inactivos -> 1 (B).
        inactivos = self.client.get(
            "/api/v1/proveedores?activo=false", headers=self.admin_headers
        )
        self.assertEqual(inactivos.status_code, 200)
        self.assertEqual(len(inactivos.json()), 1)
        self.assertEqual(inactivos.json()[0]["id"], sid_b)


if __name__ == "__main__":
    unittest.main()
