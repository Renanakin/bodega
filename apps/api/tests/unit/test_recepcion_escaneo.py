"""
Tests del flujo de recepcion con escaneo de codigo de barras (Fase 5).

Cubre el refinamiento de ``SolicitudService._apply_receive()`` que ahora
usa ``app.modules.barcode.match_product()`` para validar el barcode
escaneado contra el codigo del producto.

Casos cubiertos:
- Recepcion con barcode EAN-13 valido del producto -> OK.
- Recepcion con barcode EAN-13 con checksum invalido -> 422 barcode_mismatch.
- Recepcion con barcode de OTRO producto -> 409 barcode_mismatch.
- Recepcion de producto SIN codigo_barras (skip de validacion) -> OK.
- E2E completo: 5 lineas escaneadas -> estado `received`.
- E2E parcial: 3 de 5 lineas con incidencia -> estado `partially_received`.
- Verificar estado `partially_received` tras recepcion parcial.
- Verificar estado `received` tras recepcion total.

Los tests usan el mismo patron que ``test_solicitudes.py``: AsyncEngine
SQLite + StaticPool + TestClient + BD legacy para usuarios.
"""
from __future__ import annotations

import os
import unittest
from decimal import Decimal
from typing import Any
from uuid import uuid4

# Configurar el AsyncEngine antes de importar la app (mismo patron que test_solicitudes.py)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault(
    "JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import reset_settings_cache  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


reset_settings_cache()


# Barcodes EAN-13 VALIDOS usados en los tests. Verificamos a mano que
# los checksums son correctos (algoritmo estandar: peso 1,3,1,3,...).
# 4006381333931: 4*1+0*3+0*1+6*3+3*1+8*3+1*1+3*3+3*1+3*3+9*1+3*3 = 89
#   89 mod 10 = 9 -> check digit = (10-9) mod 10 = 1. Coincide. VALID.
# 8001234567891: 8*1+0*3+0*1+1*3+2*1+3*3+4*1+5*3+6*1+7*3+8*1+9*3 = 87
#   87 mod 10 = 7 -> check digit = 3? No: (10-7) mod 10 = 3. Coincide con 1? No.
# Re-derivamos los checksums para garantizar validez.
def _ean13_check(body12: str) -> str:
    """Calcula el check digit EAN-13 para los primeros 12 digitos."""
    digits = [int(d) for d in body12]
    total = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    return str((10 - (total % 10)) % 10)


# EAN-13 validos generados en runtime (checksum correcto).
BC_P1 = "400638133393" + _ean13_check("400638133393")  # p1
BC_P2 = "800123456789" + _ean13_check("800123456789")  # p2
BC_P3 = "750103131130" + _ean13_check("750103131130")  # p3
BC_P4 = "400638133411" + _ean13_check("400638133411")  # p4
BC_P5 = "400638133420" + _ean13_check("400638133420")  # p5
# Un barcode EAN-13 con checksum deliberadamente INVALIDO.
BC_INVALIDO = "4006381333939"  # el check digit correcto es 1, no 9

pytestmark = pytest.mark.unit


def _create_test_engine() -> AsyncEngine:
    """Engine SQLite async con StaticPool para tests."""
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


