"""
run_all.py
==========

Orquestador de tests E2E de `auditoria-fase5/`.

Corre todos los tests en serie con timeout por test, captura output,
genera reporte agregado y exit code:
  0 = todos los tests pasaron
  1 = al menos un test fallo
  2 = error del orquestador

Tests incluidos (orden de ejecucion):
  1. test_replenishment_bug12.py    - cobertura de solicitudes (rapido)
  2. test_oc_correo_flujo.py        - modulo OC por correo (3 escenarios)
  3. test_backup_restore.py         - backup + restore
  4. test_bug11_layout.py           - bug visual de layout (Playwright)
  5. test_manual_screens.py         - screenshots del manual (Playwright)

Uso:
  python run_all.py                 # corre todos
  python run_all.py --skip backup   # salta backup (lento)
  python run_all.py --only oc       # corre solo test_oc_correo_flujo
  python run_all.py --verbose       # muestra output completo de cada test
  python run_all.py --timeout 60    # timeout por test (default 180s)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Definicion de tests
# ---------------------------------------------------------------------------


@dataclass
class TestCase:
    name: str
    script: str
    args: list[str] = field(default_factory=list)
    timeout_s: int = 180
    requires_system: bool = True
    description: str = ""


TESTS: list[TestCase] = [
    TestCase(
        name="replenishment_bug12",
        script="test_replenishment_bug12.py",
        description="Cobertura de solicitudes: estados activos cubren SKUs bajo minimo",
        timeout_s=60,
    ),
    TestCase(
        name="oc_correo_flujo",
        script="test_oc_correo_flujo.py",
        description="Modulo OC por correo: happy path / descuadre / rechazo",
        timeout_s=180,
    ),
    TestCase(
        name="backup_restore",
        script="test_backup_restore.py",
        description="Backup diario + restore a BD temporal + chequeo de integridad",
        timeout_s=240,
    ),
    TestCase(
        name="bug11_layout",
        script="test_bug11_layout.py",
        description="Layout del bloque de cubiertos en Replenishment (Playwright)",
        timeout_s=120,
        requires_system=False,  # Solo necesita UI
    ),
    TestCase(
        name="manual_screens",
        script="test_manual_screens.py",
        description="Captura de pantallas del manual de usuario (Playwright)",
        timeout_s=120,
        requires_system=False,
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    name: str
    ok: bool
    exit_code: int
    duration_s: float
    stdout: str
    stderr: str
    summary: str = ""


def run_one(tc: TestCase, verbose: bool, base_timeout: int) -> TestResult:
    """Corre un test y devuelve su resultado."""
    path = HERE / tc.script
    if not path.exists():
        return TestResult(
            name=tc.name,
            ok=False,
            exit_code=2,
            duration_s=0.0,
            stdout="",
            stderr=f"Script no encontrado: {path}",
            summary="SKIP (script no existe)",
        )

    timeout = tc.timeout_s if tc.timeout_s else base_timeout
    cmd = [PYTHON, str(path), *tc.args]

    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(HERE),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        rc = proc.returncode
        ok = rc == 0
    except subprocess.TimeoutExpired as e:
        return TestResult(
            name=tc.name,
            ok=False,
            exit_code=124,
            duration_s=timeout,
            stdout=(e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
            stderr=(e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
            summary=f"TIMEOUT tras {timeout}s",
        )
    except Exception as e:
        return TestResult(
            name=tc.name,
            ok=False,
            exit_code=2,
            duration_s=time.time() - started,
            stdout="",
            stderr=str(e),
            summary=f"ERROR del runner: {e}",
        )

    duration = time.time() - started
    summary = extract_summary(proc.stdout, tc.name)
    return TestResult(
        name=tc.name,
        ok=ok,
        exit_code=rc,
        duration_s=duration,
        stdout=proc.stdout,
        stderr=proc.stderr,
        summary=summary,
    )


# Extrae la linea de resumen del test (ultima linea con "Pasados" o "OK")
_SUMMARY_PATTERNS = [
    re.compile(r"Pasados:\s*(\d+)\s*/\s*(\d+)"),
    re.compile(r"Pasaron:\s*(\d+)\s*/\s*(\d+)"),
    re.compile(r"OK:\s*(\d+)\s*/\s*(\d+)"),
    re.compile(r"(\d+)\s*/\s*(\d+)\s*tests? passed", re.IGNORECASE),
]


def extract_summary(stdout: str, name: str) -> str:
    if not stdout:
        return "sin output"
    last_lines = stdout.strip().splitlines()[-15:]
    for line in last_lines:
        for pat in _SUMMARY_PATTERNS:
            m = pat.search(line)
            if m:
                return line.strip()
    # Fallback: ultima linea no vacia
    for line in reversed(last_lines):
        if line.strip():
            return line.strip()[:120]
    return "sin resumen"


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


def print_header() -> None:
    print("=" * 78)
    print("  RUN_ALL: Bateria E2E de auditoria-fase5/")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print(f"  {len(TESTS)} tests configurados")
    print("=" * 78)


def print_test_header(tc: TestCase, idx: int, total: int) -> None:
    print()
    print("=" * 78)
    print(f"  [{idx}/{total}] {tc.name.upper()}")
    print(f"  {tc.description}")
    print(f"  Script: {tc.script} | Timeout: {tc.timeout_s}s")
    print("=" * 78)


def print_test_result(res: TestResult, verbose: bool) -> None:
    print()
    print("-" * 78)
    if res.ok:
        marker = "[OK]"
        color = "\033[92m"  # verde
    else:
        marker = "[FAIL]"
        color = "\033[91m"  # rojo
    endc = "\033[0m"
    print(
        f"  {color}{marker}{endc} {res.name} "
        f"(rc={res.exit_code}, {res.duration_s:.1f}s)"
    )
    print(f"  Resumen: {res.summary}")
    if not res.ok:
        # Mostrar las ultimas 15 lineas de stdout y stderr
        if res.stdout:
            print("\n  --- stdout (ultimas 15 lineas) ---")
            for line in res.stdout.strip().splitlines()[-15:]:
                print(f"    {line}")
        if res.stderr:
            print("\n  --- stderr (ultimas 10 lineas) ---")
            for line in res.stderr.strip().splitlines()[-10:]:
                print(f"    {line}")
    elif verbose:
        print("\n  --- stdout completo (verbose) ---")
        for line in res.stdout.strip().splitlines():
            print(f"    {line}")
        if res.stderr:
            print("\n  --- stderr ---")
            for line in res.stderr.strip().splitlines():
                print(f"    {line}")


def print_summary(results: list[TestResult], total_s: float) -> None:
    print()
    print("=" * 78)
    print("  RESUMEN FINAL")
    print("=" * 78)
    ok = sum(1 for r in results if r.ok)
    fail = sum(1 for r in results if not r.ok)
    print(f"  Tests ejecutados: {len(results)}")
    print(f"  Pasados:          {ok} / {len(results)}")
    print(f"  Fallados:         {fail} / {len(results)}")
    print(f"  Tiempo total:     {total_s:.1f}s")
    print()
    print("  Detalle por test:")
    for r in results:
        status = "OK  " if r.ok else "FAIL"
        print(
            f"    [{status}] {r.name:<25} {r.duration_s:>6.1f}s  {r.summary[:60]}"
        )
    if fail:
        print()
        print("  Fallos:")
        for r in results:
            if not r.ok:
                print(f"    - {r.name}: rc={r.exit_code}, {r.summary[:80]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Orquestador de tests E2E de auditoria-fase5/",
    )
    parser.add_argument(
        "--skip", nargs="+", default=[],
        help="Nombres de tests a saltar (ej: backup bug11_layout)",
    )
    parser.add_argument(
        "--only", nargs="+", default=[],
        help="Corre SOLO estos tests (ej: oc_correo_flujo)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Muestra output completo de cada test (no solo el resumen)",
    )
    parser.add_argument(
        "--timeout", type=int, default=180,
        help="Timeout por test en segundos (default 180)",
    )
    parser.add_argument(
        "--no-color", action="store_true",
        help="Desactiva colores ANSI",
    )
    parser.add_argument(
        "--allow-prod",
        action="store_true",
        help="PERMITE correr contra un endpoint que parece produccion. "
             "Por defecto se bloquea por seguridad (FASE 2.3 del plan).",
    )
    args = parser.parse_args()

    # FASE 2.3 del plan_ejecucion_testing.md: guard de aislamiento.
    # Por defecto, NO permitimos que los tests E2E corran contra un
    # endpoint que parezca produccion (production.example.com, prod.*, etc).
    # Si el usuario REALMENTE quiere correr contra prod (smoke test post-deploy),
    # debe usar --allow-prod explicitamente.
    BOD_API = os.environ.get("BOD_API", "http://localhost:8080/api/v1")
    if not args.allow_prod:
        suspicious_markers = (
            "prod.", "production.", ".prod", "-prod",
            "live.", ".com", "staging-",  # tambien bloquea staging
        )
        # Permitir solo localhost y 127.0.0.1 y 0.0.0.0
        if any(m in BOD_API.lower() for m in suspicious_markers) and "localhost" not in BOD_API.lower() and "127.0.0.1" not in BOD_API:
            print(
                f"\n[BLOCK] BOD_API parece apuntar a produccion: {BOD_API}",
                file=sys.stderr,
            )
            print(
                "       Por seguridad, los tests E2E no corren contra prod.",
                file=sys.stderr,
            )
            print(
                "       Si REALMENTE queres correrlos, usa --allow-prod",
                file=sys.stderr,
            )
            return 2
    # Pasamos BOD_API al ambiente para los tests que lo lean
    os.environ["BOD_API"] = BOD_API

    # Filtrar tests segun --skip / --only
    selected: list[TestCase] = []
    for tc in TESTS:
        if args.only and tc.name not in args.only:
            continue
        if args.skip and tc.name in args.skip:
            continue
        selected.append(tc)

    if not selected:
        print("[ERROR] Ningun test seleccionado.", file=sys.stderr)
        return 2

    if args.no_color or not sys.stdout.isatty():
        # Patch de colores: simple, no usamos colorama
        import builtins
        _real_print = builtins.print
        def _no_color_print(*a, **kw):
            text = "".join(str(x) for x in a)
            text = text.replace("\033[92m", "").replace("\033[91m", "").replace("\033[0m", "")
            _real_print(text, **kw)
        builtins.print = _no_color_print

    print_header()
    print(f"  Tests a correr: {[t.name for t in selected]}")

    results: list[TestResult] = []
    total_started = time.time()

    for i, tc in enumerate(selected, 1):
        print_test_header(tc, i, len(selected))
        res = run_one(tc, args.verbose, args.timeout)
        results.append(res)
        print_test_result(res, args.verbose)

    total_s = time.time() - total_started
    print_summary(results, total_s)

    failed = sum(1 for r in results if not r.ok)
    if failed:
        print(f"\n[EXIT 1] {failed} test(s) fallaron")
        return 1
    print(f"\n[EXIT 0] Todos los tests pasaron")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[abort] interrumpido por el usuario")
        sys.exit(130)
    except Exception as e:
        print(f"\n[fatal] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
