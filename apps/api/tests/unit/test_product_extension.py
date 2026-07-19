"""
Tests del sub-recurso ``detalles_neumaticos`` (Fase 2).

Cubre:
- GET 404 si no hay detalle.
- PUT upsert (crea o actualiza).
- DELETE 404 si no existe.
- DELETE 404 si el producto no existe.
- Relación 1:1: segundo PUT sobre mismo producto actualiza, no duplica.
"""
from __future__ import annotations

import unittest
from uuid import uuid4

from app.db.session import utcnow
from app.main import create_app
from app.modules.auth.security import hash_password
from fastapi.testclient import TestClient


def _auth_headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "demo123"},
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _create_user(db) -> None:
    now = utcnow().isoformat()
    db.execute(
        """
        INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (str(uuid4()), "admin", "Admin", "admin", hash_password("demo123"), now),
    )


def _create_product(client: TestClient, headers: dict[str, str], sku: str) -> str:
    r = client.post(
        "/api/v1/products",
        json={"sku": sku, "name": sku, "unit": "unidad"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class ProductExtensionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(db_path=":memory:")
        self.client = TestClient(self.app)
        _create_user(self.app.state.db)
        self.headers = _auth_headers(self.client)

    def tearDown(self) -> None:
        self.app.state.db.close()

    def test_get_404_sin_detalle(self) -> None:
        prod = _create_product(self.client, self.headers, "N-001")
        r = self.client.get(
            f"/api/v1/products/{prod}/neumatico", headers=self.headers
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(
            r.json()["detail"]["code"], "detalle_neumatico_not_found"
        )

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

        get_resp = self.client.get(
            f"/api/v1/products/{prod}/neumatico", headers=self.headers
        )
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
        get_resp = self.client.get(
            f"/api/v1/products/{prod}/neumatico", headers=self.headers
        )
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["ancho"], 205)

    def test_delete_404_sin_detalle(self) -> None:
        prod = _create_product(self.client, self.headers, "N-004")
        r = self.client.delete(
            f"/api/v1/products/{prod}/neumatico", headers=self.headers
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(
            r.json()["detail"]["code"], "detalle_neumatico_not_found"
        )

    def test_delete_ok(self) -> None:
        prod = _create_product(self.client, self.headers, "N-005")
        self.client.put(
            f"/api/v1/products/{prod}/neumatico",
            json={"ancho": 195, "perfil": 65, "aro": 15},
            headers=self.headers,
        )

        del_resp = self.client.delete(
            f"/api/v1/products/{prod}/neumatico", headers=self.headers
        )
        self.assertEqual(del_resp.status_code, 204)

        # GET ahora debe devolver 404
        get_resp = self.client.get(
            f"/api/v1/products/{prod}/neumatico", headers=self.headers
        )
        self.assertEqual(get_resp.status_code, 404)

    def test_product_not_found_en_upsert(self) -> None:
        r = self.client.put(
            f"/api/v1/products/{uuid4()}/neumatico",
            json={"ancho": 195, "perfil": 65, "aro": 15},
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 404)
        self.assertEqual(
            r.json()["detail"]["code"], "product_not_found"
        )


if __name__ == "__main__":
    unittest.main()
