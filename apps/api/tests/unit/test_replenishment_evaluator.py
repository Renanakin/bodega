"""
Tests del ReplenishmentEvaluator (Fase 4).

Cubre:
- Happy path vacio (ningun bajo minimo).
- Happy path con 1 producto bajo minimo.
- Cantidad sugerida: usa max_quantity si esta definido.
- Cantidad sugerida: usa min_quantity * 2 si max es NULL.
- Idempotencia: si ya hay solicitud PENDING, omite.
- Solo bodegas tipo 'auxiliar' (NO principal, NO mecanico_box).
- Solo productos activos (is_active=True).
- Prioridad: 'alta' si quantity < min/2, 'normal' en caso contrario.
- dry_run=True no crea solicitud.
- evaluate_one(warehouse_id) evalua solo una bodega.

Patron: unittest.IsolatedAsyncioTestCase con AsyncEngine SQLite
+ StaticPool (mismo patron que test_solicitudes.py).
"""

from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

# Configurar el AsyncEngine antes de importar la app
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.config import reset_settings_cache  # noqa: E402
from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.modules.solicitudes.replenishment import (  # noqa: E402
    ReplenishmentEvaluator,
    _calcular_cantidad,
    _calcular_prioridad,
)
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

reset_settings_cache()


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


class ReplenishmentTestBase(unittest.IsolatedAsyncioTestCase):
    """Base con el setup comun: engine, factory, bodegas, productos."""

    async def asyncSetUp(self) -> None:
        from app.db.session import reset_engine_cache

        reset_engine_cache()
        self.engine = _create_test_engine()
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        await self._seed_demo_data()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        from app.db.session import reset_engine_cache

        reset_engine_cache()

    async def _seed_demo_data(self) -> None:
        """Crea principal + 2 auxiliares + 1 box + 5 productos + stock.

        Productos:
            p1, p2, p3: activos
            p4, p5:      activos
            p_inactivo:  inactivo

        Stock en AUX-1 (bodega_origen_id):
            - p1: 3 / min 10  (BAJO minimo, ratio 0.3 → 'alta')
            - p2: 5 / min 10 / max 50  (BAJO minimo, ratio 0.5 → 'normal' borderline)
            - p3: 8 / min 5   (sobre minimo, no debe aparecer)
            - p4: 2 / min 5   (BAJO minimo, ratio 0.4 → 'alta')
            - p5: 12 / min 5  (sobre minimo, no debe aparecer)
            - p_inactivo: 1 / min 5  (BAJO, pero producto inactivo → skip)

        Stock en AUX-2: sin stock bajo minimo.
        Stock en BOX-1 (hijo de AUX-1): sin stock bajo minimo.
        """
        from app.db.models.inventory import StockLevel
        from app.db.models.products import Product
        from app.db.models.warehouses import Warehouse

        # Warehouses
        self.principal_id = uuid4()
        self.aux1_id = uuid4()
        self.aux2_id = uuid4()
        self.box1_id = uuid4()  # mecanico_box hijo de aux1

        async with self.session_factory() as session:
            # Etapa 1: warehouses. Flush para que los FKs de productos/stock
            # puedan resolver las referencias.
            session.add_all(
                [
                    Warehouse(
                        id=self.principal_id,
                        code="PRINCIPAL",
                        name="Bodega Principal",
                        warehouse_type="principal",
                        is_active=True,
                    ),
                    Warehouse(
                        id=self.aux1_id,
                        code="AUX-1",
                        name="Auxiliar Taller 1",
                        warehouse_type="auxiliar",
                        is_active=True,
                    ),
                    Warehouse(
                        id=self.aux2_id,
                        code="AUX-2",
                        name="Auxiliar Taller 2",
                        warehouse_type="auxiliar",
                        is_active=True,
                    ),
                    Warehouse(
                        id=self.box1_id,
                        code="BOX-1",
                        name="Box Mecanico 1",
                        warehouse_type="mecanico_box",
                        is_active=True,
                        parent_warehouse_id=self.aux1_id,
                    ),
                ]
            )
            await session.flush()

            # Etapa 2: productos. Flush antes de los stock_levels.
            self.p1_id = uuid4()
            self.p2_id = uuid4()
            self.p3_id = uuid4()
            self.p4_id = uuid4()
            self.p5_id = uuid4()
            self.p_inactivo_id = uuid4()
            session.add_all(
                [
                    Product(
                        id=self.p1_id,
                        sku="SKU-001",
                        name="Filtro de aire",
                        unit="unidad",
                        is_active=True,
                    ),
                    Product(
                        id=self.p2_id,
                        sku="SKU-002",
                        name="Aceite 5W30",
                        unit="litro",
                        is_active=True,
                    ),
                    Product(
                        id=self.p3_id, sku="SKU-003", name="Bujia", unit="unidad", is_active=True
                    ),
                    Product(
                        id=self.p4_id,
                        sku="SKU-004",
                        name="Pastilla freno",
                        unit="unidad",
                        is_active=True,
                    ),
                    Product(
                        id=self.p5_id,
                        sku="SKU-005",
                        name="Refrigerante",
                        unit="litro",
                        is_active=True,
                    ),
                    Product(
                        id=self.p_inactivo_id,
                        sku="SKU-INACTIVO",
                        name="Obsoleto",
                        unit="unidad",
                        is_active=False,
                    ),
                ]
            )
            await session.flush()

            now = datetime.now(UTC)
            # AUX-1: varios stocks bajo minimo + normales
            session.add_all(
                [
                    # p1: bajo minimo, ratio 0.3 → prioridad 'alta', sin max → fallback min*2
                    StockLevel(
                        warehouse_id=self.aux1_id,
                        product_id=self.p1_id,
                        quantity=Decimal("3"),
                        min_quantity=Decimal("10"),
                        max_quantity=None,
                        updated_at=now,
                    ),
                    # p2: bajo minimo, ratio 0.5, max=50 → sugerido = 50 - 5 = 45
                    StockLevel(
                        warehouse_id=self.aux1_id,
                        product_id=self.p2_id,
                        quantity=Decimal("5"),
                        min_quantity=Decimal("10"),
                        max_quantity=Decimal("50"),
                        updated_at=now,
                    ),
                    # p3: sobre minimo, no debe procesarse
                    StockLevel(
                        warehouse_id=self.aux1_id,
                        product_id=self.p3_id,
                        quantity=Decimal("8"),
                        min_quantity=Decimal("5"),
                        max_quantity=None,
                        updated_at=now,
                    ),
                    # p4: bajo minimo, ratio 0.4 → 'alta', sin max
                    StockLevel(
                        warehouse_id=self.aux1_id,
                        product_id=self.p4_id,
                        quantity=Decimal("2"),
                        min_quantity=Decimal("5"),
                        max_quantity=None,
                        updated_at=now,
                    ),
                    # p5: sobre minimo, no debe procesarse
                    StockLevel(
                        warehouse_id=self.aux1_id,
                        product_id=self.p5_id,
                        quantity=Decimal("12"),
                        min_quantity=Decimal("5"),
                        max_quantity=None,
                        updated_at=now,
                    ),
                    # p_inactivo: bajo minimo pero producto inactivo → skip
                    StockLevel(
                        warehouse_id=self.aux1_id,
                        product_id=self.p_inactivo_id,
                        quantity=Decimal("1"),
                        min_quantity=Decimal("5"),
                        max_quantity=None,
                        updated_at=now,
                    ),
                    # AUX-2: nada bajo minimo
                    StockLevel(
                        warehouse_id=self.aux2_id,
                        product_id=self.p1_id,
                        quantity=Decimal("50"),
                        min_quantity=Decimal("5"),
                        max_quantity=None,
                        updated_at=now,
                    ),
                ]
            )
            await session.commit()

    def _new_session(self) -> AsyncSession:
        return self.session_factory()


