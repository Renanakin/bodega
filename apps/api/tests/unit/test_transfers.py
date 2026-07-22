"""
Tests del módulo de transfers (DEPRECATED COMPLETO — ver ADR-0003 + Fase 5).

Este módulo valida que TODOS los endpoints de /api/v1/transfers (GET,
POST, PATCH, acciones de workflow) responden **410 Gone** con un mensaje
que indica al cliente migrar a `/api/v1/solicitudes`.

Cubre:
- POST /transfers → 410 Gone (con validación previa de body: origen==destino → 409).
- PATCH /transfers/{id} → 410 Gone.
- POST /transfers/{id}/{cancel,approve,dispatch,receive} → 410 Gone.
- GET /transfers → 410 Gone (cerrado en Fase 5+; antes era 200 con lista vacía).
- GET /transfers/{id} → 410 Gone.
- GET /transfers/{id}/derived → 410 Gone.
- POST /transfers con body inválido (origen == destino) → 409 invalid_transfer.

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


def _create_product(
    client: TestClient, headers: dict[str, str], sku: str
) -> str:
    r = client.post(
        "/api/v1/products",
        json={"sku": sku, "name": sku, "unit": "unidad"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class _AsyncTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="bodega-transfers-")
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
                    full_name="Administrador Demo",
                    role="admin",
                    password_hash=hash_password("demo123"),
                    is_active=True,
                    created_at=utcnow(),
                )
            )
            await session.commit()

        self.headers = _auth_headers(self.client)
        # Datos para construir payloads válidos.
        self.from_wh = _create_warehouse(self.client, self.headers, "WH-TX-FROM")
        self.to_wh = _create_warehouse(self.client, self.headers, "WH-TX-TO")
        self.product_id = _create_product(self.client, self.headers, "SKU-TX")

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


class TransfersDeprecationTestCase(_AsyncTestBase):
    def _valid_payload(self) -> dict:
        return {
            "from_warehouse_id": self.from_wh,
            "to_warehouse_id": self.to_wh,
            "product_id": self.product_id,
            "quantity": 5,
            "priority": "normal",
            "notes": "test",
        }

    # --- POST /transfers ---

    def test_post_transfers_returns_410_gone(self) -> None:
        response = self.client.post(
            "/api/v1/transfers",
            json=self._valid_payload(),
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 410, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "transfers_deprecated")
        message = detail["message"]
        self.assertIn("/api/v1/solicitudes", message)
        self.assertIn("ADR-0003", message)
        self.assertEqual(detail["migration_guide"], "/api/v1/solicitudes")

    def test_post_transfers_with_invalid_payload_returns_409_first(self) -> None:
        """FIX Deuda #4: si el body es inválido (origen == destino),
        se devuelve 409 invalid_transfer, NO 410."""
        bad_payload = self._valid_payload()
        bad_payload["to_warehouse_id"] = bad_payload["from_warehouse_id"]
        response = self.client.post(
            "/api/v1/transfers",
            json=bad_payload,
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "invalid_transfer")

    def test_post_transfers_without_auth_returns_401(self) -> None:
        response = self.client.post(
            "/api/v1/transfers", json=self._valid_payload()
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"]["code"], "authentication_required"
        )

    # --- PATCH /transfers/{id} ---

    def test_patch_transfers_returns_410_gone(self) -> None:
        response = self.client.patch(
            f"/api/v1/transfers/{uuid.uuid4()}",
            json={"quantity": 10, "priority": "high"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 410, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "transfers_deprecated")
        self.assertIn("/api/v1/solicitudes", detail["message"])

    # --- Acciones de workflow (también deprecadas) ---

    def test_cancel_transfers_returns_410(self) -> None:
        response = self.client.post(
            f"/api/v1/transfers/{uuid.uuid4()}/cancel", headers=self.headers
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    def test_approve_transfers_returns_410(self) -> None:
        response = self.client.post(
            f"/api/v1/transfers/{uuid.uuid4()}/approve", headers=self.headers
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    def test_dispatch_transfers_returns_410(self) -> None:
        response = self.client.post(
            f"/api/v1/transfers/{uuid.uuid4()}/dispatch",
            json={"notes": "ok"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    def test_receive_transfers_returns_410(self) -> None:
        response = self.client.post(
            f"/api/v1/transfers/{uuid.uuid4()}/receive",
            json={"quantity": 5, "notes": "ok"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    # --- DELETE no implementado ---

    def test_delete_transfers_returns_405(self) -> None:
        response = self.client.delete(
            f"/api/v1/transfers/{uuid.uuid4()}", headers=self.headers
        )
        self.assertEqual(response.status_code, 405)

    # --- GETs: cerrados en Fase 5+ (retornan 410) ---

    def test_get_transfers_list_returns_410(self) -> None:
        # Antes (Fase 3): GET /transfers retornaba 200 con lista vacía.
        # Ahora (Fase 5+): tambien retorna 410 para forzar la migracion a /solicitudes.
        response = self.client.get(
            "/api/v1/transfers", headers=self.headers
        )
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    def test_get_transfers_list_without_auth_returns_401(self) -> None:
        response = self.client.get("/api/v1/transfers")
        self.assertEqual(response.status_code, 401)

    def test_get_transfer_by_id_returns_410(self) -> None:
        response = self.client.get(
            f"/api/v1/transfers/{uuid.uuid4()}", headers=self.headers
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )


class TransfersDerivedTestCase(_AsyncTestBase):
    """GET /transfers/{id}/derived retorna 410 Gone."""

    def test_get_derived_returns_410_gone(self) -> None:
        response = self.client.get(
            f"/api/v1/transfers/{uuid.uuid4()}/derived", headers=self.headers
        )
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )


if __name__ == "__main__":
    unittest.main()
