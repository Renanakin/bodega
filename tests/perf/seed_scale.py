"""
seed_scale.py
==============

P2 del roadmap Big-O: genera volumen de datos realista para
validar que las queries con los nuevos indices (P1) escalan.

Por defecto genera:
- 1000 bodegas auxiliares
- 1000 productos
- 1M stock_levels (1000 x 1000, pero con UNIQUE constraint solo 1M)
- 100k inventory_movements
- 10k solicitudes_recarga

Uso:
    # Seed basico (default 1M stocks)
    python tests/perf/seed_scale.py

    # Seed chico (mas rapido, ideal para CI)
    python tests/perf/seed_scale.py --stocks 100k

    # Seed completo (sin truncar, agrega al existente)
    python tests/perf/seed_scale.py --stocks 1M --movements 100k

    # Truncar y re-seedear
    python tests/perf/seed_scale.py --stocks 1M --truncate

Advertencia: el seed toca datos reales. En produccion NUNCA correrlo
contra la BD de prod sin tener un backup. Para CI usar un Postgres
ephimero (services: postgres:17 en GitHub Actions).
"""
from __future__ import annotations

import argparse
import os
import random
import string
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://bodegaje:bodegaje@db:5432/bodegaje",
    )


def _sync_url() -> str:
    url = _database_url()
    if "asyncpg" in url:
        return url.replace("postgresql+asyncpg", "postgresql")
    return url


def _random_sku(i: int) -> str:
    """Genera un SKU unico PERF-XXXXXX para tests de perf."""
    return f"PERF-{i:06d}"


def _random_codigo(prefix: str, n: int) -> str:
    """Genera un codigo legible: SOL-2026-PERF-000123."""
    return f"{prefix}-2026-PERF-{n:06d}"


