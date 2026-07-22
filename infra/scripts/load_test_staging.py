"""
Wrapper para correr load test contra STAGING (C4.5).

Ejecuta el load_test.py existente con perfil 'smoke' (5 concurrentes, 30s)
o 'normal' (20 concurrentes, 60s) y reporta resultados.

Uso:
  python infra/scripts/load_test_staging.py \\
      --base-url http://localhost:8080 \\
      --profile smoke

Perfiles disponibles (heredados de load_test.py):
  smoke  : 5 concurrentes, 30s
  normal : 20 concurrentes, 60s
  peak   : 50 concurrentes, 60s
  stress : 100 concurrentes, 60s

Salida:
  - Imprime p50, p95, p99, RPS, error rate
  - Exit 0 si pasa, 1 si error rate > 1%
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Load test contra staging")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin12345")
    parser.add_argument(
        "--profile",
        choices=["smoke", "normal", "peak", "stress"],
        default="smoke",
        help="Perfil de carga (default: smoke para staging)",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=0,
        help="Override del numero de concurrentes (0 = usar el del perfil)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Override de la duracion en segundos (0 = usar la del perfil)",
    )
    args = parser.parse_args()

    script = Path(__file__).resolve().parents[2] / "auditoria-fase5" / "load_test.py"
    if not script.exists():
        print(f"ERROR: no se encontro {script}")
        return 1

    cmd = [
        sys.executable,
        str(script),
        "--base-url", args.base_url,
        "--username", args.username,
        "--password", args.password,
        "--profile", args.profile,
    ]
    if args.concurrent > 0:
        cmd.extend(["--concurrent", str(args.concurrent)])
    if args.duration > 0:
        cmd.extend(["--duration", str(args.duration)])

    print("=" * 70)
    print(f"LOAD TEST ({args.profile}) contra {args.base_url}")
    print("=" * 70)
    print(f"Comando: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, env=os.environ.copy())
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
