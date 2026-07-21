"""
Seed script via SQLAlchemy (Fase 1, ADR-0001).

Carga el set mínimo de datos equivalente a `db/seeds/0001_inventory_mvp_seed.sql`
pero usando el ORM SQLAlchemy en vez de SQL crudo. Es idempotente: re-ejecutarlo
NO duplica filas.

Uso:
    # 1) Con el env de desarrollo cargado (lee DATABASE_URL de .env.development):
    $env:ENVIRONMENT = "development"
    python -m app.db.seed

    # 2) O apuntando a un postgres específico (CI / local):
    $env:DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/db"
    python -m app.db.seed

Prerrequisito:
    Haber corrido `alembic upgrade head` antes (este script NO crea tablas).

Reglas aplicadas:
- R1: nada hardcoded; todo desde env / Settings.
- R3: ubicación obvia (`app/db/seed.py`).
- R4: solo datos; la lógica de dominio vive en services.
- R8: usa el logger estructurado.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.models.inventory import InventoryMovement, MovementType, StockLevel
from app.db.models.products import Product
from app.db.models.warehouses import Warehouse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

log = get_logger(__name__)

# IDs fijos del seed legacy (mantener compat con `db/seeds/0001_inventory_mvp_seed.sql`)
WAREHOUSE_CENTRAL_ID = UUID("11111111-1111-1111-1111-111111111111")
PRODUCT_SKU001_ID = UUID("22222222-2222-2222-2222-222222222222")
MOVEMENT_SEED_001_ID = UUID("33333333-3333-3333-3333-333333333333")
STOCK_LEVEL_SEED_ID = UUID("44444444-4444-4444-4444-444444444444")

# Datos del seed (un solo set MVP)
# NOTA: la migración 0001 (post-ADR-0002) cambió `warehouse_type` para que
# solo acepte `('principal', 'auxiliar', 'mecanico_box')`. El seed legacy en
# `db/seeds/0001_inventory_mvp_seed.sql` usaba `'central'`, que ahora viola
# el CHECK. Usamos `'principal'` (el nuevo equivalente semántico).
SEED_WAREHOUSE: dict[str, Any] = {
    "id": WAREHOUSE_CENTRAL_ID,
    "code": "CENTRAL",
    "name": "Bodega Central",
    "warehouse_type": "principal",
    "is_active": True,
    "parent_warehouse_id": None,
}

SEED_PRODUCT: dict[str, Any] = {
    "id": PRODUCT_SKU001_ID,
    "sku": "SKU-001",
    "name": "Producto Inicial",
    "unit": "unit",
    "is_active": True,
    "codigo_barras": None,
    "id_categoria": None,
    "precio_costo": Decimal("0"),
    "precio_venta": Decimal("0"),
}

SEED_MOVEMENT: dict[str, Any] = {
    "id": MOVEMENT_SEED_001_ID,
    "warehouse_id": WAREHOUSE_CENTRAL_ID,
    "product_id": PRODUCT_SKU001_ID,
    "movement_type": MovementType.IN,
    "quantity": Decimal("10.00"),
    "reference_type": "seed",
    "reference_id": "seed-in-001",
    "notes": "Carga inicial para validacion local",
}

SEED_STOCK_LEVEL: dict[str, Any] = {
    "id": STOCK_LEVEL_SEED_ID,
    "warehouse_id": WAREHOUSE_CENTRAL_ID,
    "product_id": PRODUCT_SKU001_ID,
    "quantity": Decimal("10.00"),
    "min_quantity": Decimal("2.00"),
    "max_quantity": None,
}


def _build_upsert(model: type, row: dict[str, Any], dialect: str) -> Any:
    """Construye un INSERT ... ON CONFLICT DO NOTHING portable.

    - Postgres: usa `ON CONFLICT (col) DO NOTHING`.
    - SQLite: usa `OR IGNORE` (semántica equivalente).
    - Si el dialect no soporta ninguno, raise para que el caller falle rápido.
    """
    if dialect == "postgresql":
        # Detectar la PK del modelo y construir el conflict target.
        pk_cols = [c.name for c in model.__table__.primary_key.columns]
        if len(pk_cols) == 1:
            return pg_insert(model).values(row).on_conflict_do_nothing(index_elements=pk_cols)
        return pg_insert(model).values(row).on_conflict_do_nothing()
    if dialect == "sqlite":
        return sqlite_insert(model).values(row).on_conflict_do_nothing()
    raise ValueError(f"dialect no soportado para upsert: {dialect!r}")


async def _seed_table(
    session: AsyncSession,
    model: type,
    row: dict[str, Any],
    *,
    name: str,
) -> str:
    """Inserta una fila idempotentemente. Retorna 'inserted' | 'skipped'."""
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    stmt = _build_upsert(model, row, dialect)
    result = await session.execute(stmt)
    await session.commit()
    # rowcount: en ON CONFLICT DO NOTHING, retorna 1 si insertó, 0 si no.
    if result.rowcount and result.rowcount > 0:
        log.info("seed.inserted", table=name, **row)
        return "inserted"
    log.info("seed.skipped", table=name, reason="conflict", **row)
    return "skipped"


async def seed_database() -> dict[str, int]:
    """Carga el set mínimo de datos MVP. Idempotente.

    Returns:
        Diccionario con conteo {table: inserted_count} para reporte.

    Raises:
        RuntimeError: si DATABASE_URL no está definida o el dialect no es soportado.
    """
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL no definida. Configúrala en .env.development "
            "o vía la variable de entorno DATABASE_URL."
        )

    log.info("seed.starting", url=settings.database_url.split("@")[-1])

    # Engine dedicado para el seed (no usamos get_engine() porque queremos
    # que el seed sea independiente del ciclo de vida de la app).
    engine = create_async_engine(settings.database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    counts: dict[str, int] = {
        "warehouses": 0,
        "products": 0,
        "inventory_movements": 0,
        "stock_levels": 0,
    }

    try:
        async with factory() as session:
            # Validar que las migraciones estén aplicadas (chequeo barato).
            # Si la tabla `warehouses` no existe, fallar rápido con mensaje claro.
            from sqlalchemy import text

            try:
                await session.execute(text("SELECT 1 FROM warehouses LIMIT 0"))
            except Exception as exc:
                raise RuntimeError(
                    "Las tablas no existen. Corre `alembic upgrade head` antes de seed. "
                    f"Error: {exc}"
                ) from exc

            if (
                await _seed_table(session, Warehouse, SEED_WAREHOUSE, name="warehouses")
                == "inserted"
            ):
                counts["warehouses"] += 1
            if await _seed_table(session, Product, SEED_PRODUCT, name="products") == "inserted":
                counts["products"] += 1
            if (
                await _seed_table(
                    session, InventoryMovement, SEED_MOVEMENT, name="inventory_movements"
                )
                == "inserted"
            ):
                counts["inventory_movements"] += 1
            if (
                await _seed_table(session, StockLevel, SEED_STOCK_LEVEL, name="stock_levels")
                == "inserted"
            ):
                counts["stock_levels"] += 1

    finally:
        await engine.dispose()

    log.info("seed.completed", **counts)
    return counts


def main() -> None:
    """Entry point para `python -m app.db.seed`."""
    configure_logging()
    try:
        counts = asyncio.run(seed_database())
        # Resumen al logger estructurado (no usamos print por Regla de Oro R8).
        log.info(
            "seed.summary",
            warehouses=counts["warehouses"],
            products=counts["products"],
            inventory_movements=counts["inventory_movements"],
            stock_levels=counts["stock_levels"],
        )
    except RuntimeError as exc:
        log.error("seed.failed", error=str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
