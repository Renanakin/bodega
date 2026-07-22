"""
Tests del sub-recurso ``detalles_neumaticos`` (migrado a Depends(get_session)).

Cubre:
- GET 404 si no hay detalle.
- PUT upsert (crea o actualiza).
- DELETE 404 si no existe.
- DELETE 404 si el producto no existe.
- Relación 1:1: segundo PUT sobre mismo producto actualiza, no duplica.

Migrado: usa ``DATABASE_URL=sqlite+aiosqlite:///<archivo>`` + schema async
+ seed del admin via AsyncSession. Ya no depende de ``app.state.db`` legacy.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid

from app.core.config import reset_settings_cache
from app.db import models  # noqa: F401
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


def _auth_headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "demo123"},
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _create_product(client: TestClient, headers: dict[str, str], sku: str) -> str:
    r = client.post(
        "/api/v1/products",
        json={"sku": sku, "name": sku, "unit": "unidad"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class _AsyncTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="bodega-ext-")
        self._db_path = os.path.join(self._tmpdir, "test.db")
        db_url = f"sqlite+aiosqlite:///{self._db_path}"

        self._saved_env: dict[str, str | None] = {}
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

        factory = get_session_factory()
        async with factory() as session:
            session.add(
                User(
                    id=uuid.uuid4(),
                    username="admin",
                    full_name="Admin",
                    role="admin",
                    password_hash=hash_password("demo123"),
                    is_active=True,
                    created_at=utcnow(),
                )
            )
            await session.commit()

        self.headers = _auth_headers(self.client)

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


class ProductExtensionTestCase(_AsyncTestBase):
    def test_get_404_sin_detalle(self) -> None:
        prod = _create_product(self.client, self.headers, "N-001")
        r = self.client.get(f"/api/v1/products/{prod}/neumatico", headers=self.headers)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "detalle_neumatico_not_found")

    def test_upsert_y_get(self) -> None:
        prod = _create_product(self.client, self.headers, "N-002")

        put_resp = self.client.put(
            f"/api/v1/products/{prod}/neumatico",
            json={
                "ancho": 205,
                "perfil": 55,
                "aro": 16,
                "indice_carga": 91,
                "indice_velocidad": "V",
                "dot": "2024-12-01",
            },
            headers=self.headers,
        )
        self.assertEqual(put_resp.status_code, 200)
        body = put_resp.json()
        self.assertEqual(body["ancho"], 205)
        self.assertEqual(body["perfil"], 55)
        self.assertEqual(body["aro"], 16)
        self.assertEqual(body["indice_carga"], 91)
        self.assertEqual(body["indice_velocidad"], "V")
        self.assertEqual(body["dot"], "2024-12-01")
        self.assertEqual(body["producto_id"], prod)

        get_resp = self.client.get(f"/api/v1/products/{prod}/neumatico", headers=self.headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["ancho"], 205)

    def test_upsert_idempotente_actualiza(self) -> None:
        prod = _create_product(self.client, self.headers, "N-003")
        payload_v1 = {"ancho": 195, "perfil": 65, "aro": 15}
        payload_v2 = {
            "ancho": 205,
            "perfil": 55,
            "aro": 16,
            "indice_carga": 91,
        }

        r1 = self.client.put(
            f"/api/v1/products/{prod}/neumatico",
            json=payload_v1,
            headers=self.headers,
        )
        self.assertEqual(r1.status_code, 200)

        # Misma PK → UPDATE, no INSERT
        r2 = self.client.put(
            f"/api/v1/products/{prod}/neumatico",
            json=payload_v2,
            headers=self.headers,
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["ancho"], 205)

        # Sigue siendo 1 fila
        get_resp = self.client.get(f"/api/v1/products/{prod}/neumatico", headers=self.headers)
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["ancho"], 205)

    def test_delete_404_sin_detalle(self) -> None:
        prod = _create_product(self.client, self.headers, "N-004")
        r = self.client.delete(f"/api/v1/products/{prod}/neumatico", headers=self.headers)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "detalle_neumatico_not_found")

    def test_delete_ok(self) -> None:
        prod = _create_product(self.client, self.headers, "N-005")
        self.client.put(
            f"/api/v1/products/{prod}/neumatico",
            json={"ancho": 195, "perfil": 65, "aro": 15},
            headers=self.headers,
        )

        del_resp = self.client.delete(f"/api/v1/products/{prod}/neumatico", headers=self.headers)
        self.assertEqual(del_resp.status_code, 204)

        # GET ahora debe devolver 404
        get_resp = self.client.get(f"/api/v1/products/{prod}/neumatico", headers=self.headers)
        self.assertEqual(get_resp.status_code, 404)

    def test_product_not_found_en_upsert(self) -> None:
        r = self.client.put(
            f"/api/v1/products/{uuid.uuid4()}/neumatico",
            json={"ancho": 195, "perfil": 65, "aro": 15},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["detail"]["code"], "product_not_found")


if __name__ == "__main__":
    unittest.main()
