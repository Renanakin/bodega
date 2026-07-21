"""
Tests del módulo de categorías (Fase 2).

Cubre:
- Crear categoría simple.
- Listar con filtro is_active y parent_id.
- Nombre duplicado (case-insensitive) → 409.
- parent_id inexistente → 404.
- PATCH parcial.
- Soft delete (DELETE → is_active=False, no borra fila).
- Referencia circular directa y transitiva → 409.
- Jerarquía de 3 niveles funciona.
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


class CategoriesTestCase(unittest.TestCase):
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

    # --- Tests ---

    def test_create_and_list_category(self) -> None:
        create_resp = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Neumáticos", "descripcion": "Cubiertas y afines"},
            headers=self.headers,
        )
        self.assertEqual(create_resp.status_code, 201)
        payload = create_resp.json()
        self.assertEqual(payload["nombre"], "Neumáticos")
        self.assertTrue(payload["is_active"])
        self.assertIsNone(payload["parent_id"])

        list_resp = self.client.get("/api/v1/categories", headers=self.headers)
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()), 1)

    def test_duplicate_name_is_case_insensitive(self) -> None:
        self.client.post(
            "/api/v1/categories",
            json={"nombre": "Frenos"},
            headers=self.headers,
        )
        resp = self.client.post(
            "/api/v1/categories",
            json={"nombre": "FRENOS"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["code"], "duplicate_category_name")

    def test_parent_id_not_found(self) -> None:
        resp = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Aceites", "parent_id": str(uuid4())},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["code"], "category_not_found")

    def test_hierarchical_categories_three_levels(self) -> None:
        # Nivel 1
        root_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Repuestos"},
            headers=self.headers,
        ).json()["id"]
        # Nivel 2
        mid_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Motor", "parent_id": root_id},
            headers=self.headers,
        ).json()["id"]
        # Nivel 3
        leaf_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Bujías", "parent_id": mid_id},
            headers=self.headers,
        ).json()["id"]

        # Filtro por parent_id
        children_of_root = self.client.get(
            "/api/v1/categories",
            params={"parent_id": root_id},
            headers=self.headers,
        ).json()
        self.assertEqual(len(children_of_root), 1)
        self.assertEqual(children_of_root[0]["nombre"], "Motor")
        self.assertEqual(children_of_root[0]["id"], mid_id)

        # Detalle del nivel 3
        leaf_detail = self.client.get(f"/api/v1/categories/{leaf_id}", headers=self.headers).json()
        self.assertEqual(leaf_detail["parent_id"], mid_id)

    def test_patch_partial(self) -> None:
        cat_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Filtros"},
            headers=self.headers,
        ).json()["id"]

        resp = self.client.patch(
            f"/api/v1/categories/{cat_id}",
            json={"descripcion": "Filtros de aire, aceite y combustible"},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json()["descripcion"],
            "Filtros de aire, aceite y combustible",
        )
        # nombre no se tocó
        self.assertEqual(resp.json()["nombre"], "Filtros")

    def test_soft_delete(self) -> None:
        cat_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Temporal"},
            headers=self.headers,
        ).json()["id"]

        delete_resp = self.client.delete(f"/api/v1/categories/{cat_id}", headers=self.headers)
        self.assertEqual(delete_resp.status_code, 204)

        # Sigue existiendo la fila pero is_active=False
        detail = self.client.get(f"/api/v1/categories/{cat_id}", headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.json()["is_active"])

        # Filtro is_active=true la esconde del listado
        list_active = self.client.get(
            "/api/v1/categories",
            params={"is_active": "true"},
            headers=self.headers,
        ).json()
        self.assertEqual(len(list_active), 0)

    def test_direct_circular_reference(self) -> None:
        cat_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Loop"},
            headers=self.headers,
        ).json()["id"]

        resp = self.client.patch(
            f"/api/v1/categories/{cat_id}",
            json={"parent_id": cat_id},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["code"], "category_circular_reference")

    def test_transitive_circular_reference(self) -> None:
        # A → B → C; intentar hacer A.parent = C crearía ciclo A → C → B → A
        a_id = self.client.post(
            "/api/v1/categories", json={"nombre": "A"}, headers=self.headers
        ).json()["id"]
        b_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "B", "parent_id": a_id},
            headers=self.headers,
        ).json()["id"]
        c_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "C", "parent_id": b_id},
            headers=self.headers,
        ).json()["id"]

        resp = self.client.patch(
            f"/api/v1/categories/{a_id}",
            json={"parent_id": c_id},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["detail"]["code"], "category_circular_reference")

    def test_category_not_found(self) -> None:
        resp = self.client.get(f"/api/v1/categories/{uuid4()}", headers=self.headers)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["code"], "category_not_found")


if __name__ == "__main__":
    unittest.main()
