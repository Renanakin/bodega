"""
Orquestador de seed para STAGING (C4.2 + C4.3).

Hace 2 cosas en orden:
  1. Crea 3 supervisores + 3 admins + 3 operadores origen + 3 operadores destino
     via /auth/users (endpoint admin) o via SQL directo si la API no permite
     crear usuarios (mas seguro para staging).
  2. Llama al seed_load_test_data.py existente con --size large para generar
     10 bodegas, 200 productos, stock, transferencias en distintos estados.

Uso:
  # Staging local (Docker Compose en puerto 8080)
  python infra/scripts/seed_staging.py \\
      --base-url http://localhost:8080 \\
      --admin-username admin --admin-password admin12345 \\
      --size large

Idempotencia:
  - Los usernames se generan con sufijo RUN_ID.
  - Los codigos de bodega/producto usan RUN_ID, asi que no chocan.
  - Si vuelves a correrlo, se duplica todo (no destructivo).

Salida:
  - Imprime resumen al final con los usuarios creados.
  - Codigo de salida 0 si todo OK, 1 si fallo.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import string
import subprocess
import sys
import time
import uuid
from pathlib import Path

# Anadir apps/api al path para usar la factory de sesion directa.
API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

# Setup env ANTES de importar la app
os.environ.setdefault("ENVIRONMENT", "staging")
os.environ.setdefault("LOG_LEVEL", "INFO")


def _gen_run_id() -> str:
    """RUN_ID unico por corrida (timestamp + random)."""
    return f"{int(time.time()) % 100000}{random.randint(100, 999)}"


def _gen_password() -> str:
    """Password random de 12 chars (suficiente para staging, NO para prod)."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=12))


async def seed_users(base_url: str, admin_token: str, run_id: str) -> dict:
    """Crea 3 usuarios de cada rol via SQL directo (mas confiable que via API).

    Returns: dict {rol: [username, password, full_name]}
    """
    # Importar solo aca para no contaminar env antes.
    from app.core.security import hash_password
    from app.db.models.supervisores import Supervisor
    from app.db.models.users import User, UserRole
    from app.db.session import get_session_factory, utcnow

    factory = get_session_factory()

    users_by_role: dict[str, list[tuple[str, str, str]]] = {
        "admin": [],
        "supervisor": [],
        "origen": [],
        "destino": [],
    }

    supervisores_emails = []

    async with factory() as session:
        # 1. Crear 3 supervisores (entidad separada de users)
        for i in range(1, 4):
            sup_email = f"supervisor{i}-{run_id}@staging.bodega.cl"
            sup_nombre = f"Supervisor Staging {i}"
            sup = Supervisor(
                id=uuid.uuid4(),
                email=sup_email,
                nombre=sup_nombre,
                cargo=f"Jefe de Bodega {i}",
                activo=True,
            )
            session.add(sup)
            supervisores_emails.append(sup_email)

        # 2. Crear 3 admins
        for i in range(1, 4):
            username = f"admin{i}-{run_id}"
            password = _gen_password()
            user = User(
                id=uuid.uuid4(),
                username=username,
                full_name=f"Admin Staging {i}",
                role=UserRole.ADMIN,
                password_hash=hash_password(password),
                is_active=True,
                created_at=utcnow(),
            )
            session.add(user)
            users_by_role["admin"].append((username, password, f"Admin Staging {i}"))

        # 3. Crear 3 supervisores (rol user)
        for i in range(1, 4):
            username = f"sup{i}-{run_id}"
            password = _gen_password()
            user = User(
                id=uuid.uuid4(),
                username=username,
                full_name=f"Supervisor {i}",
                role=UserRole.SUPERVISOR,
                password_hash=hash_password(password),
                is_active=True,
                created_at=utcnow(),
            )
            session.add(user)
            users_by_role["supervisor"].append((username, password, f"Supervisor {i}"))

        # 4. Crear 3 operadores origen
        for i in range(1, 4):
            username = f"origen{i}-{run_id}"
            password = _gen_password()
            user = User(
                id=uuid.uuid4(),
                username=username,
                full_name=f"Operador Origen {i}",
                role=UserRole.ORIGIN_OPERATOR,
                password_hash=hash_password(password),
                is_active=True,
                created_at=utcnow(),
            )
            session.add(user)
            users_by_role["origen"].append((username, password, f"Operador Origen {i}"))

        # 5. Crear 3 operadores destino
        for i in range(1, 4):
            username = f"destino{i}-{run_id}"
            password = _gen_password()
            user = User(
                id=uuid.uuid4(),
                username=username,
                full_name=f"Operador Destino {i}",
                role=UserRole.DESTINATION_OPERATOR,
                password_hash=hash_password(password),
                is_active=True,
                created_at=utcnow(),
            )
            session.add(user)
            users_by_role["destino"].append((username, password, f"Operador Destino {i}"))

        await session.commit()

    return {
        "users": users_by_role,
        "supervisores": supervisores_emails,
    }