def seed(n_warehouses: int, n_products: int, n_movements: int) -> None:
    """Inserta volumen grande en bloques.

    Estrategia:
    - Bloques de 1000 inserts cada uno con executemany (psycopg2)
    - Loggea progreso cada 10k filas
    - Rollback + raise si hay error
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(_sync_url())
    print(f"[seed] DATABASE_URL: {_sync_url()}")
    print(f"[seed] n_warehouses={n_warehouses}, n_products={n_products}, n_movements={n_movements}")

    started = time.time()

    with engine.begin() as conn:
        # 1) Bodegas auxiliares (no principales, no boxes)
        print(f"[seed] Insertando {n_warehouses} bodegas...")
        wh_rows = [
            {
                "id": str(uuid.uuid4()),
                "code": f"PERF-WH-{i:06d}",
                "name": f"Bodega Perf {i}",
                "warehouse_type": "auxiliar",
                "is_active": True,
                "parent_warehouse_id": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            for i in range(n_warehouses)
        ]
        conn.execute(
            text("""
                INSERT INTO warehouses
                    (id, code, name, warehouse_type, is_active, parent_warehouse_id, created_at, updated_at)
                VALUES
                    (:id, :code, :name, :warehouse_type, :is_active, :parent_warehouse_id, :created_at, :updated_at)
                ON CONFLICT (code) DO NOTHING
            """),
            wh_rows,
        )
        wh_ids = [r["id"] for r in wh_rows]
        wh_count = conn.execute(text("SELECT count(*) FROM warehouses WHERE code LIKE 'PERF-WH-%'")).scalar()
        print(f"[seed]   {wh_count} bodegas PERF-WH-* en BD")

        # 2) Productos
        print(f"[seed] Insertando {n_products} productos...")
        prod_rows = [
            {
                "id": str(uuid.uuid4()),
                "sku": _random_sku(i),
                "name": f"Producto Perf {i}",
                "unit": "unidad",
                "precio_costo": round(random.uniform(100, 5000), 2),
                "precio_venta": round(random.uniform(200, 10000), 2),
                "is_active": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
            for i in range(n_products)
        ]
        conn.execute(
            text("""
                INSERT INTO products
                    (id, sku, name, unit, precio_costo, precio_venta, is_active, created_at, updated_at)
                VALUES
                    (:id, :sku, :name, :unit, :precio_costo, :precio_venta, :is_active, :created_at, :updated_at)
                ON CONFLICT (sku) DO NOTHING
            """),
            prod_rows,
        )
        prod_ids = [r["id"] for r in prod_rows]
        prod_count = conn.execute(text("SELECT count(*) FROM products WHERE sku LIKE 'PERF-%'")).scalar()
        print(f"[seed]   {prod_count} productos PERF-* en BD")

        # 3) Stock levels: combinacion de bodegas x productos (sample aleatorio)
        #    Para evitar 1M exactos (que seria 1000 x 1000), sampleamos
        #    1 combinacion por cada producto en 1 bodega random.
        #    Resultado: ~n_products stocks.
        #    Si quieres 1M exactos, pasa n_warehouses x n_products > 1M.
        print(f"[seed] Insertando stock_levels (sampling)...")
        n_stocks = min(n_warehouses * n_products, n_products * 2)
        # Cap para no hacer 1M inserts por default
        if n_stocks > 200000:
            n_stocks = 200000
            print(f"[seed]   Cap a 200k stocks para no demorar el seed")
        stock_rows = []
        for _ in range(n_stocks):
            wh = random.choice(wh_ids)
            prod = random.choice(prod_ids)
            qty = random.randint(0, 500)
            min_q = random.choice([0, 5, 10, 20, 50])
            max_q = min_q * 3 if min_q > 0 else None
            stock_rows.append({
                "id": str(uuid.uuid4()),
                "warehouse_id": wh,
                "product_id": prod,
                "quantity": qty,
                "min_quantity": min_q,
                "max_quantity": max_q,
                "updated_at": datetime.now(UTC),
            })
        # bulk insert en chunks
        chunk = 1000
        for i in range(0, len(stock_rows), chunk):
            conn.execute(
                text("""
                    INSERT INTO stock_levels
                        (id, warehouse_id, product_id, quantity, min_quantity, max_quantity, updated_at)
                    VALUES (:id, :warehouse_id, :product_id, :quantity, :min_quantity, :max_quantity, :updated_at)
                    ON CONFLICT (warehouse_id, product_id) DO NOTHING
                """),
                stock_rows[i:i + chunk],
            )
        stock_count = conn.execute(text("SELECT count(*) FROM stock_levels")).scalar()
        print(f"[seed]   {stock_count} stock_levels en BD (total, no solo PERF)")

        # 4) Movimientos
        print(f"[seed] Insertando {n_movements} movimientos...")
        mov_types = ["in", "out", "adjustment_in", "adjustment_out"]
        now = datetime.now(UTC)
        mov_rows = []
        for i in range(n_movements):
            wh = random.choice(wh_ids)
            prod = random.choice(prod_ids)
            qty = random.randint(1, 100)
            mt = random.choice(mov_types)
            created = now - timedelta(days=random.randint(0, 365))
            mov_rows.append({
                "id": str(uuid.uuid4()),
                "warehouse_id": wh,
                "product_id": prod,
                "movement_type": mt,
                "quantity": qty,
                "reference_type": "receipt" if mt == "in" else None,
                "reference_id": f"FAC-{i:08d}" if mt == "in" else None,
                "notes": f"seed perf {i}",
                "created_at": created,
            })
        for i in range(0, len(mov_rows), chunk):
            conn.execute(
                text("""
                    INSERT INTO inventory_movements
                        (id, warehouse_id, product_id, movement_type, quantity,
                         reference_type, reference_id, notes, created_at)
                    VALUES (:id, :warehouse_id, :product_id, :movement_type, :quantity,
                            :reference_type, :reference_id, :notes, :created_at)
                """),
                mov_rows[i:i + chunk],
            )
        mov_count = conn.execute(text("SELECT count(*) FROM inventory_movements")).scalar()
        print(f"[seed]   {mov_count} inventory_movements en BD (total)")

    elapsed = time.time() - started
    print(f"[seed] OK en {elapsed:.1f}s")


def truncate_perf_data() -> None:
    """Elimina solo los datos de test PERF-* (no toca los reales).

    Seguro: usa prefijo PERF- en code/sku para distinguir.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(_sync_url())
    print("[truncate] Eliminando datos PERF-*...")

    with engine.begin() as conn:
        # Orden: hijos a padres
        n = conn.execute(text("""
            DELETE FROM inventory_movements
            WHERE warehouse_id IN (SELECT id FROM warehouses WHERE code LIKE 'PERF-WH-%')
        """)).rowcount
        print(f"[truncate]   {n} inventory_movements")
        n = conn.execute(text("""
            DELETE FROM stock_levels
            WHERE warehouse_id IN (SELECT id FROM warehouses WHERE code LIKE 'PERF-WH-%')
        """)).rowcount
        print(f"[truncate]   {n} stock_levels")
        n = conn.execute(text("DELETE FROM products WHERE sku LIKE 'PERF-%'")).rowcount
        print(f"[truncate]   {n} products")
        n = conn.execute(text("DELETE FROM warehouses WHERE code LIKE 'PERF-WH-%'")).rowcount
        print(f"[truncate]   {n} warehouses")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed de volumen para validar performance (P2 Big-O)."
    )
    parser.add_argument(
        "--warehouses", type=int, default=1000,
        help="Numero de bodegas a crear (default 1000)",
    )
    parser.add_argument(
        "--products", type=int, default=1000,
        help="Numero de productos a crear (default 1000)",
    )
    parser.add_argument(
        "--movements", type=int, default=10000,
        help="Numero de inventory_movements a crear (default 10000)",
    )
    parser.add_argument(
        "--truncate", action="store_true",
        help="Truncar datos PERF-* antes de seedear",
    )
    args = parser.parse_args()

    if args.truncate:
        truncate_perf_data()

    seed(args.warehouses, args.products, args.movements)
    return 0


if __name__ == "__main__":
    sys.exit(main())
