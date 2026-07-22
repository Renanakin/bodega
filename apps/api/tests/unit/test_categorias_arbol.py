"""
Tests del endpoint /categories/arbol (Fase 8) — async puro.

Migrado: usa ``DATABASE_URL=sqlite+aiosqlite:///<file>`` + schema async +
seed del admin via AsyncSession. Ya no depende de ``app.state.db`` legacy.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid

from app.core.config import reset_settings_cache
from app.db import models  # noqa: F401  -- importa modelos
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


class _AsyncTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="bodega-arbol-")
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

        factory = get_session_factory()
        async with factory() as session:
            admin = User(
                id=uuid.uuid4(),
                username="admin",
                full_name="Administrador Demo",
                role="admin",
                password_hash=hash_password("demo123"),
                is_active=True,
                created_at=utcnow(),
            )
            session.add(admin)
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


class CategoriasArbolTestCase(_AsyncTestBase):
    # ----------------------------------------------------------------- tests

    async def test_categorias_arbol_devuelve_jerarquia(self) -> None:
        """Crea root + 2 hijos, verifica que el árbol los incluye."""
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

    async def test_categorias_arbol_con_3_niveles(self) -> None:
        """Verifica jerarquía root -> mid -> leaf (3 niveles)."""
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

    async def test_categorias_arbol_oculta_inactivos_por_default(self) -> None:
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
        del_resp = self.client.delete(
            f"/api/v1/categories/{inactive_id}", headers=self.headers
        )
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
