"""
explain_critical_queries.py
============================

P1 + P3 del roadmap Big-O: corre EXPLAIN ANALYZE en las 5 queries
mas criticas del sistema y verifica que usen indices (no Seq Scan).

Queries cubiertas:
    1. Bajo minimo (solicitudes bajo minimo)
    2. Solicitudes pendientes (cobertura)
    3. OC listar con JOIN supervisor
    4. Audit por actor
    5. Email outbox worker

Uso:
    # Local contra Postgres en Docker
    python tests/perf/explain_critical_queries.py

    # Con threshold custom (por defecto fail si Seq Scan en tabla > 10k filas)
    python tests/perf/explain_critical_queries.py --threshold 1000

    # Solo reportar sin fail
    python tests/perf/explain_critical_queries.py --report-only

Salida:
    - Plan EXPLAIN de cada query (texto, primeras lineas)
    - Veredicto: PASS o FAIL con motivo
    - Exit code 0 si todo OK, 1 si hay Seq Scan en tabla grande

Requiere:
    - DATABASE_URL apuntando a la BD a analizar
    - Tabla con suficiente volumen para que el planner elija el indice
      (idealmente > 10k filas en cada tabla analizada)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://bodegaje:bodegaje@db:5432/bodegaje",
    )


def _sync_url() -> str:
    """Convierte asyncpg URL a psycopg2 URL para EXPLAIN sync."""
    url = _database_url()
    if "asyncpg" in url:
        return url.replace("postgresql+asyncpg", "postgresql")
    return url


def _is_postgres() -> bool:
    return _sync_url().startswith(("postgresql", "postgres"))


# ---------------------------------------------------------------------------
# Definicion de las 5 queries criticas
# ---------------------------------------------------------------------------


@dataclass
class CriticalQuery:
    name: str
    description: str
    sql: str
    # Tablas a chequear por Seq Scan. Si EXPLAIN muestra Seq Scan en
    # una de estas tablas, FAIL.
    critical_tables: list[str]


QUERIES: list[CriticalQuery] = [
    CriticalQuery(
        name="bajo_minimo",
        description="GET /solicitudes/bajo-minimo (P0: bajo minimo por bodega)",
        sql="""
            SELECT warehouse_id, product_id, quantity, min_quantity
            FROM stock_levels
            WHERE min_quantity > 0 AND quantity <= min_quantity
        """,
        critical_tables=["stock_levels"],
    ),
    CriticalQuery(
        name="solicitudes_pendientes_cobertura",
        description=(
            "Cobertura: solicitudes activas por bodega origen "
            "(BUG 12: pending/approved/in_transit/partially_received)"
        ),
        sql="""
            SELECT d.id_producto
            FROM detalle_solicitud_recarga d
            JOIN solicitudes_recarga s ON s.id = d.id_solicitud
            WHERE s.estado IN ('pending', 'approved', 'in_transit', 'partially_received')
              AND s.id_bodega_origen = '00000000-0000-0000-0000-000000000000'
        """,
        critical_tables=["solicitudes_recarga", "detalle_solicitud_recarga"],
    ),
    CriticalQuery(
        name="ordenes_compra_listar",
        description="GET /ordenes-compra (listar con JOIN supervisor)",
        sql="""
            SELECT oc.codigo, oc.estado, s.nombre AS supervisor_nombre
            FROM ordenes_compra oc
            LEFT JOIN supervisores s ON s.id = oc.id_supervisor
            WHERE oc.estado = 'enviado_a_supervisor'
            ORDER BY oc.created_at DESC
            LIMIT 50
        """,
        critical_tables=["ordenes_compra"],
    ),
    CriticalQuery(
        name="audit_por_actor",
        description="GET /audit?actor_id=X (P1: indice nuevo)",
        sql="""
            SELECT id, action, entity_type, created_at
            FROM audit_logs
            WHERE user_id = '00000000-0000-0000-0000-000000000000'
              AND created_at >= NOW() - INTERVAL '30 days'
            ORDER BY created_at DESC
            LIMIT 100
        """,
        critical_tables=["audit_logs"],
    ),
    CriticalQuery(
        name="email_outbox_worker",
        description="Worker Arq: outbox pendientes para envio",
        sql="""
            SELECT id, to_email, subject, attempts
            FROM email_outbox
            WHERE status = 'pending' AND attempts < 3
            ORDER BY created_at ASC
            LIMIT 50
        """,
        critical_tables=["email_outbox"],
    ),
]


# ---------------------------------------------------------------------------
# Ejecucion de EXPLAIN
# ---------------------------------------------------------------------------


def run_explain(sql: str) -> dict:
    """Ejecuta EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) sobre la query.

    Retorna el plan completo como dict. Si la BD no es Postgres,
    usa EXPLAIN basico (SQLite).
    """
    if _is_postgres():
        from sqlalchemy import create_engine, text

        engine = create_engine(_sync_url())
        with engine.connect() as conn:
            result = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"))
            plan = result.scalar()
        return plan[0] if isinstance(plan, list) else plan
    else:
        # SQLite: EXPLAIN QUERY PLAN da info basica
        from sqlalchemy import create_engine, text

        engine = create_engine(_database_url())
        with engine.connect() as conn:
            result = conn.execute(text(f"EXPLAIN QUERY PLAN {sql}"))
            rows = list(result)
        return {"SQLite_Plan": [dict(r._mapping) for r in rows]}


def check_plan_has_seq_scan(plan: dict, critical_tables: list[str], threshold_rows: int) -> tuple[bool, str]:
    """Recorre recursivamente el plan buscando Seq Scan en critical_tables.

    Para Postgres: busca en 'Plan' -> 'Node Type' == 'Seq Scan' y
    'Relation Name' in critical_tables, y 'Plan Rows' > threshold.
    Para SQLite: busca texto "SCAN" en critical_tables.

    Returns:
        (passed, message). passed=True si NO hay Seq Scan problematico.
    """
    if _is_postgres():
        problems = _walk_plan_for_seq_scan(plan.get("Plan", plan), critical_tables, threshold_rows)
        if problems:
            return False, "; ".join(problems)
        return True, "OK - todos los nodos usan index scan o son pequenos"
    else:
        # SQLite: cualquier SCAN es malo
        text = json.dumps(plan)
        bad = [t for t in critical_tables if f"SCAN {t}".upper() in text.upper()]
        if bad:
            return False, f"SQLite SCAN en: {bad}"
        return True, "OK - SQLite usa SEARCH (index)"


def _walk_plan_for_seq_scan(node: dict, critical_tables: list[str], threshold: int) -> list[str]:
    """DFS en el plan de Postgres buscando Seq Scan en tablas grandes."""
    problems = []
    if not isinstance(node, dict):
        return problems
    node_type = node.get("Node Type", "")
    rel_name = node.get("Relation Name", "")
    plan_rows = node.get("Plan Rows", 0)
    if node_type == "Seq Scan" and rel_name in critical_tables and plan_rows > threshold:
        problems.append(
            f"Seq Scan en {rel_name} (Plan Rows={plan_rows} > threshold={threshold})"
        )
    for child in node.get("Plans", []) or []:
        problems.extend(_walk_plan_for_seq_scan(child, critical_tables, threshold))
    return problems


# ---------------------------------------------------------------------------
# Reporte
# ---------------------------------------------------------------------------


def truncate(s: str, n: int) -> str:
    """Trunca a n caracteres, anadiendo '...' si fue truncado."""
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida que las 5 queries criticas usen indices (Big-O)."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=1000,
        help="Si Seq Scan devuelve mas de N filas estimadas, FAIL (default 1000). "
             "Tablas <1000 filas: Seq Scan es optimo, OK.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Solo reportar, exit 0 siempre",
    )
    args = parser.parse_args()

    print("=" * 78)
    print("  EXPLAIN ANALYZE: 5 queries criticas (P1 + P3 Big-O)")
    print("=" * 78)
    print(f"  DATABASE_URL: {_database_url()}")
    print(f"  Threshold:    {args.threshold} filas estimadas para Seq Scan OK")
    print(f"  Backend:      {'Postgres' if _is_postgres() else 'SQLite (test)'}")
    print()

    if not _is_postgres():
        print("  [AVISO] SQLite detectado. El test es informativo (no falla).")
        print("          Para validar en serio, correr contra Postgres en Docker.")
        print()

    failures: list[tuple[str, str]] = []
    for q in QUERIES:
        print("-" * 78)
        print(f"  {q.name}: {q.description}")
        try:
            plan = run_explain(q.sql)
        except Exception as e:
            print(f"  [ERROR] {e}")
            failures.append((q.name, f"Error ejecutando EXPLAIN: {e}"))
            continue

        # Mostrar primeras lineas del plan
        plan_text = json.dumps(plan, indent=2, default=str)
        print(f"  Plan (truncado):")
        for line in plan_text.splitlines()[:15]:
            print(f"    {line}")
        if len(plan_text.splitlines()) > 15:
            print(f"    ... ({len(plan_text.splitlines()) - 15} lineas mas)")

        passed, msg = check_plan_has_seq_scan(
            plan, q.critical_tables, args.threshold
        )
        if passed:
            print(f"  [OK] {msg}")
        else:
            print(f"  [FAIL] {msg}")
            if _is_postgres() and not args.report_only:
                failures.append((q.name, msg))

    # Resumen
    print()
    print("=" * 78)
    if failures:
        print(f"  RESULTADO: {len(failures)} queries con Seq Scan problematico")
        for name, msg in failures:
            print(f"    - {name}: {msg}")
        if args.report_only:
            print()
            print("  --report-only activo: exit 0")
            return 0
        return 1
    else:
        print("  RESULTADO: Todas las queries usan indices (Big-O compliant)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