class TestReplenishmentHelpers(unittest.IsolatedAsyncioTestCase):
    """Tests de las funciones puras de calculo (sin BD)."""

    def test_calcular_cantidad_con_max_definido(self) -> None:
        """max - actual cuando max esta definido."""
        from uuid import uuid4

        from app.db.models.inventory import StockLevel

        sl = StockLevel(
            id=uuid4(),
            warehouse_id=uuid4(),
            product_id=uuid4(),
            quantity=Decimal("5"),
            min_quantity=Decimal("10"),
            max_quantity=Decimal("50"),
            updated_at=datetime.now(UTC),
        )
        self.assertEqual(_calcular_cantidad(sl), Decimal("45"))

    def test_calcular_cantidad_sin_max_usa_min_x2(self) -> None:
        """Si max es NULL: min*2 - actual."""
        from uuid import uuid4

        from app.db.models.inventory import StockLevel

        sl = StockLevel(
            id=uuid4(),
            warehouse_id=uuid4(),
            product_id=uuid4(),
            quantity=Decimal("3"),
            min_quantity=Decimal("10"),
            max_quantity=None,
            updated_at=datetime.now(UTC),
        )
        # 10*2 - 3 = 17
        self.assertEqual(_calcular_cantidad(sl), Decimal("17"))

    def test_calcular_cantidad_no_negativa(self) -> None:
        """Si current > target, retorna 0 (caller debe skipear)."""
        from uuid import uuid4

        from app.db.models.inventory import StockLevel

        sl = StockLevel(
            id=uuid4(),
            warehouse_id=uuid4(),
            product_id=uuid4(),
            quantity=Decimal("100"),
            min_quantity=Decimal("10"),
            max_quantity=Decimal("20"),
            updated_at=datetime.now(UTC),
        )
        self.assertEqual(_calcular_cantidad(sl), Decimal("0"))

    def test_calcular_prioridad_alta_si_menor_a_50_por_ciento(self) -> None:
        from uuid import uuid4

        from app.db.models.inventory import StockLevel

        sl = StockLevel(
            id=uuid4(),
            warehouse_id=uuid4(),
            product_id=uuid4(),
            quantity=Decimal("3"),
            min_quantity=Decimal("10"),
            max_quantity=None,
            updated_at=datetime.now(UTC),
        )
        # ratio 0.3 < 0.5
        self.assertEqual(_calcular_prioridad(sl), "alta")

    def test_calcular_prioridad_normal_si_sobre_50_por_ciento(self) -> None:
        from uuid import uuid4

        from app.db.models.inventory import StockLevel

        sl = StockLevel(
            id=uuid4(),
            warehouse_id=uuid4(),
            product_id=uuid4(),
            quantity=Decimal("6"),
            min_quantity=Decimal("10"),
            max_quantity=None,
            updated_at=datetime.now(UTC),
        )
        # ratio 0.6 >= 0.5
        self.assertEqual(_calcular_prioridad(sl), "normal")

    def test_calcular_prioridad_normal_si_min_es_cero(self) -> None:
        """Edge case: min_quantity=0 → no dividir por cero → 'normal'."""
        from uuid import uuid4

        from app.db.models.inventory import StockLevel

        sl = StockLevel(
            id=uuid4(),
            warehouse_id=uuid4(),
            product_id=uuid4(),
            quantity=Decimal("0"),
            min_quantity=Decimal("0"),
            max_quantity=None,
            updated_at=datetime.now(UTC),
        )
        self.assertEqual(_calcular_prioridad(sl), "normal")


