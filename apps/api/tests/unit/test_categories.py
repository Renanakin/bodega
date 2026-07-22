"""
Tests del módulo de categorías (migrado a async + Depends(get_session)).

Cubre:
- Crear categoría simple.
- Listar con filtro is_active y parent_id.
- Nombre duplicado (case-insensitive) → 409.
- parent_id inexistente → 404.
- PATCH parcial.
- Soft delete (DELETE → is_active=False, no borra fila).
- Referencia circular directa y transitiva → 409.
- Jerarquía de 3 niveles funciona.

Migrado a async: usa ``DATABASE_URL=sqlite+aiosqlite:///:memory:`` + schema
async + seed del admin via AsyncSession. El ``app.state.db`` legacy NO se usa.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid

from app.core.config import reset_settings_cache
from app.db import models  # noqa: F401  -- importa modelos para Base.metadata
from app.db.base import Base
from app.db.models.users import User
from app.db.session import (
    get_session_factory,
    reset_engine_cache,
    utcnow,
)
from app.main import create_app
from app.modules.auth.security import hash_password
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "demo123"},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class CategoriesTestCase(unittest.IsolatedAsyncioTestCase):
    """Tests del módulo categories (migrado a Depends(get_session))."""

    async def asyncSetUp(self) -> None:
        # Usar un archivo temporal compartido (en vez de :memory:) para
        # que ``app.create_app()`` (que crea su propio engine desde
        # ``settings.database_url``) y la sesión del test apunten al
        # MISMO archivo.
        self._tmpdir = tempfile.mkdtemp(prefix="bodega-categories-")
        self._db_path = os.path.join(self._tmpdir, "test.db")
        db_url = f"sqlite+aiosqlite:///{self._db_path}"

        # Forzar DATABASE_URL ANTES de cualquier create_app() o get_engine().
        self._saved_env = {}
        for key in ("DATABASE_URL", "ENVIRONMENT", "JWT_SECRET", "SECRET_KEY", "REDIS_URL"):
            self._saved_env[key] = os.environ.get(key)
        os.environ["DATABASE_URL"] = db_url
        os.environ["ENVIRONMENT"] = "development"
        os.environ.setdefault("JWT_SECRET", "x" * 32)
        os.environ.setdefault("SECRET_KEY", "x" * 32)
        os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
        reset_settings_cache()
        reset_engine_cache()

        # Crear app. SIN db_path → modo sqlite async, el engine async es la
        # única fuente de verdad. La rama sqlite_legacy NO se usa.
        self.app = create_app()
        self.client = TestClient(self.app)

        # Inicializar el schema async (tablas) y sembrar el admin.
        from app.db.session import get_engine

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
        from app.db.session import get_engine

        await get_engine().dispose()
        reset_engine_cache()
        # Restaurar env vars
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_settings_cache()
        # Limpiar archivo temporal
        try:
            os.remove(self._db_path)
            os.rmdir(self._tmpdir)
        except OSError:
            pass

    # --- Tests ---

    async def test_create_and_list_category(self) -> None:
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

    async def test_duplicate_name_is_case_insensitive(self) -> None:
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

    async def test_parent_id_not_found(self) -> None:
        resp = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Aceites", "parent_id": str(uuid.uuid4())},
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["code"], "category_not_found")

    async def test_hierarchical_categories_three_levels(self) -> None:
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
        leaf_detail = self.client.get(
            f"/api/v1/categories/{leaf_id}", headers=self.headers
        ).json()
        self.assertEqual(leaf_detail["parent_id"], mid_id)

    async def test_patch_partial(self) -> None:
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

    async def test_soft_delete(self) -> None:
        cat_id = self.client.post(
            "/api/v1/categories",
            json={"nombre": "Temporal"},
            headers=self.headers,
        ).json()["id"]

        delete_resp = self.client.delete(
            f"/api/v1/categories/{cat_id}", headers=self.headers
        )
        self.assertEqual(delete_resp.status_code, 204)

        # Sigue existiendo la fila pero is_active=False
        detail = self.client.get(
            f"/api/v1/categories/{cat_id}", headers=self.headers
        )
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.json()["is_active"])

        # Filtro is_active=true la esconde del listado
        list_active = self.client.get(
            "/api/v1/categories",
            params={"is_active": "true"},
            headers=self.headers,
        ).json()
        self.assertEqual(len(list_active), 0)

    async def test_direct_circular_reference(self) -> None:
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
        self.assertEqual(
            resp.json()["detail"]["code"], "category_circular_reference"
        )

    async def test_transitive_circular_reference(self) -> None:
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
        self.assertEqual(
            resp.json()["detail"]["code"], "category_circular_reference"
        )

    async def test_category_not_found(self) -> None:
        resp = self.client.get(
            f"/api/v1/categories/{uuid.uuid4()}", headers=self.headers
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["detail"]["code"], "category_not_found")


if __name__ == "__main__":
    unittest.main()
