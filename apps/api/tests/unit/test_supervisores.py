"""Tests del CRUD de Supervisores (Fase 6).

Cubre:
- Crear supervisor OK.
- Email duplicado falla con 409.
- Email invalido (Pydantic) falla con 422.
- Listar con filtro ?activo=true/false.
- Actualizar nombre OK.
- Soft delete (DELETE) marca activo=False.
"""

from __future__ import annotations

import os
import unittest
from uuid import uuid4

# Configurar el AsyncEngine antes de importar la app
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.config import reset_settings_cache  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

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


class SupervisoresTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from app.core.security import hash_password
        from app.db.session import create_database, reset_engine_cache, utcnow

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

        # Crear usuarios en BD legacy para auth
        legacy_db = create_database(":memory:")
        now = utcnow().isoformat()
        self.admin_id = str(uuid4())
        self.supervisor_id = str(uuid4())
        self.operador_id = str(uuid4())
        for uid, username, full_name, role in [
            (self.admin_id, "admin", "Admin", "admin"),
            (self.supervisor_id, "supervisor", "Supervisor", "supervisor"),
            (self.operador_id, "operador", "Operador", "origin_operator"),
        ]:
            legacy_db.execute(
                """
                INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (uid, username, full_name, role, hash_password("demo123"), now),
            )
        self.legacy_db = legacy_db
        self.app.state.db = legacy_db

        self.client = TestClient(self.app)
        self.admin_headers = _auth_headers(self.client, "admin", "demo123")
        self.supervisor_headers = _auth_headers(self.client, "supervisor", "demo123")
        self.operador_headers = _auth_headers(self.client, "operador", "demo123")

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.legacy_db.close()
        from app.db.session import reset_engine_cache

        reset_engine_cache()

    # 1. Crear OK
    async def test_crear_supervisor_ok(self) -> None:
        resp = self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "Juan Perez", "email": "juan@bodega.example"},
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()
        self.assertEqual(body["nombre"], "Juan Perez")
        self.assertEqual(body["email"], "juan@bodega.example")
        self.assertTrue(body["activo"])

    # 2. Email duplicado falla con 409
    async def test_crear_supervisor_email_duplicado_falla(self) -> None:
        self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "Juan", "email": "dup@bodega.example"},
            headers=self.admin_headers,
        )
        resp = self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "Pedro", "email": "dup@bodega.example"},
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["code"], "duplicate_supervisor_email")

    # 3. Email invalido (Pydantic) falla con 422
    async def test_crear_supervisor_email_invalido_falla(self) -> None:
        resp = self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "X", "email": "esto-no-es-email"},
            headers=self.admin_headers,
        )
        self.assertEqual(resp.status_code, 422)

    # 4. Listar con filtro ?activo=true
    async def test_listar_supervisores_con_filtro_activo(self) -> None:
        # Crear 2 supervisores: uno activo, otro desactivado
        r1 = self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "A", "email": "a@bodega.example"},
            headers=self.admin_headers,
        )
        self.assertEqual(r1.status_code, 201, r1.text)
        sid_a = r1.json()["id"]

        r2 = self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "B", "email": "b@bodega.example"},
            headers=self.admin_headers,
        )
        self.assertEqual(r2.status_code, 201, r2.text)
        sid_b = r2.json()["id"]

        # Desactivar B
        r = self.client.delete(f"/api/v1/supervisores/{sid_b}", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200, r.text)

        # Listar todos
        all_resp = self.client.get("/api/v1/supervisores", headers=self.admin_headers)
        self.assertEqual(all_resp.status_code, 200)
        self.assertEqual(len(all_resp.json()), 2)

        # Listar solo activos
        activos = self.client.get("/api/v1/supervisores?activo=true", headers=self.admin_headers)
        self.assertEqual(activos.status_code, 200)
        self.assertEqual(len(activos.json()), 1)
        self.assertEqual(activos.json()[0]["id"], sid_a)

        # Listar solo inactivos
        inactivos = self.client.get("/api/v1/supervisores?activo=false", headers=self.admin_headers)
        self.assertEqual(inactivos.status_code, 200)
        self.assertEqual(len(inactivos.json()), 1)
        self.assertEqual(inactivos.json()[0]["id"], sid_b)

    # 5. Actualizar OK
    async def test_actualizar_supervisor_ok(self) -> None:
        r = self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "Original", "email": "x@bodega.example"},
            headers=self.admin_headers,
        )
        sid = r.json()["id"]

        r = self.client.patch(
            f"/api/v1/supervisores/{sid}",
            json={"nombre": "Renombrado", "cargo": "Jefe de turno"},
            headers=self.admin_headers,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["nombre"], "Renombrado")
        self.assertEqual(body["cargo"], "Jefe de turno")
        # email NO se cambio (no se paso)
        self.assertEqual(body["email"], "x@bodega.example")

    # 6. Soft delete: DELETE marca activo=False
    async def test_soft_delete_supervisor_activo_false(self) -> None:
        r = self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "Para Borrar", "email": "borrar@bodega.example"},
            headers=self.admin_headers,
        )
        sid = r.json()["id"]
        self.assertTrue(r.json()["activo"])

        r = self.client.delete(f"/api/v1/supervisores/{sid}", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertFalse(r.json()["activo"])

        # Verificar que sigue existiendo (no se elimino fisicamente)
        r = self.client.get(f"/api/v1/supervisores/{sid}", headers=self.admin_headers)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["activo"])

    # 7. No-admin no puede crear (403)
    async def test_no_admin_no_puede_crear(self) -> None:
        r = self.client.post(
            "/api/v1/supervisores",
            json={"nombre": "X", "email": "x@bodega.example"},
            headers=self.supervisor_headers,
        )
        # Supervisor NO tiene permiso de admin, debe ser 403
        self.assertEqual(r.status_code, 403, r.text)


def _auth_headers(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}
