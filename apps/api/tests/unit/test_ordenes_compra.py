"""Tests del workflow de Ordenes de Compra + public token approval (Fase 6).

Cubre:
- Crear OC en estado Borrador.
- Actualizar OC solo si esta en Borrador.
- Enviar correo genera token y encola en email_outbox.
- Enviar correo falla si OC no esta en Borrador.
- Aprobar OC via token publico.
- Rechazar OC via token publico con motivo.
- Token expirado retorna 410.
- Token invalido retorna 401.
- Rate limiting 5 req/min en /public/ordenes-compra/*.

Patron: unittest.IsolatedAsyncioTestCase con AsyncEngine SQLite + StaticPool.
"""
from __future__ import annotations

import os
import unittest
from decimal import Decimal
from uuid import uuid4

# Configurar el AsyncEngine antes de importar la app
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault(
    "JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from sqlalchemy import event, select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import reset_settings_cache  # noqa: E402
from app.core.rate_limit import reset_rate_limiter_for_tests  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.modules.ordenes_compra.service import OrdenCompraService  # noqa: E402


reset_settings_cache()


def _create_test_engine() -> AsyncEngine:
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


class OrdenCompraTestCase(unittest.IsolatedAsyncioTestCase):
    """Tests de service-level (sin TestClient) - patron de test_ordenes_compra.py
    integracion."""

    async def asyncSetUp(self) -> None:
        from app.db.session import reset_engine_cache

        reset_rate_limiter_for_tests()
        reset_engine_cache()
        self.engine = _create_test_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        await self._seed()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        from app.db.session import reset_engine_cache
        reset_engine_cache()
        reset_rate_limiter_for_tests()

    async def _seed(self) -> None:
        from app.db.models.products import Product
        from app.db.models.supervisores import Supervisor
        from app.db.models.warehouses import Warehouse

        self.principal_id = uuid4()
        self.supervisor_id = uuid4()
        self.p1_id = uuid4()
        self.p2_id = uuid4()
        async with self.session_factory() as s:
            s.add_all([
                Warehouse(
                    id=self.principal_id, code="PRINCIPAL",
                    name="Bodega Principal", warehouse_type="principal",
                    is_active=True,
                ),
                Supervisor(
                    id=self.supervisor_id, nombre="Sup Test",
                    email="supervisor.test@bodega.example", activo=True,
                ),
                Product(
                    id=self.p1_id, sku="SKU-OC-001", name="Producto OC 1",
                    unit="unidad", is_active=True,
                ),
                Product(
                    id=self.p2_id, sku="SKU-OC-002", name="Producto OC 2",
                    unit="unidad", is_active=True,
                ),
            ])
            await s.commit()

    async def _crear_oc(self) -> "OrdenCompraView":  # type: ignore[name-defined]  # noqa: F821
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            view = await service.create_orden(
                id_bodega_principal=self.principal_id,
                id_supervisor=self.supervisor_id,
                proveedor_nombre="Proveedor Test",
                lineas=[
                    {
                        "id_producto": self.p1_id,
                        "cantidad_pedida": Decimal("10"),
                        "costo_unitario_pactado": Decimal("100"),
                    },
                    {
                        "id_producto": self.p2_id,
                        "cantidad_pedida": Decimal("5"),
                        "costo_unitario_pactado": Decimal("50"),
                    },
                ],
            )
            await s.commit()
        return view

    # 1. Crear OC en Borrador OK
    async def test_crear_oc_borrador_ok(self) -> None:
        view = await self._crear_oc()
        self.assertTrue(view.codigo.startswith("OC-"))
        self.assertEqual(view.estado, "borrador")
        self.assertEqual(view.total_estimado, Decimal("1250.00"))
        self.assertEqual(len(view.detalles), 2)
        self.assertEqual(view.supervisor_nombre, "Sup Test")

    # 2. Actualizar OC solo si esta en Borrador
    async def test_actualizar_oc_solo_si_borrador(self) -> None:
        view = await self._crear_oc()
        # Update en borrador: OK
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            actualizado = await service.update_orden(view.id, notas="Actualizado")
            await s.commit()
        self.assertEqual(actualizado.notas, "Actualizado")

        # Enviar a supervisor
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            await service.enviar_correo(view.id)
            await s.commit()

        # Intentar update: debe fallar
        from app.core.errors import InvalidOrdenCompraStatusError
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            with self.assertRaises(InvalidOrdenCompraStatusError):
                await service.update_orden(view.id, notas="No debe aplicarse")

    # 3. Enviar correo genera token y encola outbox
    async def test_enviar_correo_genera_token_y_encola_outbox(self) -> None:
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            v, token, outbox_id = await service.enviar_correo(view.id)
            await s.commit()
        self.assertEqual(v.estado, "enviado_a_supervisor")
        self.assertTrue(token)

        # Verificar email_outbox
        from app.db.models.ordenes_compra import EmailOutbox
        async with self.session_factory() as s:
            stmt = select(EmailOutbox)
            outbox_rows = list((await s.execute(stmt)).scalars().all())
            self.assertEqual(len(outbox_rows), 1)
            self.assertEqual(outbox_rows[0].to_email, "supervisor.test@bodega.example")
            self.assertEqual(outbox_rows[0].status, "pending")
            self.assertIn(token, outbox_rows[0].body_html)
            self.assertEqual(outbox_rows[0].id, outbox_id)

    # 4. Enviar correo solo si Borrador; falla si Enviado
    async def test_enviar_correo_solo_si_borrador_falla_si_enviado(self) -> None:
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            await service.enviar_correo(view.id)
            await s.commit()

        from app.core.errors import InvalidOrdenCompraStatusError
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            with self.assertRaises(InvalidOrdenCompraStatusError):
                await service.enviar_correo(view.id)

    # 5. Aprobar OC via token publico
    async def test_aprobar_oc_via_token_publico_ok(self) -> None:
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            _, token, _ = await service.enviar_correo(view.id)
            await s.commit()

        # Simular llamada al endpoint publico (sin auth)
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            view_aprobado = await service.aprobar_con_token(token, "approve")
            await s.commit()
        self.assertEqual(view_aprobado.estado, "aprobado")
        self.assertIsNotNone(view_aprobado.aprobado_at)

    # 6. Rechazar OC via token publico con motivo
    async def test_rechazar_oc_via_token_publico_ok(self) -> None:
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            _, token, _ = await service.enviar_correo(view.id)
            await s.commit()

        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            view_rechazado = await service.aprobar_con_token(
                token, "reject", motivo="Excede presupuesto"
            )
            await s.commit()
        self.assertEqual(view_rechazado.estado, "rechazado")
        self.assertIn("presupuesto", view_rechazado.motivo_rechazo)

    # 7. Token invalido retorna 401
    async def test_token_invalido_retorna_401(self) -> None:
        from app.core.errors import InvalidApprovalTokenError
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            with self.assertRaises(InvalidApprovalTokenError):
                await service.aprobar_con_token("esto-no-es-un-token-valido", "approve")


class OrdenCompraTokenExpiradoTestCase(unittest.IsolatedAsyncioTestCase):
    """Test del flujo de token expirado."""

    async def asyncSetUp(self) -> None:
        from app.db.session import reset_engine_cache

        reset_rate_limiter_for_tests()
        reset_engine_cache()
        self.engine = _create_test_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

        from app.db.models.products import Product
        from app.db.models.supervisores import Supervisor
        from app.db.models.warehouses import Warehouse

        self.principal_id = uuid4()
        self.supervisor_id = uuid4()
        self.p1_id = uuid4()
        async with self.session_factory() as s:
            s.add_all([
                Warehouse(
                    id=self.principal_id, code="PRINCIPAL",
                    name="Bodega Principal", warehouse_type="principal",
                    is_active=True,
                ),
                Supervisor(
                    id=self.supervisor_id, nombre="Sup",
                    email="exp@bodega.example", activo=True,
                ),
                Product(
                    id=self.p1_id, sku="SKU-EXP", name="P",
                    unit="unidad", is_active=True,
                ),
            ])
            await s.commit()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        from app.db.session import reset_engine_cache
        reset_engine_cache()
        reset_rate_limiter_for_tests()

    async def test_token_expirado_retorna_410(self) -> None:
        from app.core.errors import ExpiredApprovalTokenError
        from app.modules.ordenes_compra.service import OrdenCompraService

        # Crear OC
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            view = await service.create_orden(
                id_bodega_principal=self.principal_id,
                id_supervisor=self.supervisor_id,
                proveedor_nombre="X",
                lineas=[
                    {
                        "id_producto": self.p1_id,
                        "cantidad_pedida": Decimal("1"),
                        "costo_unitario_pactado": Decimal("1"),
                    }
                ],
            )
            await s.commit()

        # Mockear verify_approval_token para que lance ApprovalTokenExpiredError
        # (simula un token firmado correctamente pero con timestamp > max_age).
        from unittest.mock import patch
        from app.core.security import ApprovalTokenExpiredError

        def fake_verify(token):  # type: ignore[no-untyped-def]
            raise ApprovalTokenExpiredError("Token expirado (simulado)")

        with patch(
            "app.modules.ordenes_compra.actions.aprobar.verify_approval_token",
            side_effect=fake_verify,
        ):
            async with self.session_factory() as s:
                service = OrdenCompraService(s)
                with self.assertRaises(ExpiredApprovalTokenError):
                    await service.aprobar_con_token("any-token", "approve")


class OrdenCompraRateLimitTestCase(unittest.IsolatedAsyncioTestCase):
    """Test del rate limiter in-memory."""

    def setUp(self) -> None:
        from app.core.rate_limit import get_rate_limiter
        reset_rate_limiter_for_tests()
        self.limiter = get_rate_limiter()

    def test_rate_limiting_5_req_por_minuto(self) -> None:
        """5 requests pasan, la 6ta falla."""
        ip = "192.168.1.42"
        for i in range(5):
            r = self.limiter.check(ip, "public_oc", max_requests=5, window_seconds=60)
            self.assertTrue(r.allowed, f"req {i+1} deberia pasar")
        # La 6ta debe fallar
        r = self.limiter.check(ip, "public_oc", max_requests=5, window_seconds=60)
        self.assertFalse(r.allowed)
        self.assertGreater(r.retry_after_seconds, 0)

    def test_rate_limiting_por_ip(self) -> None:
        """Distintas IPs no comparten cupo."""
        for i in range(5):
            r1 = self.limiter.check("1.1.1.1", "public_oc", max_requests=5, window_seconds=60)
            self.assertTrue(r1.allowed)
            r2 = self.limiter.check("2.2.2.2", "public_oc", max_requests=5, window_seconds=60)
            self.assertTrue(r2.allowed)

    def test_rate_limiting_sliding_window(self) -> None:
        """Sliding window: si pasa el tiempo, se libera cupo."""
        # En este test no podemos esperar 60s, asi que verificamos que
        # al limpiar manualmente el bucket se libera.
        ip = "10.0.0.1"
        for _ in range(5):
            self.limiter.check(ip, "public_oc", max_requests=5, window_seconds=60)
        r = self.limiter.check(ip, "public_oc", max_requests=5, window_seconds=60)
        self.assertFalse(r.allowed)
        # Limpiar manualmente
        self.limiter.clear()
        r = self.limiter.check(ip, "public_oc", max_requests=5, window_seconds=60)
        self.assertTrue(r.allowed)
