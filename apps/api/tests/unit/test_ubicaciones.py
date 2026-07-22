"""
Tests del módulo de ubicaciones (migrado a Depends(get_session)).

Cubre:
- Crear ubicación simple en una bodega.
- Listar ubicaciones por bodega.
- UNIQUE constraint (mismo slot en la misma bodega) → 409.
- PATCH activar/desactivar.
- Soft delete.
- Bodega inexistente → 404.
- Ubicación inexistente → 404.
"""

from __future__ import annotations

import unittest
import uuid

from fastapi.testclient import TestClient

from tests.unit._async_test_base import AsyncTestBase


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "demo123"},
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _create_warehouse(
    client: TestClient, headers: dict[str, str], name_suffix: str = ""
) -> str:
    code = f"W-{uuid.uuid4().hex[:6].upper()}"
    resp = client.post(
        "/api/v1/warehouses",
        json={"code": code, "name": f"Test WH{name_suffix}", "warehouse_type": "principal"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class UbicacionesTestCase(AsyncTestBase, unittest.IsolatedAsyncioTestCase):
    def test_create_and_list_ubicacion(self) -> None:
        bodega_id = _create_warehouse(self.client, self.headers, name_suffix="-A")
        create_resp = self.client.post(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            json={"pasillo": 1, "estanteria": 2, "altura": 1},
            headers=self.headers,
        )
        self.assertEqual(create_resp.status_code, 201)
        payload = create_resp.json()
        self.assertEqual(payload["pasillo"], 1)
        self.assertEqual(payload["estanteria"], 2)
        self.assertEqual(payload["altura"], 1)
        self.assertTrue(payload["is_active"])

        list_resp = self.client.get(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            headers=self.headers,
        )
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()), 1)

    def test_unique_constraint_same_slot(self) -> None:
        bodega_id = _create_warehouse(self.client, self.headers, name_suffix="-A")
        payload = {"pasillo": 3, "estanteria": 4, "altura": 2}
        first = self.client.post(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["detail"]["code"], "duplicate_ubicacion")

    def test_same_slot_different_bodega_is_ok(self) -> None:
        bodega_id = _create_warehouse(self.client, self.headers, name_suffix="-A")
        other_bodega = _create_warehouse(self.client, self.headers, name_suffix="-B")
        payload = {"pasillo": 5, "estanteria": 5, "altura": 1}

        r1 = self.client.post(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            json=payload,
            headers=self.headers,
        )
        r2 = self.client.post(
            f"/api/v1/bodegas/{other_bodega}/ubicaciones",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.json()["id"], r2.json()["id"])

    def test_bodega_not_found(self) -> None:
        resp = self.client.get(
            f"/api/v1/bodegas/{uuid.uuid4()}/ubicaciones",
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 404)

        post_resp = self.client.post(
            f"/api/v1/bodegas/{uuid.uuid4()}/ubicaciones",
            json={"pasillo": 1, "estanteria": 1, "altura": 1},
            headers=self.headers,
        )
        self.assertEqual(post_resp.status_code, 404)

    def test_ubicacion_not_found(self) -> None:
        resp = self.client.get(
            f"/api/v1/ubicaciones/{uuid.uuid4()}", headers=self.headers
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["code"], "ubicacion_not_found")

    def test_patch_activar_desactivar(self) -> None:
        bodega_id = _create_warehouse(self.client, self.headers, name_suffix="-A")
        ub_id = self.client.post(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            json={"pasillo": 7, "estanteria": 1, "altura": 1},
            headers=self.headers,
        ).json()["id"]

        # Desactivar
        resp = self.client.patch(
            f"/api/v1/ubicaciones/{ub_id}",
            json={"is_active": False},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_active"])

        # Reactivar con descripcion nueva
        resp2 = self.client.patch(
            f"/api/v1/ubicaciones/{ub_id}",
            json={"is_active": True, "descripcion": "Estantería de picking"},
            headers=self.headers,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(resp2.json()["is_active"])
        self.assertEqual(resp2.json()["descripcion"], "Estantería de picking")

    def test_soft_delete(self) -> None:
        bodega_id = _create_warehouse(self.client, self.headers, name_suffix="-A")
        ub_id = self.client.post(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            json={"pasillo": 8, "estanteria": 1, "altura": 1},
            headers=self.headers,
        ).json()["id"]

        delete_resp = self.client.delete(
            f"/api/v1/ubicaciones/{ub_id}", headers=self.headers
        )
        self.assertEqual(delete_resp.status_code, 204)

        # Detalle sigue accesible pero is_active=False
        detail = self.client.get(
            f"/api/v1/ubicaciones/{ub_id}", headers=self.headers
        ).json()
        self.assertFalse(detail["is_active"])

        # Listado sigue mostrando la fila (no se borra)
        listed = self.client.get(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            headers=self.headers,
        ).json()
        self.assertEqual(len(listed), 1)

    def test_validacion_positivos(self) -> None:
        bodega_id = _create_warehouse(self.client, self.headers, name_suffix="-A")
        # pasillo=0 debe fallar con 422 (Pydantic)
        resp = self.client.post(
            f"/api/v1/bodegas/{bodega_id}/ubicaciones",
            json={"pasillo": 0, "estanteria": 1, "altura": 1},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