def run_load_seed(base_url: str, admin_username: str, admin_password: str, size: str) -> int:
    """Llama al seed_load_test_data.py con el size elegido."""
    script = Path(__file__).resolve().parents[2] / "auditoria-fase5" / "seed_load_test_data.py"
    if not script.exists():
        print(f"ERROR: no se encontro {script}")
        return 1

    cmd = [
        sys.executable,
        str(script),
        "--base-url", base_url,
        "--username", admin_username,
        "--password", admin_password,
        "--size", size,
    ]
    print(f"\n[2/2] Ejecutando seed de datos: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=os.environ.copy())
    return result.returncode


async def get_admin_token(base_url: str, username: str, password: str) -> str:
    """Hace login con el admin inicial y devuelve el token."""
    import httpx

    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        if resp.status_code != 200:
            print(f"ERROR: login admin fallo ({resp.status_code}): {resp.text}")
            print("  (probable: el admin no fue sembrado o la password es incorrecta)")
            return ""
        return resp.json().get("token", "")


def print_summary(users: dict, supervisores: list[str], run_id: str, output_file: str | None = None) -> str:
    """Imprime y opcionalmente guarda un resumen con las credenciales."""
    lines = [
        "=" * 70,
        f"SEED STAGING COMPLETO (run_id={run_id})",
        "=" * 70,
        "",
        "SUPERVISORES (entidad separada; aprueban OC por email):",
    ]
    for email in supervisores:
        lines.append(f"  {email}")

    lines.append("")
    lines.append("USUARIOS CREADOS (3 por rol, password random):")
    for rol, lista in users.items():
        lines.append(f"\n  {rol.upper()}:")
        for username, password, full_name in lista:
            lines.append(f"    {username} / {password}  ({full_name})")

    lines.append("")
    lines.append("IMPORTANTE:")
    lines.append("  - Guarda este output (es la unica vez que veras las passwords).")
    lines.append("  - Cada usuario puede cambiar su password desde /auth/me en produccion.")
    lines.append("=" * 70)

    output = "\n".join(lines)
    print(output)

    if output_file:
        Path(output_file).write_text(output, encoding="utf-8")
        print(f"\nCredenciales guardadas en: {output_file}")

    return output


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed staging: usuarios + datos")
    parser.add_argument("--base-url", default="http://localhost:8080", help="URL del API")
    parser.add_argument("--admin-username", default="admin", help="Username del admin preexistente")
    parser.add_argument("--admin-password", default="admin12345", help="Password del admin preexistente")
    parser.add_argument("--size", choices=["small", "medium", "large"], default="medium",
                        help="Tamano del dataset (large = 50 bodegas, 2000 productos)")
    parser.add_argument("--output-file", default="",
                        help="Si se da, guarda las credenciales en este archivo")
    args = parser.parse_args()

    run_id = _gen_run_id()
    print(f"RUN_ID = {run_id}")
    print(f"Base URL = {args.base_url}")
    print(f"Size = {args.size}")

    # Paso 1: crear usuarios directamente en BD
    print(f"\n[1/2] Creando 3 usuarios por rol + 3 supervisores...")
    try:
        result = await seed_users(args.base_url, "", run_id)
    except Exception as e:
        print(f"ERROR creando usuarios: {e}")
        return 1

    # Paso 2: load seed via API (usa el admin preexistente)
    rc = run_load_seed(args.base_url, args.admin_username, args.admin_password, args.size)
    if rc != 0:
        print(f"ERROR: seed_load_test_data.py retorno {rc}")
        return rc

    # Resumen final
    output_file = args.output_file or None
    print_summary(result["users"], result["supervisores"], run_id, output_file)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