class TestReplenishmentEvaluatorHappyPath(ReplenishmentTestBase):
    """Tests del flujo principal con datos reales."""

    async def test_evaluar_sin_productos_bajo_minimo_no_crea_solicitud(self) -> None:
        """Si todo el stock esta sobre el minimo, no crea nada."""
        # Mover todo el stock de AUX-1 sobre el minimo
        async with self.session_factory() as session:
            from app.db.models.inventory import StockLevel
            from sqlalchemy import update

            await session.execute(
                update(StockLevel)
                .where(StockLevel.warehouse_id == self.aux1_id)
                .values(quantity=StockLevel.min_quantity + 10)
            )
            await session.commit()

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_all()
            await session.commit()

        self.assertEqual(report.solicitudes_creadas, 0)
        self.assertEqual(report.skus_bajo_minimo, 0)
        self.assertEqual(report.bodegas_evaluadas, 2)
        self.assertEqual(report.errores, [])

    async def test_evaluar_con_productos_bajo_minimo_crea_1_solicitud(self) -> None:
        """AUX-1 tiene 3 SKUs bajo minimo (p1, p2, p4). El Evaluator
        crea UNA sola solicitud con 3 lineas, dirigida a PRINCIPAL."""
        from app.db.models.solicitudes import DetalleSolicitudRecarga, SolicitudRecarga
        from sqlalchemy import func, select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_all()
            await session.commit()

        self.assertEqual(report.bodegas_evaluadas, 2)
        # skus_bajo_minimo = 4 (p1, p2, p4 activos + p_inactivo).
        # El Evaluator cuenta TODOS los stocks bajo minimo, incluyendo
        # inactivos; los inactivos se filtran despues al construir lineas.
        self.assertEqual(report.skus_bajo_minimo, 4)
        self.assertEqual(report.solicitudes_creadas, 1)
        self.assertEqual(report.solicitudes_omitidas_pendientes, 0)
        self.assertEqual(report.errores, [])

        # Verificar la solicitud creada
        async with self.session_factory() as session:
            stmt = select(SolicitudRecarga)
            result = await session.execute(stmt)
            solicitudes = list(result.scalars().all())
            self.assertEqual(len(solicitudes), 1)
            sol = solicitudes[0]
            self.assertEqual(sol.estado.value, "pending")
            self.assertEqual(sol.id_bodega_origen, self.aux1_id)
            self.assertEqual(sol.id_bodega_destino, self.principal_id)
            self.assertEqual(sol.prioridad, "alta")  # hay al menos 1 linea con prioridad alta
            self.assertIn("ReplenishmentEvaluator", sol.notas or "")

            # Detalles: 3 lineas (p_inactivo NO aparece)
            detalles = list(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(DetalleSolicitudRecarga)
                        .where(DetalleSolicitudRecarga.id_solicitud == sol.id)
                    )
                ).scalars()
            )
            self.assertEqual(detalles[0], 3)

    async def test_evaluar_usa_max_quantity_si_esta_definido(self) -> None:
        """p2 tiene max=50, actual=5 → sugerido = 45."""
        from app.db.models.solicitudes import DetalleSolicitudRecarga
        from sqlalchemy import select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            await evaluator.evaluate_all()
            await session.commit()

        async with self.session_factory() as session:
            stmt = select(DetalleSolicitudRecarga).where(
                DetalleSolicitudRecarga.id_producto == self.p2_id
            )
            detalle = (await session.execute(stmt)).scalars().first()
            self.assertIsNotNone(detalle)
            # p2: max 50 - actual 5 = 45
            self.assertEqual(detalle.cantidad_solicitada, Decimal("45"))

    async def test_evaluar_usa_min_quantity_x2_si_max_es_null(self) -> None:
        """p1 y p4 tienen max=NULL → sugerido = min*2 - actual."""
        from app.db.models.solicitudes import DetalleSolicitudRecarga
        from sqlalchemy import select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            await evaluator.evaluate_all()
            await session.commit()

        async with self.session_factory() as session:
            stmt = select(DetalleSolicitudRecarga).where(
                DetalleSolicitudRecarga.id_producto.in_([self.p1_id, self.p4_id])
            )
            detalles = {d.id_producto: d for d in (await session.execute(stmt)).scalars().all()}

        # p1: min 10 * 2 - 3 = 17
        self.assertEqual(detalles[self.p1_id].cantidad_solicitada, Decimal("17"))
        # p4: min 5 * 2 - 2 = 8
        self.assertEqual(detalles[self.p4_id].cantidad_solicitada, Decimal("8"))

    async def test_evaluar_no_crea_solicitud_si_ya_hay_pendiente(self) -> None:
        """Idempotencia R6: si ya hay PENDING desde esa bodega, omite."""
        from app.db.models.solicitudes import SolicitudEstado, SolicitudRecarga
        from sqlalchemy import select

        # Crear manualmente una solicitud PENDING desde AUX-1
        async with self.session_factory() as session:
            session.add(
                SolicitudRecarga(
                    id=uuid4(),
                    codigo="SOL-EXISTENTE-0001",
                    id_bodega_origen=self.aux1_id,
                    id_bodega_destino=self.principal_id,
                    estado=SolicitudEstado.PENDING,
                    prioridad="normal",
                    notas="Solicitud preexistente",
                )
            )
            await session.commit()

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_all()
            await session.commit()

        self.assertEqual(report.solicitudes_creadas, 0)
        self.assertEqual(report.solicitudes_omitidas_pendientes, 1)
        # skus_bajo_minimo = 0: cuando una bodega se omite por tener
        # PENDING, salimos antes de contar stocks bajo minimo (no se
        # "consideran" para reposicion). AUX-2 no tiene bajo minimo.
        self.assertEqual(report.skus_bajo_minimo, 0)

        # Solo debe existir 1 solicitud (la preexistente)
        async with self.session_factory() as session:
            count = (await session.execute(select(SolicitudRecarga))).scalars().all()
            self.assertEqual(len(count), 1)

    async def test_evaluar_solo_procesa_bodegas_auxiliares(self) -> None:
        """El Evaluator NO crea solicitudes desde Principal ni desde Boxes."""
        from app.db.models.inventory import StockLevel
        from app.db.models.solicitudes import SolicitudRecarga
        from sqlalchemy import select

        # Crear stock bajo minimo en PRINCIPAL y en BOX-1
        async with self.session_factory() as session:
            # Stock bajo minimo en Principal
            session.add(
                StockLevel(
                    warehouse_id=self.principal_id,
                    product_id=self.p1_id,
                    quantity=Decimal("0"),
                    min_quantity=Decimal("10"),
                    max_quantity=None,
                    updated_at=datetime.now(UTC),
                )
            )
            # Stock bajo minimo en BOX-1 (hijo de aux1)
            session.add(
                StockLevel(
                    warehouse_id=self.box1_id,
                    product_id=self.p1_id,
                    quantity=Decimal("0"),
                    min_quantity=Decimal("10"),
                    max_quantity=None,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_all()
            await session.commit()

        # Solo debe haber 1 solicitud (la de AUX-1)
        self.assertEqual(report.solicitudes_creadas, 1)
        async with self.session_factory() as session:
            solicitudes = (await session.execute(select(SolicitudRecarga))).scalars().all()
            self.assertEqual(len(solicitudes), 1)
            self.assertEqual(solicitudes[0].id_bodega_origen, self.aux1_id)

    async def test_evaluar_solo_procesa_productos_activos(self) -> None:
        """Productos con is_active=False son skipeados aunque esten bajo minimo."""
        from app.db.models.solicitudes import DetalleSolicitudRecarga
        from sqlalchemy import select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            await evaluator.evaluate_all()
            await session.commit()

        async with self.session_factory() as session:
            stmt = select(DetalleSolicitudRecarga).where(
                DetalleSolicitudRecarga.id_producto == self.p_inactivo_id
            )
            detalle = (await session.execute(stmt)).scalars().first()
            self.assertIsNone(detalle)  # producto inactivo NO aparece

    async def test_evaluar_asigna_prioridad_alta_si_stock_menor_a_min_50_por_ciento(self) -> None:
        """Si hay al menos 1 linea con ratio < 0.5, prioridad final = 'alta'."""
        from app.db.models.solicitudes import SolicitudRecarga
        from sqlalchemy import select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            await evaluator.evaluate_all()
            await session.commit()

        async with self.session_factory() as session:
            sol = (await session.execute(select(SolicitudRecarga))).scalars().first()
            self.assertEqual(sol.prioridad, "alta")
            # p1 ratio=0.3 (<0.5 → alta), p4 ratio=0.4 (<0.5 → alta)
            # p2 ratio=0.5 (border, normal). Gana 'alta'.

    async def test_evaluar_dry_run_no_crea_solicitud(self) -> None:
        """dry_run=True evalua y reporta pero NO persiste solicitudes."""
        from app.db.models.solicitudes import SolicitudRecarga
        from sqlalchemy import func, select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_all(dry_run=True)
            await session.commit()

        self.assertTrue(report.dry_run)
        # En dry_run, contamos como "hubiera creado" para reportar impacto
        self.assertEqual(report.solicitudes_creadas, 1)
        # skus_bajo_minimo = 4 (p1, p2, p4, p_inactivo) — incluye inactivos
        self.assertEqual(report.skus_bajo_minimo, 4)

        # Pero la BD no debe tener solicitudes nuevas
        async with self.session_factory() as session:
            count = (
                await session.execute(select(func.count()).select_from(SolicitudRecarga))
            ).scalar()
            self.assertEqual(count, 0)

    async def test_evaluar_un_warehouse_especifico(self) -> None:
        """evaluate_one(warehouse_id) evalua solo esa bodega."""
        from app.db.models.inventory import StockLevel
        from app.db.models.solicitudes import SolicitudRecarga
        from sqlalchemy import select

        # Crear stock bajo minimo tambien en AUX-2
        async with self.session_factory() as session:
            session.add(
                StockLevel(
                    warehouse_id=self.aux2_id,
                    product_id=self.p2_id,
                    quantity=Decimal("1"),
                    min_quantity=Decimal("10"),
                    max_quantity=None,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()

        # evaluate_one sobre AUX-1
        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_one(self.aux1_id)
            await session.commit()

        self.assertEqual(report.bodegas_evaluadas, 1)
        self.assertEqual(report.solicitudes_creadas, 1)

        # Solo debe existir 1 solicitud (la de AUX-1, NO la de AUX-2)
        async with self.session_factory() as session:
            solicitudes = (await session.execute(select(SolicitudRecarga))).scalars().all()
            self.assertEqual(len(solicitudes), 1)
            self.assertEqual(solicitudes[0].id_bodega_origen, self.aux1_id)

    async def test_evaluar_uno_warehouse_inexistente_retorna_error(self) -> None:
        """evaluate_one con UUID inexistente retorna reporte con error."""
        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_one(uuid4())
            await session.commit()

        # bodegas_evaluadas = 0 (no encontro la bodega, salio antes)
        self.assertEqual(report.bodegas_evaluadas, 0)
        self.assertEqual(len(report.errores), 1)
        self.assertIn("no encontrada", report.errores[0].lower())

    async def test_evaluar_uno_warehouse_principal_retorna_error(self) -> None:
        """evaluate_one sobre Principal NO crea solicitud; lo reporta como error."""
        from app.db.models.solicitudes import SolicitudRecarga
        from sqlalchemy import func, select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_one(self.principal_id)
            await session.commit()

        # bodegas_evaluadas = 1 (se intento evaluar, pero no era tipo
        # 'auxiliar' → se reporta error y no se procesa)
        self.assertEqual(report.bodegas_evaluadas, 1)
        self.assertEqual(len(report.errores), 1)
        self.assertIn("auxiliar", report.errores[0].lower())
        self.assertEqual(report.solicitudes_creadas, 0)

        async with self.session_factory() as session:
            count = (
                await session.execute(select(func.count()).select_from(SolicitudRecarga))
            ).scalar()
            self.assertEqual(count, 0)

    async def test_evaluar_uno_warehouse_box_retorna_error(self) -> None:
        """evaluate_one sobre Box (mecanico_box) NO crea solicitud."""
        from app.db.models.solicitudes import SolicitudRecarga
        from sqlalchemy import func, select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_one(self.box1_id)
            await session.commit()

        # bodegas_evaluadas = 1 (se intento, pero no era 'auxiliar')
        self.assertEqual(report.bodegas_evaluadas, 1)
        self.assertEqual(len(report.errores), 1)
        self.assertEqual(report.solicitudes_creadas, 0)
        async with self.session_factory() as session:
            count = (
                await session.execute(select(func.count()).select_from(SolicitudRecarga))
            ).scalar()
            self.assertEqual(count, 0)

    async def test_evaluar_dry_run_para_bodega_especifica(self) -> None:
        """evaluate_one con dry_run=True evalua pero no persiste."""
        from app.db.models.solicitudes import SolicitudRecarga
        from sqlalchemy import func, select

        async with self.session_factory() as session:
            evaluator = ReplenishmentEvaluator(session)
            report = await evaluator.evaluate_one(self.aux1_id, dry_run=True)
            await session.commit()

        self.assertTrue(report.dry_run)
        self.assertEqual(report.solicitudes_creadas, 1)
        async with self.session_factory() as session:
            count = (
                await session.execute(select(func.count()).select_from(SolicitudRecarga))
            ).scalar()
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
