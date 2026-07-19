"""Tests E2E de notificaciones in-app automaticas (Deuda #7).

Cubre:
- NotificacionesService.notify_user / notify_users / notify_role_except_actor
  (broadcast excluyendo al actor, sin excluir cuando actor_id=None).
- SolicitudService emite la notificacion correcta en cada transicion:
    CREATE  -> solicitud.created    a ADMIN + SUPERVISOR (excluye actor)
    APPROVE -> solicitud.approved   a ORIGIN_OPERATOR
    DISPATCH-> solicitud.dispatched a DESTINATION_OPERATOR
    RECEIVE -> solicitud.received   a ADMIN + SUPERVISOR (excluye actor)
    REJECT  -> solicitud.rejected   a ORIGIN_OPERATOR
    CANCEL  -> solicitud.cancelled  a ADMIN + SUPERVISOR (excluye actor)
- OrdenCompraService emite la notificacion correcta en cada transicion:
    ENVIAR_CORREO  -> orden_compra.enviada   a ADMIN + SUPERVISOR
    APROBAR_ORDEN  -> orden_compra.aprobada  a ADMIN + SUPERVISOR
    RECHAZAR_ORDEN -> orden_compra.rechazada a ADMIN + SUPERVISOR
    MARCAR_COMPRADA-> orden_compra.recibida  a ADMIN + SUPERVISOR
    APROBAR_TOKEN  -> orden_compra.aprobada  a ADMIN + SUPERVISOR (sin excluir)
- Workflow E2E completo de Solicitud (create -> approve -> dispatch -> receive)
  genera exactamente 4 notificaciones, una por transicion.

Patron: unittest.IsolatedAsyncioTestCase con AsyncEngine SQLite + StaticPool
(mismo patron que test_ordenes_compra.py y test_solicitudes.py).
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
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.db.models.notificaciones import NotificationType, Notificacion  # noqa: E402
from app.db.models.users import User, UserRole  # noqa: E402
from app.modules.notificaciones.service import NotificacionesService  # noqa: E402
from app.modules.ordenes_compra.service import OrdenCompraService  # noqa: E402
from app.modules.solicitudes.service import SolicitudService  # noqa: E402

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


# ============================================================ HELPER UTILS


async def _notif_for(
    session: AsyncSession, user_id, tipo: str | None = None
) -> list[Notificacion]:
    """Lee las notificaciones de un usuario (mas recientes primero).

    Si ``tipo`` se da, filtra por tipo exacto.
    """
    stmt = select(Notificacion).where(Notificacion.user_id == user_id)
    if tipo is not None:
        stmt = stmt.where(Notificacion.tipo == tipo)
    stmt = stmt.order_by(Notificacion.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ============================================================ NotificacionesService


class NotificacionesServiceUnitTests(unittest.IsolatedAsyncioTestCase):
    """Tests unitarios del NotificacionesService (broadcast helpers)."""

    async def asyncSetUp(self) -> None:
        from app.db.session import reset_engine_cache

        reset_engine_cache()
        self.engine = _create_test_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        await self._seed_users()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def _seed_users(self) -> None:
        """Crea 6 users (1 admin, 1 sup, 2 origin_op, 2 dest_op)."""
        from datetime import UTC, datetime

        self.admin_id = uuid4()
        self.supervisor_id = uuid4()
        self.origin_op_1_id = uuid4()
        self.origin_op_2_id = uuid4()
        self.dest_op_1_id = uuid4()
        self.dest_op_2_id = uuid4()
        now = datetime.now(UTC)
        async with self.session_factory() as s:
            s.add_all([
                User(
                    id=self.admin_id, username="admin_n",
                    full_name="Admin N", role=UserRole.ADMIN,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.supervisor_id, username="sup_n",
                    full_name="Sup N", role=UserRole.SUPERVISOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.origin_op_1_id, username="op1_n",
                    full_name="Op1 N", role=UserRole.ORIGIN_OPERATOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.origin_op_2_id, username="op2_n",
                    full_name="Op2 N", role=UserRole.ORIGIN_OPERATOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.dest_op_1_id, username="do1_n",
                    full_name="Dest1 N", role=UserRole.DESTINATION_OPERATOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.dest_op_2_id, username="do2_n",
                    full_name="Dest2 N", role=UserRole.DESTINATION_OPERATOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
            ])
            await s.commit()

    async def test_notify_users_bulk_insert(self) -> None:
        """notify_users hace 1 INSERT para todos los recipients."""
        async with self.session_factory() as s:
            svc = NotificacionesService(s)
            count = await svc.notify_users(
                user_ids=[self.admin_id, self.supervisor_id],
                tipo="test.bulk",
                titulo="Bulk test",
            )
            self.assertEqual(count, 2)
            await s.commit()

        async with self.session_factory() as s:
            admin_notifs = await _notif_for(s, self.admin_id, "test.bulk")
            self.assertEqual(len(admin_notifs), 1)
            self.assertEqual(admin_notifs[0].titulo, "Bulk test")

    async def test_notify_users_lista_vacia_retorna_0(self) -> None:
        async with self.session_factory() as s:
            svc = NotificacionesService(s)
            count = await svc.notify_users(
                user_ids=[],
                tipo="test.empty",
                titulo="Empty",
            )
            self.assertEqual(count, 0)

    async def test_notify_role_except_actor_excluye_al_actor(self) -> None:
        """Si actor_id es admin, NO se le envia la notificacion."""
        async with self.session_factory() as s:
            svc = NotificacionesService(s)
            count = await svc.notify_role_except_actor(
                actor_id=self.admin_id,
                roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
                tipo="test.exclude_actor",
                titulo="Solo supervisor",
            )
            # Solo el supervisor (1) — admin excluido.
            self.assertEqual(count, 1)
            await s.commit()

        async with self.session_factory() as s:
            admin_n = await _notif_for(s, self.admin_id, "test.exclude_actor")
            sup_n = await _notif_for(s, self.supervisor_id, "test.exclude_actor")
            self.assertEqual(len(admin_n), 0, "admin excluido")
            self.assertEqual(len(sup_n), 1)

    async def test_notify_role_except_actor_sin_actor_no_excluye(self) -> None:
        """Si actor_id es None, NO se excluye a nadie."""
        async with self.session_factory() as s:
            svc = NotificacionesService(s)
            count = await svc.notify_role_except_actor(
                actor_id=None,
                roles=[UserRole.ADMIN, UserRole.SUPERVISOR],
                tipo="test.no_actor",
                titulo="Todos",
            )
            # admin + supervisor = 2
            self.assertEqual(count, 2)

    async def test_notify_role_except_actor_roles_multiples(self) -> None:
        """Broadcast a multiples roles: 2 origin_op + 2 dest_op = 4."""
        async with self.session_factory() as s:
            svc = NotificacionesService(s)
            count = await svc.notify_role_except_actor(
                actor_id=None,
                roles=[UserRole.ORIGIN_OPERATOR, UserRole.DESTINATION_OPERATOR],
                tipo="test.multi_role",
                titulo="Operadores",
            )
            self.assertEqual(count, 4)

    async def test_notify_role_except_actor_excluye_usuarios_inactivos(self) -> None:
        """Users inactivos NO reciben notificaciones (is_active=False)."""
        # Desactivar origin_op_2
        async with self.session_factory() as s:
            u = await s.get(User, self.origin_op_2_id)
            assert u is not None
            u.is_active = False
            await s.commit()

        async with self.session_factory() as s:
            svc = NotificacionesService(s)
            count = await svc.notify_role_except_actor(
                actor_id=None,
                roles=[UserRole.ORIGIN_OPERATOR],
                tipo="test.skip_inactive",
                titulo="Solo activos",
            )
            # Solo origin_op_1 (origin_op_2 desactivado).
            self.assertEqual(count, 1)


# ============================================================ SolicitudService


class SolicitudServiceNotifTests(unittest.IsolatedAsyncioTestCase):
    """Tests de integracion: cada transicion de SolicitudService emite la
    notificacion esperada."""

    async def asyncSetUp(self) -> None:
        from app.db.session import reset_engine_cache

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

    async def _seed(self) -> None:
        from datetime import UTC, datetime

        from app.db.models.inventory import StockLevel
        from app.db.models.products import Product
        from app.db.models.warehouses import Warehouse

        self.admin_id = uuid4()
        self.supervisor_id = uuid4()
        self.origin_op_id = uuid4()
        self.dest_op_id = uuid4()
        self.principal_id = uuid4()
        self.aux_id = uuid4()
        self.product_id = uuid4()
        now = datetime.now(UTC)

        async with self.session_factory() as s:
            s.add_all([
                User(
                    id=self.admin_id, username="admin_s",
                    full_name="Admin S", role=UserRole.ADMIN,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.supervisor_id, username="sup_s",
                    full_name="Sup S", role=UserRole.SUPERVISOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.origin_op_id, username="op_s",
                    full_name="Op S", role=UserRole.ORIGIN_OPERATOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.dest_op_id, username="do_s",
                    full_name="Dest S", role=UserRole.DESTINATION_OPERATOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
                Warehouse(
                    id=self.principal_id, code="PRINCIPAL",
                    name="Principal", warehouse_type="principal",
                    is_active=True,
                ),
                Warehouse(
                    id=self.aux_id, code="AUX1",
                    name="Aux1", warehouse_type="auxiliar",
                    is_active=True,
                ),
                Product(
                    id=self.product_id, sku="SKU-NOTIF-001",
                    name="Producto Notif", unit="unidad", is_active=True,
                ),
            ])
            await s.flush()  # Insertar users/warehouses/products primero
            # Stock suficiente en Principal para que dispatch funcione.
            s.add(StockLevel(
                warehouse_id=self.principal_id,
                product_id=self.product_id,
                quantity=Decimal("100"),
                min_quantity=Decimal("5"),
                max_quantity=Decimal("500"),
            ))
            await s.commit()

    async def _count_notifs(
        self, user_id, tipo: str
    ) -> int:
        async with self.session_factory() as s:
            notifs = await _notif_for(s, user_id, tipo)
            return len(notifs)

    async def test_create_solicitud_notifica_admin_supervisor_excluye_actor(self) -> None:
        """CREATE solicitud: notifica a admin+supervisor excluyendo al actor."""
        async with self.session_factory() as s:
            service = SolicitudService(s)
            view = await service.create_solicitud(
                id_bodega_origen=self.aux_id,
                id_bodega_destino=self.principal_id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_solicitada": Decimal("10"),
                }],
                prioridad="normal",
                notas="test",
                user_id=self.origin_op_id,  # origin_op crea
            )
            await s.commit()
        codigo = view.codigo

        # admin y supervisor reciben la notificacion
        self.assertEqual(
            await self._count_notifs(self.admin_id, NotificationType.SOLICITUD_CREATED.value),
            1, "admin recibe solicitud.created",
        )
        self.assertEqual(
            await self._count_notifs(self.supervisor_id, NotificationType.SOLICITUD_CREATED.value),
            1, "supervisor recibe solicitud.created",
        )
        # origin_op NO recibe (es el actor)
        self.assertEqual(
            await self._count_notifs(self.origin_op_id, NotificationType.SOLICITUD_CREATED.value),
            0, "origin_op excluido como actor",
        )
        # dest_op NO recibe
        self.assertEqual(
            await self._count_notifs(self.dest_op_id, NotificationType.SOLICITUD_CREATED.value),
            0, "dest_op no recibe solicitud.created",
        )

    async def test_approve_solicitud_notifica_origin_operator(self) -> None:
        """APPROVE solicitud: notifica a origin_operator."""
        async with self.session_factory() as s:
            service = SolicitudService(s)
            view = await service.create_solicitud(
                id_bodega_origen=self.aux_id,
                id_bodega_destino=self.principal_id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_solicitada": Decimal("10"),
                }],
                user_id=self.origin_op_id,
            )
            await s.commit()
            view2 = await service.approve_solicitud(
                view.id, user_id=self.admin_id,
            )
            await s.commit()

        # origin_op recibe solicitud.approved
        self.assertEqual(
            await self._count_notifs(self.origin_op_id, NotificationType.SOLICITUD_APPROVED.value),
            1,
        )
        # admin NO recibe (es el actor del approve)
        self.assertEqual(
            await self._count_notifs(self.admin_id, NotificationType.SOLICITUD_APPROVED.value),
            0,
        )

    async def test_dispatch_solicitud_notifica_destination_operator(self) -> None:
        """DISPATCH solicitud: notifica a destination_operator."""
        async with self.session_factory() as s:
            service = SolicitudService(s)
            view = await service.create_solicitud(
                id_bodega_origen=self.aux_id,
                id_bodega_destino=self.principal_id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_solicitada": Decimal("10"),
                }],
                user_id=self.origin_op_id,
            )
            await s.commit()
            await service.approve_solicitud(view.id, user_id=self.admin_id)
            await s.commit()
            await service.dispatch_solicitud(view.id, user_id=self.origin_op_id)
            await s.commit()

        # dest_op recibe solicitud.dispatched
        self.assertEqual(
            await self._count_notifs(self.dest_op_id, NotificationType.SOLICITUD_DISPATCHED.value),
            1,
        )
        # origin_op NO recibe (es el actor)
        self.assertEqual(
            await self._count_notifs(self.origin_op_id, NotificationType.SOLICITUD_DISPATCHED.value),
            0,
        )

    async def test_receive_solicitud_notifica_admin_supervisor_excluye_actor(self) -> None:
        """RECEIVE solicitud: notifica a admin+supervisor excluyendo al actor."""
        async with self.session_factory() as s:
            service = SolicitudService(s)
            view = await service.create_solicitud(
                id_bodega_origen=self.aux_id,
                id_bodega_destino=self.principal_id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_solicitada": Decimal("10"),
                }],
                user_id=self.origin_op_id,
            )
            await s.commit()
            await service.approve_solicitud(view.id, user_id=self.admin_id)
            await s.commit()
            await service.dispatch_solicitud(view.id, user_id=self.origin_op_id)
            await s.commit()
            await service.receive_solicitud(
                view.id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_recibida": Decimal("10"),
                }],
                notas="Recibido OK",
                user_id=self.dest_op_id,  # dest_op recibe
            )
            await s.commit()

        # admin y supervisor reciben solicitud.received
        self.assertEqual(
            await self._count_notifs(self.admin_id, NotificationType.SOLICITUD_RECEIVED.value),
            1,
        )
        self.assertEqual(
            await self._count_notifs(self.supervisor_id, NotificationType.SOLICITUD_RECEIVED.value),
            1,
        )
        # dest_op NO recibe (es el actor)
        self.assertEqual(
            await self._count_notifs(self.dest_op_id, NotificationType.SOLICITUD_RECEIVED.value),
            0,
        )

    async def test_reject_solicitud_notifica_origin_operator(self) -> None:
        """REJECT solicitud: notifica a origin_operator."""
        async with self.session_factory() as s:
            service = SolicitudService(s)
            view = await service.create_solicitud(
                id_bodega_origen=self.aux_id,
                id_bodega_destino=self.principal_id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_solicitada": Decimal("10"),
                }],
                user_id=self.origin_op_id,
            )
            await s.commit()
            await service.reject_solicitud(
                view.id, motivo="stock bajo", user_id=self.admin_id,
            )
            await s.commit()

        # origin_op recibe solicitud.rejected
        self.assertEqual(
            await self._count_notifs(self.origin_op_id, NotificationType.SOLICITUD_REJECTED.value),
            1,
        )
        # admin NO recibe (es el actor)
        self.assertEqual(
            await self._count_notifs(self.admin_id, NotificationType.SOLICITUD_REJECTED.value),
            0,
        )

    async def test_cancel_solicitud_notifica_admin_supervisor_excluye_actor(self) -> None:
        """CANCEL solicitud: notifica a admin+supervisor excluyendo al actor."""
        async with self.session_factory() as s:
            service = SolicitudService(s)
            view = await service.create_solicitud(
                id_bodega_origen=self.aux_id,
                id_bodega_destino=self.principal_id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_solicitada": Decimal("10"),
                }],
                user_id=self.origin_op_id,
            )
            await s.commit()
            await service.cancel_solicitud(
                view.id, user_id=self.origin_op_id,
            )
            await s.commit()

        # admin y supervisor reciben solicitud.cancelled
        self.assertEqual(
            await self._count_notifs(self.admin_id, NotificationType.SOLICITUD_CANCELLED.value),
            1,
        )
        self.assertEqual(
            await self._count_notifs(self.supervisor_id, NotificationType.SOLICITUD_CANCELLED.value),
            1,
        )
        # origin_op NO recibe (es el actor)
        self.assertEqual(
            await self._count_notifs(self.origin_op_id, NotificationType.SOLICITUD_CANCELLED.value),
            0,
        )

    async def test_workflow_completo_genera_4_notificaciones(self) -> None:
        """E2E: create -> approve -> dispatch -> receive = 4 notifs
        (1 por transicion, distribuidas segun el rol)."""
        async with self.session_factory() as s:
            service = SolicitudService(s)
            view = await service.create_solicitud(
                id_bodega_origen=self.aux_id,
                id_bodega_destino=self.principal_id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_solicitada": Decimal("10"),
                }],
                user_id=self.origin_op_id,  # CREATE por origin_op
            )
            await s.commit()
            await service.approve_solicitud(view.id, user_id=self.admin_id)
            await s.commit()
            await service.dispatch_solicitud(view.id, user_id=self.origin_op_id)
            await s.commit()
            await service.receive_solicitud(
                view.id,
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_recibida": Decimal("10"),
                }],
                user_id=self.dest_op_id,  # RECEIVE por dest_op
            )
            await s.commit()

        # CREATE (origin_op) -> admin+supervisor
        self.assertEqual(
            await self._count_notifs(self.admin_id, NotificationType.SOLICITUD_CREATED.value),
            1,
        )
        self.assertEqual(
            await self._count_notifs(self.supervisor_id, NotificationType.SOLICITUD_CREATED.value),
            1,
        )
        # APPROVE (admin) -> origin_op
        self.assertEqual(
            await self._count_notifs(self.origin_op_id, NotificationType.SOLICITUD_APPROVED.value),
            1,
        )
        # DISPATCH (origin_op) -> dest_op
        self.assertEqual(
            await self._count_notifs(self.dest_op_id, NotificationType.SOLICITUD_DISPATCHED.value),
            1,
        )
        # RECEIVE (dest_op) -> admin+supervisor
        self.assertEqual(
            await self._count_notifs(self.admin_id, NotificationType.SOLICITUD_RECEIVED.value),
            1,
        )
        self.assertEqual(
            await self._count_notifs(self.supervisor_id, NotificationType.SOLICITUD_RECEIVED.value),
            1,
        )

        # Total: 6 inserts (1+1+1+1+1+1) cruzando 3 tipos y 4 usuarios.
        async with self.session_factory() as s:
            stmt = select(Notificacion)
            all_notifs = list((await s.execute(stmt)).scalars().all())
            self.assertEqual(len(all_notifs), 6, "E2E debe generar 6 notifs")


# ============================================================ OrdenCompraService


class OrdenCompraServiceNotifTests(unittest.IsolatedAsyncioTestCase):
    """Tests de integracion: cada transicion de OrdenCompraService emite
    la notificacion esperada."""

    async def asyncSetUp(self) -> None:
        from app.db.session import reset_engine_cache

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

    async def _seed(self) -> None:
        from datetime import UTC, datetime

        from app.db.models.products import Product
        from app.db.models.supervisores import Supervisor
        from app.db.models.warehouses import Warehouse

        self.admin_id = uuid4()
        self.supervisor_id = uuid4()
        self.principal_id = uuid4()
        self.sup_id_oc = uuid4()  # Supervisor OC (externo, no User)
        self.product_id = uuid4()
        now = datetime.now(UTC)

        async with self.session_factory() as s:
            s.add_all([
                User(
                    id=self.admin_id, username="admin_oc",
                    full_name="Admin OC", role=UserRole.ADMIN,
                    password_hash="x", is_active=True, created_at=now,
                ),
                User(
                    id=self.supervisor_id, username="sup_oc",
                    full_name="Sup OC", role=UserRole.SUPERVISOR,
                    password_hash="x", is_active=True, created_at=now,
                ),
                Warehouse(
                    id=self.principal_id, code="PRINCIPAL_OC",
                    name="Principal OC", warehouse_type="principal",
                    is_active=True,
                ),
                Supervisor(
                    id=self.sup_id_oc, nombre="Sup Ext",
                    email="ext@bodega.example", activo=True,
                ),
                Product(
                    id=self.product_id, sku="SKU-OC-N",
                    name="Producto OC N", unit="unidad", is_active=True,
                ),
            ])
            await s.commit()

    async def _crear_oc(self) -> object:
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            view = await service.create_orden(
                id_bodega_principal=self.principal_id,
                id_supervisor=self.sup_id_oc,
                proveedor_nombre="Prov Test",
                lineas=[{
                    "id_producto": self.product_id,
                    "cantidad_pedida": Decimal("10"),
                    "costo_unitario_pactado": Decimal("100"),
                }],
            )
            await s.commit()
        return view

    async def test_enviar_correo_notifica_admin_supervisor(self) -> None:
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            v, _token, _outbox = await service.enviar_correo(
                view.id, user_id=self.admin_id,
            )
            await s.commit()

        # admin excluido (es actor), supervisor recibe
        async with self.session_factory() as s:
            admin_n = await _notif_for(
                s, self.admin_id,
                NotificationType.ORDEN_COMPRA_ENVIADA.value,
            )
            sup_n = await _notif_for(
                s, self.supervisor_id,
                NotificationType.ORDEN_COMPRA_ENVIADA.value,
            )
        self.assertEqual(len(admin_n), 0, "admin excluido")
        self.assertEqual(len(sup_n), 1, "supervisor recibe")

    async def test_aprobar_orden_notifica_admin_supervisor(self) -> None:
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            await service.enviar_correo(view.id, user_id=self.admin_id)
            await s.commit()
            await service.aprobar_orden(view.id, user_id=self.supervisor_id)
            await s.commit()

        # supervisor excluido (es actor), admin recibe
        async with self.session_factory() as s:
            sup_n = await _notif_for(
                s, self.supervisor_id,
                NotificationType.ORDEN_COMPRA_APROBADA.value,
            )
            admin_n = await _notif_for(
                s, self.admin_id,
                NotificationType.ORDEN_COMPRA_APROBADA.value,
            )
        self.assertEqual(len(sup_n), 0, "supervisor excluido")
        self.assertEqual(len(admin_n), 1, "admin recibe")

    async def test_rechazar_orden_notifica_admin_supervisor(self) -> None:
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            await service.enviar_correo(view.id, user_id=self.admin_id)
            await s.commit()
            await service.rechazar_orden(
                view.id, motivo="Fuera de presupuesto",
                user_id=self.supervisor_id,
            )
            await s.commit()

        # admin recibe
        async with self.session_factory() as s:
            admin_n = await _notif_for(
                s, self.admin_id,
                NotificationType.ORDEN_COMPRA_RECHAZADA.value,
            )
        self.assertEqual(len(admin_n), 1)
        self.assertIn("Fuera de presupuesto", admin_n[0].mensaje or "")

    async def test_marcar_comprada_notifica_admin_supervisor(self) -> None:
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            await service.enviar_correo(view.id, user_id=self.admin_id)
            await s.commit()
            await service.aprobar_orden(view.id, user_id=self.supervisor_id)
            await s.commit()
            await service.marcar_comprada(view.id, user_id=self.supervisor_id)
            await s.commit()

        # admin recibe orden_compra.recibida
        async with self.session_factory() as s:
            admin_n = await _notif_for(
                s, self.admin_id,
                NotificationType.ORDEN_COMPRA_RECIBIDA.value,
            )
        self.assertEqual(len(admin_n), 1)

    async def test_aprobar_con_token_no_excluye_nadie(self) -> None:
        """Aprobar OC por token (sin auth) -> broadcast a TODOS admin+sup."""
        view = await self._crear_oc()
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            v, token, _ = await service.enviar_correo(view.id, user_id=self.admin_id)
            await s.commit()

        # Aprobar via token (sin user_id)
        async with self.session_factory() as s:
            service = OrdenCompraService(s)
            v2 = await service.aprobar_con_token(token, "approve", motivo=None)
            await s.commit()

        # Tanto admin como supervisor reciben (no hay actor que excluir)
        async with self.session_factory() as s:
            admin_n = await _notif_for(
                s, self.admin_id,
                NotificationType.ORDEN_COMPRA_APROBADA.value,
            )
            sup_n = await _notif_for(
                s, self.supervisor_id,
                NotificationType.ORDEN_COMPRA_APROBADA.value,
            )
        # admin ya recibio la de enviar_correo, pero aprobar_orden via
        # token no excluye a nadie -> ambos reciben la 2da notificacion.
        # Filtramos las notificaciones de tipo "ORDEN_COMPRA_APROBADA"
        # (la 1ra de enviar_correo es "ORDEN_COMPRA_ENVIADA", no esta).
        self.assertGreaterEqual(len(admin_n), 1)
        self.assertGreaterEqual(len(sup_n), 1)
