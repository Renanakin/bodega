"""
Wrapper para correr la bateria E2E contra STAGING (C4.4).

Hace:
  1. Health check de staging
  2. Login con admin
  3. Ejecuta bateria_e2e_demo.py (51 pasos, 9 modulos)
  4. Reporta resultados y exit code

Uso:
  python infra/scripts/run_e2e_staging.py \\
      --base-url http://localhost:8080 \\
      --admin-username admin \\
      --admin-password admin12345

Salida:
  - Imprime cada step con [OK]/[FAIL]
  - Exit 0 si 51/51 pasan
  - Exit 1 si algun step falla
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import httpx


async def healthcheck(base_url: str) -> bool:
    """Verifica que staging esta vivo antes de empezar la bateria."""
    async with httpx.AsyncClient(base_url=base_url, timeout=10) as client:
        try:
            r = await client.get("/api/v1/health/live")
            if r.status_code == 200:
                print(f"[OK] health check: {r.json()}")
                return True
            print(f"[FAIL] health check: status {r.status_code}")
            return False
        except Exception as e:
            print(f"[FAIL] health check: {e}")
            return False


async def login(base_url: str, username: str, password: str) -> str:
    """Hace login y devuelve el token (vacio si falla)."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        r = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        if r.status_code != 200:
            print(f"[FAIL] login: status {r.status_code} {r.text}")
            return ""
        print(f"[OK] login como {username}")
        return r.json().get("token", "")


def run_bateria(base_url: str, username: str, password: str) -> int:
    """Ejecuta la bateria E2E completa."""
    script = Path(__file__).resolve().parents[2] / "auditoria-fase5" / "bateria_e2e_demo.py"
    if not script.exists():
        print(f"[FAIL] no se encontro {script}")
        return 1

    # La bateria usa variables de entorno para base-url y credenciales.
    env = os.environ.copy()
    env["BATERIA_BASE_URL"] = base_url
    env["BATERIA_USERNAME"] = username
    env["BATERIA_PASSWORD"] = password

    print(f"\n[3/3] Ejecutando bateria E2E: {script.name}")
    result = subprocess.run([sys.executable, str(script)], env=env)
    return result.returncode


async def main() -> int:
    parser = argparse.ArgumentParser(description="Bateria E2E contra staging")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password", default="admin12345")
    args = parser.parse_args()

    print("=" * 70)
    print(f"BATERIA E2E STAGING (base_url={args.base_url})")
    print("=" * 70)

    # 1. Health check
    if not await healthcheck(args.base_url):
        print("\n[FAIL] staging no responde. Verifica que el stack este corriendo:")
        print("  docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.staging.yml ps")
        return 1

    # 2. Login
    token = await login(args.base_url, args.admin_username, args.admin_password)
    if not token:
        print("\n[FAIL] login fallo. Verifica las credenciales.")
        return 1

    # 3. Bateria
    rc = run_bateria(args.base_url, args.admin_username, args.admin_password)
    if rc == 0:
        print("\n" + "=" * 70)
        print("[OK] BATERIA E2E: 51/51 pasos pasaron. Staging listo para cliente piloto.")
        print("=" * 70)
    else:
        print("\n" + "=" * 70)
        print(f"[FAIL] BATERIA E2E: codigo de salida {rc}. Revisar logs arriba.")
        print("=" * 70)
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
