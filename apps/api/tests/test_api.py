from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.auth.security import hash_password
from app.db.session import utcnow


def auth_headers(client: TestClient, username: str = "admin", password: str = "demo123") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(db_path=":memory:")
        self.client = TestClient(self.app)
        now = utcnow().isoformat()
        for username, full_name, role in [
            ("admin", "Administrador Demo", "admin"),
            ("supervisor", "Supervisor Demo", "supervisor"),
            ("origen", "Operador Origen Demo", "origin_operator"),
            ("destino", "Operador Destino Demo", "destination_operator"),
        ]:
            self.app.state.db.execute(
                """
                INSERT INTO users (id, username, full_name, role, password_hash, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (str(uuid4()), username, full_name, role, hash_password("demo123"), now),
            )
        self.admin_headers = auth_headers(self.client)
        self.supervisor_headers = auth_headers(self.client, "supervisor")
        self.origin_headers = auth_headers(self.client, "origen")
        self.destination_headers = auth_headers(self.client, "destino")

    def tearDown(self) -> None:
        self.app.state.db.close()

    def test_healthcheck_returns_ok(self) -> None:
        # FIX Deuda #4: el endpoint ``/api/v1/health`` (readiness) verifica
        # BD + Redis + worker. En tests sin esos servicios retorna 503.
        # El endpoint ``/api/v1/health/live`` (liveness) es un simple
        # ping que retorna 200 con ``{"status": "alive"}``.
        response = self.client.get("/api/v1/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "alive"})

    def test_create_and_list_warehouses(self) -> None:
        create_response = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "central",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        )
        list_response = self.client.get("/api/v1/warehouses", headers=self.admin_headers)

        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertEqual(payload["code"], "CENTRAL")
        self.assertEqual(payload["warehouse_type"], "principal")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

    def test_create_and_list_products(self) -> None:
        create_response = self.client.post(
            "/api/v1/products",
            json={
                "sku": "sku-001",
                "name": "Producto Inicial",
                "unit": "Unit",
            },
            headers=self.supervisor_headers,
        )
        list_response = self.client.get("/api/v1/products", headers=self.admin_headers)

        self.assertEqual(create_response.status_code, 201)
        payload = create_response.json()
        self.assertEqual(payload["sku"], "SKU-001")
        self.assertEqual(payload["unit"], "unit")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

    def test_register_movements_and_read_stock(self) -> None:
        warehouse_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-001",
                "name": "Producto Inicial",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]

        incoming_response = self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "movement_type": "in",
                "quantity": 10,
                "reference_type": "manual",
                "reference_id": "ingreso-001",
                "notes": "Carga inicial",
            },
            headers=self.admin_headers,
        )
        outgoing_response = self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "movement_type": "out",
                "quantity": 3,
                "reference_type": "manual",
                "reference_id": "salida-001",
                "notes": "Salida parcial",
            },
            headers=self.admin_headers,
        )
        stock_response = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": warehouse_id, "product_id": product_id},
            headers=self.admin_headers,
        )
        movement_response = self.client.get(
            "/api/v1/inventory/movements",
            params={"product_id": product_id},
            headers=self.admin_headers,
        )
        summary_response = self.client.get("/api/v1/inventory/summary", headers=self.admin_headers)

        self.assertEqual(incoming_response.status_code, 201)
        self.assertEqual(outgoing_response.status_code, 201)
        self.assertEqual(stock_response.status_code, 200)
        stock_payload = stock_response.json()
        self.assertEqual(len(stock_payload), 1)
        self.assertEqual(float(stock_payload[0]["quantity"]), 7.0)
        self.assertEqual(movement_response.status_code, 200)
        self.assertEqual(len(movement_response.json()), 2)
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.json()["movements"], 2)

    def test_rejects_outgoing_movement_with_insufficient_stock(self) -> None:
        warehouse_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-002",
                "name": "Producto Sin Stock",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]

        response = self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "movement_type": "out",
                "quantity": 1,
            },
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "insufficient_stock")

    @unittest.skip(
        "FIX Deuda #4: POST /transfers esta deprecado en ADR-0003. "
        "El flujo de 1 producto se migro a /api/v1/solicitudes (N productos). "
        "El flujo end-to-end equivalente se valida con el smoke_e2e_full.py."
    )
    def test_create_transfer_updates_both_warehouses(self) -> None:
        origin_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        destination_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "NORTE",
                "name": "Sucursal Norte",
                "warehouse_type": "auxiliar",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-100",
                "name": "Producto Transferible",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]

        self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": origin_id,
                "product_id": product_id,
                "movement_type": "in",
                "quantity": 10,
            },
            headers=self.admin_headers,
        )

        transfer_response = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": origin_id,
                "to_warehouse_id": destination_id,
                "product_id": product_id,
                "quantity": 4,
                "priority": "Alta",
                "notes": "Reabastecimiento interno",
            },
            headers=self.origin_headers,
        )
        transfer_id = transfer_response.json()["id"]
        approve_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/approve", headers=self.supervisor_headers
        )
        dispatch_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/dispatch",
            headers=self.origin_headers,
            json={"notes": "Salida hacia sucursal"},
        )
        receive_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/receive",
            headers=self.destination_headers,
            json={"quantity": 4, "notes": "Recepcion completa"},
        )
        list_response = self.client.get("/api/v1/transfers", headers=self.admin_headers)
        origin_stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": origin_id, "product_id": product_id},
            headers=self.admin_headers,
        )
        destination_stock = self.client.get(
            "/api/v1/inventory/stock",
            params={"warehouse_id": destination_id, "product_id": product_id},
            headers=self.admin_headers,
        )

        self.assertEqual(transfer_response.status_code, 201)
        self.assertEqual(transfer_response.json()["status"], "requested")
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(dispatch_response.status_code, 200)
        self.assertEqual(receive_response.status_code, 200)
        self.assertEqual(receive_response.json()["status"], "received")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(float(origin_stock.json()[0]["quantity"]), 6.0)
        self.assertEqual(float(destination_stock.json()[0]["quantity"]), 4.0)

    def test_rejects_transfer_with_same_origin_and_destination(self) -> None:
        warehouse_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-200",
                "name": "Producto",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]

        response = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": warehouse_id,
                "to_warehouse_id": warehouse_id,
                "product_id": product_id,
                "quantity": 1,
            },
            headers=self.origin_headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "invalid_transfer")

    @unittest.skip(
        "FIX Deuda #4: POST /transfers esta deprecado en ADR-0003. "
        "El flujo de 1 producto se migro a /api/v1/solicitudes (N productos). "
        "El flujo end-to-end equivalente se valida con el smoke_e2e_full.py."
    )
    def test_rejects_dispatch_before_approval(self) -> None:
        origin_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        destination_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "SUR",
                "name": "Sucursal Sur",
                "warehouse_type": "auxiliar",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-300",
                "name": "Producto Etapas",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]
        self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": origin_id,
                "product_id": product_id,
                "movement_type": "in",
                "quantity": 5,
            },
            headers=self.admin_headers,
        )
        transfer_id = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": origin_id,
                "to_warehouse_id": destination_id,
                "product_id": product_id,
                "quantity": 2,
            },
            headers=self.origin_headers,
        ).json()["id"]

        response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/dispatch",
            headers=self.origin_headers,
            json={"notes": "Intento fuera de secuencia"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "invalid_transfer_status")

    def test_requires_authentication(self) -> None:
        response = self.client.get("/api/v1/products")

        self.assertEqual(response.status_code, 401)

    @unittest.skip(
        "FIX Deuda #4: POST /transfers esta deprecado en ADR-0003. "
        "El flujo de 1 producto se migro a /api/v1/solicitudes (N productos). "
        "El flujo end-to-end equivalente se valida con el smoke_e2e_full.py."
    )
    def test_blocks_role_without_permission(self) -> None:
        origin_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "CENTRAL",
                "name": "Bodega Central",
                "warehouse_type": "principal",
            },
            headers=self.admin_headers,
        ).json()["id"]
        destination_id = self.client.post(
            "/api/v1/warehouses",
            json={
                "code": "NORTE",
                "name": "Sucursal Norte",
                "warehouse_type": "auxiliar",
            },
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={
                "sku": "SKU-999",
                "name": "Producto Restringido",
                "unit": "unit",
            },
            headers=self.admin_headers,
        ).json()["id"]
        self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": origin_id,
                "product_id": product_id,
                "movement_type": "in",
                "quantity": 5,
            },
            headers=self.admin_headers,
        )
        transfer_response = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": origin_id,
                "to_warehouse_id": destination_id,
                "product_id": product_id,
                "quantity": 1,
            },
            headers=self.origin_headers,
        )
        transfer_id = transfer_response.json()["id"]

        response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/approve",
            headers=self.origin_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["code"], "insufficient_permissions")

    def test_login_and_audit_endpoints(self) -> None:
        me_response = self.client.get("/api/v1/auth/me", headers=self.admin_headers)
        audit_response = self.client.get("/api/v1/audit", headers=self.admin_headers)

        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["username"], "admin")
        self.assertEqual(audit_response.status_code, 200)
        self.assertGreaterEqual(len(audit_response.json()), 1)

    @unittest.skip(
        "FIX Deuda #4: POST /transfers esta deprecado en ADR-0003. "
        "El flujo de 1 producto se migro a /api/v1/solicitudes (N productos). "
        "El flujo end-to-end equivalente se valida con el smoke_e2e_full.py."
    )
    def test_partial_receive_and_complete_later(self) -> None:
        origin_id = self.client.post(
            "/api/v1/warehouses",
            json={"code": "CEN2", "name": "Central 2", "warehouse_type": "principal"},
            headers=self.admin_headers,
        ).json()["id"]
        destination_id = self.client.post(
            "/api/v1/warehouses",
            json={"code": "NOR2", "name": "Norte 2", "warehouse_type": "auxiliar"},
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={"sku": "SKU-401", "name": "Producto Parcial", "unit": "unit"},
            headers=self.admin_headers,
        ).json()["id"]
        self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": origin_id,
                "product_id": product_id,
                "movement_type": "in",
                "quantity": 9,
            },
            headers=self.admin_headers,
        )
        transfer_id = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": origin_id,
                "to_warehouse_id": destination_id,
                "product_id": product_id,
                "quantity": 9,
            },
            headers=self.origin_headers,
        ).json()["id"]

        self.client.post(
            f"/api/v1/transfers/{transfer_id}/approve",
            headers=self.supervisor_headers,
        )
        self.client.post(
            f"/api/v1/transfers/{transfer_id}/dispatch",
            headers=self.origin_headers,
            json={"notes": "Despacho completo"},
        )
        partial_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/receive",
            headers=self.destination_headers,
            json={
                "quantity": 4,
                "notes": "Llegada parcial",
                "incident_type": "faltante",
                "incident_notes": "Faltan 5 unidades en el transporte",
            },
        )
        complete_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/receive",
            headers=self.destination_headers,
            json={"quantity": 5, "notes": "Completa recepcion"},
        )

        self.assertEqual(partial_response.status_code, 200)
        self.assertEqual(partial_response.json()["status"], "partially_received")
        self.assertEqual(float(partial_response.json()["received_quantity"]), 4.0)
        self.assertEqual(partial_response.json()["incident_type"], "faltante")
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.json()["status"], "received")
        self.assertEqual(float(complete_response.json()["received_quantity"]), 9.0)

    @unittest.skip(
        "FIX Deuda #4: POST /transfers esta deprecado en ADR-0003. "
        "El flujo de 1 producto se migro a /api/v1/solicitudes (N productos). "
        "El flujo end-to-end equivalente se valida con el smoke_e2e_full.py."
    )
    def test_update_and_cancel_requested_transfer(self) -> None:
        origin_id = self.client.post(
            "/api/v1/warehouses",
            json={"code": "CEN3", "name": "Central 3", "warehouse_type": "principal"},
            headers=self.admin_headers,
        ).json()["id"]
        destination_id = self.client.post(
            "/api/v1/warehouses",
            json={"code": "NOR3", "name": "Norte 3", "warehouse_type": "auxiliar"},
            headers=self.admin_headers,
        ).json()["id"]
        product_id = self.client.post(
            "/api/v1/products",
            json={"sku": "SKU-402", "name": "Producto Editable", "unit": "unit"},
            headers=self.admin_headers,
        ).json()["id"]
        self.client.post(
            "/api/v1/inventory/movements",
            json={
                "warehouse_id": origin_id,
                "product_id": product_id,
                "movement_type": "in",
                "quantity": 6,
            },
            headers=self.admin_headers,
        )
        transfer_id = self.client.post(
            "/api/v1/transfers",
            json={
                "from_warehouse_id": origin_id,
                "to_warehouse_id": destination_id,
                "product_id": product_id,
                "quantity": 2,
            },
            headers=self.origin_headers,
        ).json()["id"]

        update_response = self.client.patch(
            f"/api/v1/transfers/{transfer_id}",
            headers=self.origin_headers,
            json={"quantity": 3, "priority": "Alta", "notes": "Actualizar solicitud"},
        )
        cancel_response = self.client.post(
            f"/api/v1/transfers/{transfer_id}/cancel",
            headers=self.origin_headers,
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(float(update_response.json()["quantity"]), 3.0)
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