async def _setup_escaneo_data(session: AsyncSession) -> dict[str, Any]:
    """Crea 5 productos con barcodes validos + 1 sin barcode.

    Productos p1..p5 tienen EAN-13 validos; p_sin_bc tiene codigo_barras=NULL.
    """
    from app.db.session import create_database, utcnow

    legacy_db = create_database(":memory:")
    now = utcnow().isoformat()
    users: dict[str, str] = {}
    for username, full_name, role in [
        ("origen", "Operador Origen", "origin_operator"),
        ("supervisor", "Supervisor", "supervisor"),
        ("destino", "Operador Destino", "destination_operator"),
    ]:
        uid = str(uuid4())
        users[f"{username}_id"] = uid
        legacy_db.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (uid, username, full_name, role, hash_password("demo123"), now),
        )

    from app.db.models.warehouses import Warehouse
    from app.db.models.products import Product
    from app.db.models.inventory import StockLevel
    from datetime import datetime, UTC

    warehouses: dict[str, Any] = {
        "principal_id": uuid4(),
        "aux1_id": uuid4(),
    }
    session.add(
        Warehouse(
            id=warehouses["principal_id"],
            code="PRINCIPAL",
            name="Bodega Principal",
            warehouse_type="principal",
            is_active=True,
        )
    )
    session.add(
        Warehouse(
            id=warehouses["aux1_id"],
            code="AUX-1",
            name="Auxiliar 1",
            warehouse_type="auxiliar",
            is_active=True,
        )
    )
    await session.flush()

    products: dict[str, Any] = {}
    barcodes = [BC_P1, BC_P2, BC_P3, BC_P4, BC_P5]
    for i in range(1, 6):
        pid = uuid4()
        products[f"p{i}_id"] = pid
        products[f"p{i}_sku"] = f"SKU-EAN-{i:03d}"
        products[f"p{i}_barcode"] = barcodes[i - 1]
        session.add(
            Product(
                id=pid,
                sku=products[f"p{i}_sku"],
                codigo_barras=barcodes[i - 1],
                name=f"Producto {i}",
                unit="unidad",
                is_active=True,
            )
        )

    # Producto sin barcode registrado
    products["p_sin_bc_id"] = uuid4()
    products["p_sin_bc_sku"] = "SKU-SIN-BC"
    session.add(
        Product(
            id=products["p_sin_bc_id"],
            sku=products["p_sin_bc_sku"],
            codigo_barras=None,
            name="Producto sin barcode",
            unit="unidad",
            is_active=True,
        )
    )
    await session.flush()

    # Stock en Principal (suficiente para despachar 100 de cada uno)
    for i in range(1, 6):
        session.add(
            StockLevel(
                warehouse_id=warehouses["principal_id"],
                product_id=products[f"p{i}_id"],
                quantity=Decimal("100"),
                min_quantity=Decimal("10"),
                updated_at=datetime.now(UTC),
            )
        )
    # Stock en Principal para el producto sin barcode
    session.add(
        StockLevel(
            warehouse_id=warehouses["principal_id"],
            product_id=products["p_sin_bc_id"],
            quantity=Decimal("100"),
            min_quantity=Decimal("10"),
            updated_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return {
        "users": users,
        "warehouses": warehouses,
        "products": products,
        "legacy_db": legacy_db,
    }


class RecepcionEscaneoTestCase(unittest.IsolatedAsyncioTestCase):
    """Tests del flujo de recepcion con barcode scanning (Fase 5)."""

    async def asyncSetUp(self) -> None:
        from app.db.session import reset_engine_cache
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

        setup = await _setup_escaneo_data(self.session_factory())
        self.users = setup["users"]
        self.warehouses = setup["warehouses"]
        self.products = setup["products"]
        self.legacy_db = setup["legacy_db"]
        self.app.state.db = self.legacy_db

        self.client = TestClient(self.app)
        self.headers_origen = _auth(self.client, "origen", "demo123")
        self.headers_supervisor = _auth(self.client, "supervisor", "demo123")
        self.headers_destino = _auth(self.client, "destino", "demo123")

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.legacy_db.close()
        from app.db.session import reset_engine_cache
        reset_engine_cache()

    def _id(self, key: str) -> str:
        if key in self.users:
            return self.users[key]
        if key in self.warehouses:
            return str(self.warehouses[key])
        if key in self.products:
            return str(self.products[key])
        raise KeyError(key)

    def _crear_despachar_5_lineas(self) -> str:
        """Helper: crea, aprueba y despacha una solicitud con p1..p5.
        Devuelve el id de la solicitud para usar en /receive.
        """
        # Lineas de la solicitud (create) usan cantidad_solicitada
        lineas_create = [
            {"producto_id": str(self._id(f"p{i}_id")), "cantidad_solicitada": 10}
            for i in range(1, 6)
        ]
        # Lineas del despacho (dispatch) usan cantidad_despachada
        lineas_dispatch = [
            {
                "producto_id": str(self._id(f"p{i}_id")),
                "cantidad_despachada": 10,
            }
            for i in range(1, 6)
        ]
        sol = self.client.post(
            "/api/v1/solicitudes",
            json={
                "bodega_origen_id": str(self._id("aux1_id")),
                "bodega_destino_id": str(self._id("principal_id")),
                "lineas": lineas_create,
            },
            headers=self.headers_origen,
        )
        self.assertEqual(sol.status_code, 201, sol.text)
        sol_id = sol.json()["id"]
        self.client.post(
            f"/api/v1/solicitudes/{sol_id}/approve", json={},
            headers=self.headers_supervisor,
        )
        dispatch_resp = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/dispatch",
            json={"lineas": lineas_dispatch},
            headers=self.headers_origen,
        )
        self.assertEqual(
            dispatch_resp.status_code, 200,
            f"dispatch fallo: {dispatch_resp.text}",
        )
        self.assertEqual(
            dispatch_resp.json()["estado"], "in_transit",
            f"esperado in_transit, obtenido {dispatch_resp.json()['estado']}",
        )
        return sol_id

    # =====================================================================
    # 11. Recepcion con barcode valido -> OK
    # =====================================================================
    async def test_recibir_linea_con_barcode_valido_ok(self) -> None:
        sol_id = self._crear_despachar_5_lineas()
        resp = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={
                "lineas": [
                    {
                        "producto_id": str(self._id("p1_id")),
                        "cantidad_recibida": 10,
                        "barcode": self.products["p1_barcode"],
                    }
                ]
            },
            headers=self.headers_destino,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        # La solicitud queda parcialmente recibida (4 lineas pendientes).
        self.assertEqual(resp.json()["estado"], "partially_received")

    # =====================================================================
    # 12. Recepcion con barcode de checksum invalido -> 409 barcode_mismatch
    # =====================================================================
    async def test_recibir_linea_con_barcode_invalido_falla(self) -> None:
        sol_id = self._crear_despachar_5_lineas()
        resp = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={
                "lineas": [
                    {
                        "producto_id": str(self._id("p1_id")),
                        "cantidad_recibida": 10,
                        # BC_INVALIDO tiene checksum deliberadamente malo
                        # -> match_product retorna False -> BarcodeMismatchError.
                        "barcode": BC_INVALIDO,
                    }
                ]
            },
            headers=self.headers_destino,
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["code"], "barcode_mismatch")

    # =====================================================================
    # 13. Recepcion con barcode de OTRO producto -> 409 barcode_mismatch
    # =====================================================================
    async def test_recibir_linea_con_barcode_de_otro_producto_falla(self) -> None:
        sol_id = self._crear_despachar_5_lineas()
        # Mandamos el barcode de p2 con producto_id de p1
        resp = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={
                "lineas": [
                    {
                        "producto_id": str(self._id("p1_id")),
                        "cantidad_recibida": 10,
                        "barcode": self.products["p2_barcode"],
                    }
                ]
            },
            headers=self.headers_destino,
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        self.assertEqual(resp.json()["detail"]["code"], "barcode_mismatch")
        # Verificar que NO se desconto ningun stock en la bodega origen
        # (rollback transaccional). Producto p2 sigue intacto.
        async with self.session_factory() as s:
            from sqlalchemy import select
            from app.db.models.inventory import StockLevel
            stmt = select(StockLevel).where(
                StockLevel.warehouse_id == self._id("aux1_id"),
                StockLevel.product_id == self._id("p1_id"),
            )
            row = (await s.execute(stmt)).scalar_one_or_none()
            self.assertIsNone(row)  # nunca se incremento

    # =====================================================================
    # 14. Producto sin codigo_barras -> skip de la validacion
    # =====================================================================
    async def test_recibir_producto_sin_codigo_barras_skip(self) -> None:
        # Crear solicitud con el producto sin barcode
        sol = self.client.post(
            "/api/v1/solicitudes",
            json={
                "bodega_origen_id": str(self._id("aux1_id")),
                "bodega_destino_id": str(self._id("principal_id")),
                "lineas": [
                    {
                        "producto_id": str(self._id("p_sin_bc_id")),
                        "cantidad_solicitada": 5,
                    }
                ],
            },
            headers=self.headers_origen,
        )
        self.assertEqual(sol.status_code, 201, sol.text)
        sol_id = sol.json()["id"]
        self.client.post(
            f"/api/v1/solicitudes/{sol_id}/approve", json={},
            headers=self.headers_supervisor,
        )
        self.client.post(
            f"/api/v1/solicitudes/{sol_id}/dispatch",
            json={"lineas": [
                {"producto_id": str(self._id("p_sin_bc_id")), "cantidad_despachada": 5}
            ]},
            headers=self.headers_origen,
        )
        # Sin barcode en el payload: la validacion se salta (None)
        resp = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={"lineas": [
                {"producto_id": str(self._id("p_sin_bc_id")), "cantidad_recibida": 5}
            ]},
            headers=self.headers_destino,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["estado"], "received")

    # =====================================================================
    # 15. E2E: 5 lineas escaneadas con barcode valido -> received
    # =====================================================================
    async def test_e2e_recepcion_total_5_lineas_escaneadas(self) -> None:
        sol_id = self._crear_despachar_5_lineas()
        # Las 5 lineas con su barcode correspondiente
        lineas = [
            {
                "producto_id": str(self._id(f"p{i}_id")),
                "cantidad_recibida": 10,
                "barcode": self.products[f"p{i}_barcode"],
            }
            for i in range(1, 6)
        ]
        resp = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={"lineas": lineas},
            headers=self.headers_destino,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["estado"], "received")
        self.assertIsNotNone(resp.json()["received_at"])

        # Verificar que Auxiliar tiene 10 unidades de cada producto
        async with self.session_factory() as s:
            from sqlalchemy import select
            from app.db.models.inventory import StockLevel
            for i in range(1, 6):
                stmt = select(StockLevel).where(
                    StockLevel.warehouse_id == self._id("aux1_id"),
                    StockLevel.product_id == self._id(f"p{i}_id"),
                )
                row = (await s.execute(stmt)).scalar_one_or_none()
                self.assertIsNotNone(row)
                self.assertEqual(row.quantity, Decimal("10"))

    # =====================================================================
    # 16. E2E parcial: 3 de 5 con barcode OK + 2 con incidencia (sin escaneo)
    # =====================================================================
    async def test_e2e_recepcion_parcial_3_de_5_con_incidencia(self) -> None:
        sol_id = self._crear_despachar_5_lineas()
        # p1, p2, p3 escaneados OK; p4, p5 con incidencia (faltante, no se escanean).
        # Cantidad_recibida = 0 para las que no llegaron, con incidencia=faltante.
        lineas = [
            {
                "producto_id": str(self._id("p1_id")),
                "cantidad_recibida": 10,
                "barcode": self.products["p1_barcode"],
            },
            {
                "producto_id": str(self._id("p2_id")),
                "cantidad_recibida": 10,
                "barcode": self.products["p2_barcode"],
            },
            {
                "producto_id": str(self._id("p3_id")),
                "cantidad_recibida": 5,  # llegaron 5 de 10
                "barcode": self.products["p3_barcode"],
                "incidencia": "5 unidades danadas",
            },
            # p4 y p5 NO se incluyen (no se escanearon; faltante total).
            # El frontend solo envia lineas con cantidad > 0 o barcode presente.
        ]
        resp = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={"lineas": lineas, "notas": "Recepcion parcial con faltantes"},
            headers=self.headers_destino,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        # Estado: quedan lineas pendientes (p4, p5 con cantidad_recibida=0)
        # y p3 parcial (5 de 10) -> partially_received.
        self.assertEqual(resp.json()["estado"], "partially_received")

    # =====================================================================
    # 17. Estado partially_received tras recepcion parcial
    # =====================================================================
    async def test_estado_parcial_despues_de_recepcion_parcial(self) -> None:
        sol_id = self._crear_despachar_5_lineas()
        resp = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={"lineas": [
                {
                    "producto_id": str(self._id("p1_id")),
                    "cantidad_recibida": 5,  # mitad
                    "barcode": self.products["p1_barcode"],
                }
            ]},
            headers=self.headers_destino,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["estado"], "partially_received")
        # Verificar que received_at es None (solo se setea en received total)
        self.assertIsNone(resp.json()["received_at"])

    # =====================================================================
    # 18. Estado received tras recepcion total
    # =====================================================================
    async def test_estado_received_despues_de_recepcion_total(self) -> None:
        sol_id = self._crear_despachar_5_lineas()
        lineas = [
            {
                "producto_id": str(self._id(f"p{i}_id")),
                "cantidad_recibida": 10,
                "barcode": self.products[f"p{i}_barcode"],
            }
            for i in range(1, 6)
        ]
        # Primera llamada: solo 2 lineas -> parcial
        resp1 = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={"lineas": lineas[:2]},
            headers=self.headers_destino,
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json()["estado"], "partially_received")
        # Segunda llamada: 3 lineas mas -> completa
        resp2 = self.client.post(
            f"/api/v1/solicitudes/{sol_id}/receive",
            json={"lineas": lineas[2:]},
            headers=self.headers_destino,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json()["estado"], "received")
        self.assertIsNotNone(resp2.json()["received_at"])


def _auth(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, f"login failed: {response.text}"
    return {"Authorization": f"Bearer {response.json()['token']}"}


if __name__ == "__main__":
    unittest.main()
