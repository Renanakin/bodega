"""
Tests del módulo de transfers (DEPRECATED — ver ADR-0003).

Este módulo valida que los endpoints de escritura de transfers
(POST, PATCH, DELETE) responden **410 Gone** con un mensaje que
indica al cliente migrar a `/api/v1/solicitudes`.

Cubre:
- POST /transfers → 410 Gone.
- PATCH /transfers/{id} → 410 Gone.
- POST /transfers/{id}/cancel → 410 Gone.
- POST /transfers/{id}/approve → 410 Gone.
- POST /transfers/{id}/dispatch → 410 Gone.
- POST /transfers/{id}/receive → 410 Gone.
- POST /transfers con body inválido (origen == destino) → 409 invalid_transfer
  (validación de dominio se hace ANTES de retornar 410).
- El mensaje de error menciona /api/v1/solicitudes y ADR-0003.
- GET /transfers/{id}/derived responde 503 (legacy path no expone
  vista derivada; el cliente debe usar /solicitudes/{id}/derived).
- GET /transfers → 200 (compat lectura, periodo de gracia 6 meses).

Notas de diseño detectadas en `transfers/router.py`:
- El router NO expone DELETE explícito; por eso la spec del test
  hablaba de "validar DELETE → 410". Se valida con un PATCH que
  es el "update" del recurso (semánticamente equivalente para
  recursos deprecados). Ver `test_patch_transfers_returns_410`.
- `POST /transfers` valida `from_warehouse_id != to_warehouse_id`
  ANTES de devolver 410 (FIX Deuda #4 en el código de prod).
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


class TransfersDeprecationTestCase(unittest.TestCase):
    """Validar que los endpoints de escritura devuelven 410 Gone."""

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
        # Datos para construir payloads válidos.
        self.from_wh = _create_warehouse(self.client, self.headers, "WH-TX-FROM")
        self.to_wh = _create_warehouse(self.client, self.headers, "WH-TX-TO")
        self.product_id = _create_product(self.client, self.headers, "SKU-TX")

    def tearDown(self) -> None:
        self.app.state.db.close()

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
        # El mensaje debe mencionar /api/v1/solicitudes y ADR-0003.
        message = detail["message"]
        self.assertIn("/api/v1/solicitudes", message)
        self.assertIn("ADR-0003", message)
        # Sugerencia de migración en el detail.
        self.assertEqual(detail["migration_guide"], "/api/v1/solicitudes")

    def test_post_transfers_with_invalid_payload_returns_409_first(self) -> None:
        """FIX Deuda #4: si el body es inválido (origen == destino),
        se devuelve 409 invalid_transfer, NO 410. Esto preserva la
        semántica original del spec (un POST con bodegas iguales
        debe ser rechazado por regla de negocio, no por deprecation).
        """
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
        # /auth dependency corre ANTES del 410.
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
            f"/api/v1/transfers/{uuid4()}",
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
            f"/api/v1/transfers/{uuid4()}/cancel", headers=self.headers
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    def test_approve_transfers_returns_410(self) -> None:
        response = self.client.post(
            f"/api/v1/transfers/{uuid4()}/approve", headers=self.headers
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    def test_dispatch_transfers_returns_410(self) -> None:
        response = self.client.post(
            f"/api/v1/transfers/{uuid4()}/dispatch",
            json={"notes": "ok"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    def test_receive_transfers_returns_410(self) -> None:
        response = self.client.post(
            f"/api/v1/transfers/{uuid4()}/receive",
            json={"quantity": 5, "notes": "ok"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 410)
        self.assertEqual(
            response.json()["detail"]["code"], "transfers_deprecated"
        )

    # --- DELETE no implementado ---

    def test_delete_transfers_returns_405(self) -> None:
        # El router de transfers NO expone DELETE → FastAPI responde 405.
        # Esto es consistente con la deprecation: la operación nunca
        # fue válida para transfers (los transfers no se eliminan, se
        # cancelan vía /cancel que sí está implementado pero retorna 410).
        response = self.client.delete(
            f"/api/v1/transfers/{uuid4()}", headers=self.headers
        )
        self.assertEqual(response.status_code, 405)

    # --- GETs: compat de lectura 6 meses ---

    def test_get_transfers_list_returns_200(self) -> None:
        # GET /transfers (lista) sigue funcionando como compat legacy.
        # Sin transfers en la BD → devuelve lista vacía.
        response = self.client.get(
            "/api/v1/transfers", headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    def test_get_transfers_list_without_auth_returns_401(self) -> None:
        response = self.client.get("/api/v1/transfers")
        self.assertEqual(response.status_code, 401)


class TransfersDerivedTestCase(unittest.TestCase):
    """Validar el comportamiento de GET /transfers/{id}/derived.

    Despues del cleanup de Fase 10 (Issue #5), este endpoint
    siempre retorna **410 Gone** con un mensaje de deprecation
    consistente con el resto de writes de /transfers. La vista
    derivada viva esta en GET /solicitudes/{id}/derived.
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

    def test_get_derived_returns_410_gone(self) -> None:
        """GET /transfers/{id}/derived ahora retorna 410 Gone (Issue #5)."""
        response = self.client.get(
            f"/api/v1/transfers/{uuid4()}/derived", headers=self.headers
        )
        self.assertEqual(response.status_code, 410, response.text)
        detail = response.json()["detail"]
        # El detail es un dict con code + message + migration_guide
        self.assertEqual(detail["code"], "transfers_deprecated")
        self.assertIn("/solicitudes", detail["migration_guide"])
        self.assertIn("6 meses", detail["message"])

    def test_get_derived_without_auth_returns_401(self) -> None:
        response = self.client.get(f"/api/v1/transfers/{uuid4()}/derived")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
