"""Tests del endpoint /categories/arbol (Fase 8).

Cubre:
- El endpoint devuelve la jerarquia completa como arbol anidado.
- Jerarquia de 3 niveles (root -> mid -> leaf) se serializa correctamente.
- Los nodos inactivos se ocultan por default.
- Los conteos (subcategorias_count, productos_count) son correctos.
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


class CategoriasArbolTestCase(unittest.TestCase):
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

    # ----------------------------------------------------------------- tests

    def test_categorias_arbol_devuelve_jerarquia(self) -> None:
        """Crea root + 2 hijos, verifica que el arbol los incluye."""
        root_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Repuestos"},
            headers=self.headers,
        ).json()["id"]
        self.client.post(
            "/api/v1/categories",
            json={"nombre": "Motor", "parent_id": root_id},
            headers=self.headers,
        )
        self.client.post(
            "/api/v1/categories",
            json={"nombre": "Frenos", "parent_id": root_id},
            headers=self.headers,
        )

        resp = self.client.get("/api/v1/categories/arbol", headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        tree = resp.json()
        self.assertEqual(len(tree), 1, "deberia haber 1 nodo raiz")
        root = tree[0]
        self.assertEqual(root["nombre"], "Repuestos")
        self.assertEqual(len(root["children"]), 2, "root deberia tener 2 hijos")
        nombres_hijos = sorted(c["nombre"] for c in root["children"])
        self.assertEqual(nombres_hijos, ["Frenos", "Motor"])
        # Conteos.
        self.assertEqual(root["subcategorias_count"], 2)
        for child in root["children"]:
            self.assertEqual(child["subcategorias_count"], 0)
            self.assertEqual(child["productos_count"], 0)

    def test_categorias_arbol_con_3_niveles(self) -> None:
        """Verifica jerarquia root -> mid -> leaf (3 niveles)."""
        root_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Vehiculos"},
            headers=self.headers,
        ).json()["id"]
        mid_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Neumaticos", "parent_id": root_id},
            headers=self.headers,
        ).json()["id"]
        leaf_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Auto", "parent_id": mid_id},
            headers=self.headers,
        ).json()["id"]
        # Hoja extra de mid para confirmar que subcategorias_count es 2.
        self.client.post(
            "/api/v1/categories",
            json={"nombre": "Moto", "parent_id": mid_id},
            headers=self.headers,
        )

        resp = self.client.get("/api/v1/categories/arbol", headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        tree = resp.json()
        # Nivel 1: 1 root.
        self.assertEqual(len(tree), 1)
        root = tree[0]
        # Nivel 2: 1 hijo (Neumaticos).
        self.assertEqual(len(root["children"]), 1)
        mid = root["children"][0]
        self.assertEqual(mid["id"], mid_id)
        self.assertEqual(mid["subcategorias_count"], 2)
        # Nivel 3: 2 nietos.
        self.assertEqual(len(mid["children"]), 2)
        leaf_ids = sorted(c["id"] for c in mid["children"])
        self.assertIn(leaf_id, leaf_ids)
        nombres_hojas = sorted(c["nombre"] for c in mid["children"])
        self.assertEqual(nombres_hojas, ["Auto", "Moto"])
        # Las hojas no tienen hijos.
        for leaf in mid["children"]:
            self.assertEqual(len(leaf["children"]), 0)
            self.assertEqual(leaf["subcategorias_count"], 0)

    def test_categorias_arbol_oculta_inactivos_por_default(self) -> None:
        """Con solo_activos=true (default), los nodos is_active=False no aparecen."""
        self.client.post(
            "/api/v1/categories",
            json={"nombre": "Activo"},
            headers=self.headers,
        ).json()["id"]
        inactive_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Inactivo"},
            headers=self.headers,
        ).json()["id"]
        # Soft-delete "Inactivo".
        del_resp = self.client.delete(f"/api/v1/categories/{inactive_id}", headers=self.headers)
        self.assertEqual(del_resp.status_code, 204, del_resp.text)

        # Default: solo_activos=True. Solo "Activo" aparece.
        resp = self.client.get("/api/v1/categories/arbol", headers=self.headers)
        self.assertEqual(resp.status_code, 200, resp.text)
        tree = resp.json()
        nombres = [n["nombre"] for n in tree]
        self.assertIn("Activo", nombres)
        self.assertNotIn("Inactivo", nombres)

        # Con solo_activos=false aparecen ambos.
        resp_all = self.client.get(
            "/api/v1/categories/arbol?solo_activos=false", headers=self.headers
        )
        self.assertEqual(resp_all.status_code, 200, resp_all.text)
        tree_all = resp_all.json()
        nombres_all = [n["nombre"] for n in tree_all]
        self.assertIn("Activo", nombres_all)
        self.assertIn("Inactivo", nombres_all)


if __name__ == "__main__":
    unittest.main()
