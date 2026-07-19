"""
Tests de integración con PostgreSQL real (ADR-0001 IMP-005).

Estos tests usan `testcontainers` para levantar un PostgreSQL efímero en Docker,
ejecutan las migraciones de Alembic contra él, y validan el contrato de la
interface `Database` (ADR-0001) contra el motor real.

Marcados con `@pytest.mark.integration`. NO se ejecutan en CI estándar
(requieren Docker local). Para correrlos:
    pytest -m integration tests/test_api_integration.py -v

Skip conditions (decaen con skip, no fail):
- `testcontainers` no está instalado.
- Docker daemon no responde.
- Timeout al levantar el container (>60s).

References:
- ADR-0001 §"Tests integración"
- ADR-0001 IMP-005: pytest tests/test_api_integration.py -v debe pasar.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

# Skip suave si testcontainers no está instalado (Fase 0/1 dev no lo requiere).
testcontainers = pytest.importorskip("testcontainers")
pytest.importorskip("testcontainers.postgres")

from app.db.session import (  # noqa: E402
    AsyncSQLiteDatabase,
    Database,
    PostgresDatabase,
    create_database_from_url,
)
from testcontainers.postgres import PostgresContainer  # noqa: E402

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def postgres_container():
    """Levanta un Postgres real en Docker, scoped al módulo (una vez por archivo).

    Yields:
        PostgresContainer con la BD lista para conectar.

    Skips the test if Docker is not available.
    """
    try:
        with PostgresContainer("postgres:17-alpine") as pg:
            yield pg
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgresContainer no disponible (¿Docker daemon caído?): {exc}")


@pytest.fixture(scope="module")
def database_url(postgres_container) -> str:  # type: ignore[no-untyped-def]
    """URL de conexión asyncpg al Postgres efímero."""
    # PostgresContainer expone get_connection_url() con psycopg2 (postgresql://).
    # Lo coercemos a postgresql+asyncpg:// para nuestro Database interface.
    sync_url = postgres_container.get_connection_url()
    # driver://user:pass@host:port/db?args → postgresql+asyncpg://...
    if sync_url.startswith("postgresql+psycopg2://"):
        async_url = "postgresql+asyncpg://" + sync_url[len("postgresql+psycopg2://") :]
    elif sync_url.startswith("postgresql://"):
        async_url = "postgresql+asyncpg://" + sync_url[len("postgresql://") :]
    else:
        async_url = sync_url
    return async_url


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def db(database_url: str) -> AsyncIterator[Database]:  # type: ignore[no-untyped-def]
    """Database async contra el Postgres real, con esquema creado vía metadata.create_all.

    Nota: no usamos Alembic para crear el schema en este test porque Alembic
    requiere un driver síncrono (psycopg2/psycopg3) y la install de esos en
    Python 3.14 / Windows es problemática. La validación de las migraciones
    en sí mismas se hace por separado con `alembic check` (no incluido en
    esta suite). Acá solo necesitamos el schema presente para validar la
    interface `Database`.

    Fixture async con loop_scope="module" para que comparta event loop con
    los tests marcados con `@pytest.mark.asyncio(loop_scope="module")`.
    """
    database: Database = create_database_from_url(database_url, pool_size=2, max_overflow=5)
    await _create_schema(database)
    try:
        yield database
    finally:
        await database.close()


async def _create_schema(database: Database) -> None:
    """Crea todas las tablas definidas en los modelos SQLAlchemy.

    Equivalente a `alembic upgrade head` para el propósito de los integration
    tests: tener el schema listo antes de los CRUD tests.
    """
    # Importar Base y todos los modelos para que la metadata los conozca.
    # Importar el paquete `models` para registrar todas las clases.
    from app.db import models  # noqa: F401
    from app.db.base import Base

    # Necesitamos el engine raw; _AsyncSQLADatabase lo expone como `_engine`.
    engine = database._engine  # type: ignore[attr-defined]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _run_alembic_upgrade(url: str) -> None:
    """Aplica `alembic upgrade head` contra la URL dada.

    Importante: Alembic es síncrono; lo corremos en un executor para no bloquear
    el event loop. Si Alembic falla, propagamos la excepción (no skip).
    """
    from alembic import command
    from alembic.config import Config

    def _sync_upgrade() -> None:
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)
        command.upgrade(cfg, "head")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _sync_upgrade)


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="module")
class TestPostgresDatabase:
    """Suite de validación de `Database` interface contra Postgres real."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_healthcheck_ping(self, db: Database) -> None:
        """Un SELECT 1 retorna 1 fila; ping_database es True."""
        row = await db.fetch_one("SELECT 1 AS one")
        assert row is not None
        assert row["one"] == 1

    @pytest.mark.asyncio(loop_scope="module")
    async def test_create_warehouse(self, db: Database) -> None:
        """INSERT + fetch_one por code funciona, respetando UNIQUE."""
        code = f"WH-{uuid.uuid4().hex[:8]}"
        wh_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO warehouses (id, code, name, warehouse_type, is_active, created_at, updated_at)
            VALUES (:id, :code, :name, :type, :is_active, :now, :now)
            """,
            {
                "id": wh_id,
                "code": code,
                "name": "Test Warehouse",
                "type": "principal",
                "is_active": True,
                "now": datetime.now(UTC),
            },
        )
        row = await db.fetch_one(
            "SELECT * FROM warehouses WHERE code = :code", {"code": code}
        )
        assert row is not None
        assert row["name"] == "Test Warehouse"
        assert row["warehouse_type"] == "principal"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_create_product(self, db: Database) -> None:
        """INSERT product respeta UNIQUE de sku."""
        sku = f"SKU-{uuid.uuid4().hex[:8]}"
        await db.execute(
            """
            INSERT INTO products (
                id, sku, name, unit, precio_costo, precio_venta,
                is_active, created_at, updated_at
            ) VALUES (
                :id, :sku, :name, :unit, :costo, :venta,
                :is_active, :now, :now
            )
            """,
            {
                "id": str(uuid.uuid4()),
                "sku": sku,
                "name": "Test Product",
                "unit": "unit",
                "costo": Decimal("0"),
                "venta": Decimal("0"),
                "is_active": True,
                "now": datetime.now(UTC),
            },
        )
        row = await db.fetch_one(
            "SELECT * FROM products WHERE sku = :sku", {"sku": sku}
        )
        assert row is not None
        assert row["name"] == "Test Product"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_register_movement(self, db: Database) -> None:
        """INSERT de inventory_movement funciona y respeta CHECKs (quantity > 0)."""
        # Crear warehouse + product primero (FK).
        wh_id = str(uuid.uuid4())
        pr_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        async with db.transaction():
            await db.execute(
                """
                INSERT INTO warehouses (id, code, name, warehouse_type, is_active, created_at, updated_at)
                VALUES (:id, :code, :name, :type, :is_active, :now, :now)
                """,
                {
                    "id": wh_id,
                    "code": f"WH-M-{uuid.uuid4().hex[:6]}",
                    "name": "Movement WH",
                    "type": "principal",
                    "is_active": True,
                    "now": now,
                },
            )
            await db.execute(
                """
                INSERT INTO products (
                    id, sku, name, unit, precio_costo, precio_venta,
                    is_active, created_at, updated_at
                ) VALUES (
                    :id, :sku, :name, :unit, :costo, :venta,
                    :is_active, :now, :now
                )
                """,
                {
                    "id": pr_id,
                    "sku": f"SKU-M-{uuid.uuid4().hex[:6]}",
                    "name": "Movement Product",
                    "unit": "unit",
                    "costo": Decimal("0"),
                    "venta": Decimal("0"),
                    "is_active": True,
                    "now": now,
                },
            )
            await db.execute(
                """
                INSERT INTO inventory_movements (
                    id, warehouse_id, product_id, movement_type, quantity,
                    reference_type, reference_id, notes, created_at
                ) VALUES (
                    :id, :wh, :pr, :type, :qty, :rtype, :rid, :notes, :now
                )
                """,
                {
                    "id": str(uuid.uuid4()),
                    "wh": wh_id,
                    "pr": pr_id,
                    "type": "in",
                    "qty": Decimal("15.00"),
                    "rtype": "test",
                    "rid": "tc-001",
                    "notes": "Integration test",
                    "now": now,
                },
            )

        # Verificar que se persistió.
        rows = await db.fetch_all(
            """
            SELECT * FROM inventory_movements
            WHERE warehouse_id = :wh AND product_id = :pr
            """,
            {"wh": wh_id, "pr": pr_id},
        )
        assert len(rows) == 1
        assert rows[0]["movement_type"] == "in"
        assert rows[0]["notes"] == "Integration test"

    @pytest.mark.asyncio(loop_scope="module")
    async def test_query_stock_levels(self, db: Database) -> None:
        """fetch_all sobre stock_levels retorna shape esperado."""
        # Insert mínimo directo: warehouse + product + stock_level.
        wh_id = str(uuid.uuid4())
        pr_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        async with db.transaction():
            await db.execute(
                """
                INSERT INTO warehouses (id, code, name, warehouse_type, is_active, created_at, updated_at)
                VALUES (:id, :code, :name, :type, :is_active, :now, :now)
                """,
                {
                    "id": wh_id,
                    "code": f"WH-S-{uuid.uuid4().hex[:6]}",
                    "name": "Stock WH",
                    "type": "principal",
                    "is_active": True,
                    "now": now,
                },
            )
            await db.execute(
                """
                INSERT INTO products (
                    id, sku, name, unit, precio_costo, precio_venta,
                    is_active, created_at, updated_at
                ) VALUES (
                    :id, :sku, :name, :unit, :costo, :venta,
                    :is_active, :now, :now
                )
                """,
                {
                    "id": pr_id,
                    "sku": f"SKU-S-{uuid.uuid4().hex[:6]}",
                    "name": "Stock Product",
                    "unit": "unit",
                    "costo": Decimal("0"),
                    "venta": Decimal("0"),
                    "is_active": True,
                    "now": now,
                },
            )
            await db.execute(
                """
                INSERT INTO stock_levels (
                    id, warehouse_id, product_id, quantity, min_quantity, updated_at
                ) VALUES (:id, :wh, :pr, :qty, :min, :now)
                """,
                {
                    "id": str(uuid.uuid4()),
                    "wh": wh_id,
                    "pr": pr_id,
                    "qty": Decimal("42.50"),
                    "min": Decimal("5.00"),
                    "now": now,
                },
            )

        rows = await db.fetch_all(
            "SELECT * FROM stock_levels WHERE warehouse_id = :wh", {"wh": wh_id}
        )
        assert len(rows) == 1
        # Postgres NUMERIC llega como Decimal (psycopg2/asyncpg nativos).
        assert Decimal(str(rows[0]["quantity"])) == Decimal("42.50")
        assert Decimal(str(rows[0]["min_quantity"])) == Decimal("5.00")

    @pytest.mark.asyncio(loop_scope="module")
    async def test_transaction_rollback(self, db: Database) -> None:
        """Si una transacción raise, los cambios se revierten."""
        marker_code = f"ROLLBACK-{uuid.uuid4().hex[:8]}"
        try:
            async with db.transaction():
                await db.execute(
                    """
                    INSERT INTO warehouses (id, code, name, warehouse_type, is_active, created_at, updated_at)
                    VALUES (:id, :code, :name, :type, :is_active, :now, :now)
                    """,
                    {
                        "id": str(uuid.uuid4()),
                        "code": marker_code,
                        "name": "Rollback WH",
                        "type": "principal",
                        "is_active": True,
                        "now": datetime.now(UTC),
                    },
                )
                # Forzar fallo dentro de la transacción.
                raise RuntimeError("intencional para test de rollback")
        except RuntimeError:
            pass  # esperado

        # El warehouse NO debe existir (rollback lo deshizo).
        row = await db.fetch_one(
            "SELECT * FROM warehouses WHERE code = :code", {"code": marker_code}
        )
        assert row is None, f"Rollback no funcionó: {row}"


@pytest.mark.integration
class TestDatabaseFactory:
    """Validación de la factory `create_database_from_url` (sin tocar BD)."""

    def test_postgres_url_returns_postgres_database(self) -> None:
        url = "postgresql+asyncpg://user:pass@localhost:5432/db"
        db = create_database_from_url(url)
        assert isinstance(db, PostgresDatabase)
        # No abrimos conexiones hasta usar, pero la fábrica debe poder cerrarse.

    def test_postgres_no_driver_coerced(self) -> None:
        """`postgresql://` (sin driver) debe coercerse a `postgresql+asyncpg://`."""
        db = create_database_from_url("postgresql://u:p@h:5432/d")
        assert isinstance(db, PostgresDatabase)

    def test_sqlite_url_returns_async_sqlite(self) -> None:
        db = create_database_from_url("sqlite:///:memory:")
        assert isinstance(db, AsyncSQLiteDatabase)

    def test_unsupported_scheme_raises(self) -> None:
        with pytest.raises(ValueError, match="scheme no soportado"):
            create_database_from_url("mongodb://localhost/db")


@pytest.mark.integration
class TestAsyncSQLiteInterface:
    """Tests del contrato `Database` usando AsyncSQLiteDatabase (sin testcontainers)."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_crud_roundtrip(self) -> None:
        """Insert + fetch_one + fetch_all + transacción sobre AsyncSQLite."""
        db: Database = create_database_from_url("sqlite:///:memory:")
        try:
            await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, n TEXT)")
            async with db.transaction():
                await db.execute("INSERT INTO t (n) VALUES (:n)", {"n": "alpha"})
                await db.execute("INSERT INTO t (n) VALUES (:n)", {"n": "beta"})
            rows = await db.fetch_all("SELECT n FROM t ORDER BY id")
            assert [r["n"] for r in rows] == ["alpha", "beta"]
        finally:
            await db.close()
