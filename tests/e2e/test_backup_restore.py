"""Test E2E de backup + restore para bodegaje.

Verifica que el backup del servicio `bodegaje-backup`:
1. Existe y no es stale (< 25h).
2. Se puede restaurar a una BD Postgres temporal.
3. Despues de restaurar, las tablas tienen la misma cantidad de filas
   que la BD original (chequeo de integridad basico).

Si todo pasa, exit 0. Si falla, exit 1 con detalle.
"""
import gzip
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Container names (los del docker-compose.yml)
CONTAINER_BACKUP = "bodegaje-backup"
CONTAINER_DB = "bodegaje-db"
BACKUP_PATH = "/backups/bodegaje-latest.dump.gz"
TEMP_DB = "bodegaje_restore_test"


def run(cmd: list[str], check: bool = True, capture: bool = True) -> tuple[int, str, str]:
    """Run a command via PowerShell, return (rc, stdout, stderr)."""
    # Para evitar problemas con {} en PowerShell, usamos cmd.exe o construimos
    # la cadena con quoting cuidadoso.
    # En Windows, lo mas confiable es invocar docker via cmd.exe directo.
    # Aqui usamos lista -> call directo, no string -> PowerShell.
    proc = subprocess.run(cmd, capture_output=capture, text=True, shell=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"cmd failed ({proc.returncode}): {cmd}\n{proc.stderr}")
    return proc.returncode, proc.stdout, proc.stderr


def docker_exec(container: str, cmd: str, check: bool = True) -> tuple[int, str, str]:
    """Ejecuta cmd dentro de un container via docker exec."""
    return run(["docker", "exec", container, "sh", "-c", cmd], check=check)


def main() -> int:
    failures: list[str] = []

    # 1) El servicio de backup esta corriendo?
    rc, out, _ = run(["docker", "ps", "--filter", f"name={CONTAINER_BACKUP}", "--format", "{{.Status}}"])
    if "Up" not in out:
        failures.append(f"servicio {CONTAINER_BACKUP} no esta corriendo: {out}")
        print("FAIL: backup no esta corriendo")
        return 1
    print(f"[OK] {CONTAINER_BACKUP} corriendo: {out.strip()}")

    # 2) Hay backup y no es stale
    rc, out, _ = docker_exec(CONTAINER_BACKUP, "ls -la /backups/")
    print(f"[INFO] contenido /backups:\n{out}")

    rc, age, _ = docker_exec(CONTAINER_BACKUP, "stat -c %Y /backups/bodegaje-latest.dump.gz")
    if rc != 0:
        failures.append("no existe bodegaje-latest.dump.gz")
        return 1
    mtime = int(age.strip())
    now_ts = int(datetime.now(timezone.utc).timestamp())
    age_h = (now_ts - mtime) / 3600
    print(f"[OK] ultimo backup tiene {age_h:.1f}h (max 25h)")
    if age_h > 25:
        failures.append(f"ultimo backup tiene {age_h:.1f}h (>25h, stale)")

    # 3) Tamanio minimo razonable (>= 1KB). Usamos -L para seguir
    # el symlink y obtener el tamaño del archivo real.
    rc, size_str, _ = docker_exec(CONTAINER_BACKUP, "stat -L -c %s /backups/bodegaje-latest.dump.gz")
    size = int(size_str.strip())
    if size < 1024:
        failures.append(f"backup demasiado pequeno: {size} bytes")
    else:
        print(f"[OK] backup {size} bytes")

    # 4) gzip descomprime OK
    rc, out, _ = docker_exec(CONTAINER_BACKUP, "gzip -t /backups/bodegaje-latest.dump.gz && echo OK || echo FAIL")
    if "OK" not in out:
        failures.append("gzip integridad fallida")
    else:
        print("[OK] gzip integridad OK")

    # 5) Crear BD temporal, restaurar, comparar counts
    print("\n=== Test restore a BD temporal ===")
    # Drop si existe de un test previo
    docker_exec(CONTAINER_DB, f"psql -U bodegaje -d postgres -c 'DROP DATABASE IF EXISTS {TEMP_DB};'", check=False)
    # Crear
    docker_exec(CONTAINER_DB, f"psql -U bodegaje -d postgres -c 'CREATE DATABASE {TEMP_DB};'")
    print(f"[OK] BD {TEMP_DB} creada")

    # Copiar dump al host. Importante: docker cp no sigue symlinks, hay
    # que copiar el archivo real (resolvemos el symlink primero).
    rc, real_path, _ = docker_exec(CONTAINER_BACKUP, "readlink -f /backups/bodegaje-latest.dump.gz")
    real_path = real_path.strip()
    print(f"[INFO] symlink resuelve a: {real_path}")
    tmp_local = Path(r"C:\Users\Tranquilidad\AppData\Local\Temp\test_restore.dump.gz")
    rc, _, _ = run(["docker", "cp", f"{CONTAINER_BACKUP}:{real_path}", str(tmp_local)])
    print(f"[OK] dump copiado a {tmp_local} ({tmp_local.stat().st_size} bytes)")

    # Copiar al contenedor de la BD
    rc, _, _ = run(["docker", "cp", str(tmp_local), f"{CONTAINER_DB}:/tmp/restore.dump.gz"])
    print("[OK] dump copiado al contenedor db")

    # Restore
    rc, out, err = docker_exec(
        CONTAINER_DB,
        "gunzip -c /tmp/restore.dump.gz | pg_restore -U bodegaje -d bodegaje_restore_test --no-owner --no-privileges 2>&1 | tail -20 || true",
    )
    print(f"[INFO] pg_restore output:\n{out}")

    # 6) Comparar counts de las tablas principales.
    # NOTA: el backup es diario (3am), asi que si han pasado < 24h
    # los counts deben coincidir exactamente. Si han pasado mas, es
    # esperable que el backup tenga menos filas en tablas de transaccion
    # (solicitudes, movimientos, audit). En ese caso, registramos como
    # INFO y seguimos, porque la integridad del backup en si es OK.
    tablas_exactas = ["warehouses", "products", "stock_levels", "users"]
    tablas_transaccionales = ["solicitudes_recarga"]
    print("\n=== Comparacion de counts ===")

    for t in tablas_exactas:
        rc_orig, orig, _ = docker_exec(
            CONTAINER_DB, f"psql -U bodegaje -d bodegaje -tAc 'SELECT count(*) FROM {t};'"
        )
        rc_test, test, _ = docker_exec(
            CONTAINER_DB, f"psql -U bodegaje -d {TEMP_DB} -tAc 'SELECT count(*) FROM {t};'"
        )
        o = orig.strip()
        t_val = test.strip()
        if o == t_val:
            print(f"  [OK] {t}: original={o}, restored={t_val}")
        else:
            failures.append(f"{t}: original={o} != restored={t_val}")
            print(f"  [FAIL] {t}: original={o} != restored={t_val}")

    for t in tablas_transaccionales:
        rc_orig, orig, _ = docker_exec(
            CONTAINER_DB, f"psql -U bodegaje -d bodegaje -tAc 'SELECT count(*) FROM {t};'"
        )
        rc_test, test, _ = docker_exec(
            CONTAINER_DB, f"psql -U bodegaje -d {TEMP_DB} -tAc 'SELECT count(*) FROM {t};'"
        )
        o = int(orig.strip())
        t_val = int(test.strip())
        if o == t_val:
            print(f"  [OK] {t}: original={o}, restored={t_val}")
        elif t_val < o:
            # Backup es mas viejo: se han creado filas desde el backup.
            # Es esperado, no es fallo del backup en si.
            drift = o - t_val
            print(
                f"  [INFO] {t}: original={o}, restored={t_val} "
                f"(drift={drift} filas creadas desde el backup - esperado si backup > 1h)"
            )
        else:
            # restored > original: anomalía, el backup tendría mas filas que la BD
            # actual. Esto sí es un problema.
            failures.append(f"{t}: original={o}, restored={t_val} (anomalia: backup > actual)")
            print(f"  [FAIL] {t}: original={o} < restored={t_val} (backup tiene mas filas!)")

    # 7) Cleanup
    docker_exec(CONTAINER_DB, f"psql -U bodegaje -d postgres -c 'DROP DATABASE {TEMP_DB};'", check=False)
    docker_exec(CONTAINER_DB, "rm -f /tmp/restore.dump.gz", check=False)
    tmp_local.unlink(missing_ok=True)
    print("[OK] cleanup")

    print("\n=== RESUMEN ===")
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("[OK] backup + restore verificados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
