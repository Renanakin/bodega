"""
test_prod_guard.py
==================

Valida el guard de aislamiento de `run_all.py` (FASE E del
`docs/plan_ejecucion_testing.md`).

Este test verifica que el orquestador:
1. Bloquea por defecto si BOD_API apunta a un endpoint sospechoso de prod.
2. Permite con --allow-prod explicito.
3. NO bloquea si BOD_API es localhost o 127.0.0.1.
4. Bloquea URLs con `prod.`, `production.`, `live.`, etc.

No hace requests HTTP, solo valida la logica del argparse/guard.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_ALL = HERE / "run_all.py"
PYTHON = sys.executable


def run_run_all(env: dict[str, str], extra_args: list[str] = ()) -> tuple[int, str, str]:
    """Corre `run_all.py` con el env dado. Devuelve (returncode, stdout, stderr)."""
    proc = subprocess.run(
        [PYTHON, str(RUN_ALL), "--help"],  # --help no corre tests, solo muestra el guard
        cwd=str(HERE),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_guard_bloquea_prod() -> None:
    """BOD_API=production.example.com sin --allow-prod debe ser bloqueado."""
    env = {"BOD_API": "https://production.bodega.com/api/v1"}
    # --help no llega a la fase de ejecucion, hay que usar un comando
    # que SI dispare el guard. Usamos un test inexistente + --help no
    # sirve. En su lugar, corremos run_all.py con un test dummy
    # (que va a fallar de otra forma, pero el guard se chequea ANTES).
    # Usamos ``--only nonexistent`` que activa el guard antes de fallar.
    proc = subprocess.run(
        [PYTHON, str(RUN_ALL), "--only", "nonexistent_test_for_guard"],
        cwd=str(HERE),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )
    # El guard retorna rc=2 cuando bloquea. Si bloquea: rc=2.
    # Si NO bloquea: rc=2 tambien (por "test no encontrado").
    # La diferencia esta en stderr/stdout: el guard imprime "[BLOCK]".
    output = proc.stdout + proc.stderr
    assert "[BLOCK]" in output, (
        f"Guard NO bloqueo prod. Output: {output[:500]}"
    )
    assert "produccion" in output.lower(), (
        f"Mensaje de bloqueo no encontrado. Output: {output[:500]}"
    )
    print("[OK] Guard bloqueo production.bodega.com")


def test_guard_bloquea_live() -> None:
    """BOD_API=live.example.com sin --allow-prod debe ser bloqueado."""
    env = {"BOD_API": "https://live.bodega.com/api/v1"}
    proc = subprocess.run(
        [PYTHON, str(RUN_ALL), "--only", "nonexistent_test_for_guard"],
        cwd=str(HERE),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = proc.stdout + proc.stderr
    assert "[BLOCK]" in output, (
        f"Guard NO bloqueo live. Output: {output[:500]}"
    )
    print("[OK] Guard bloqueo live.bodega.com")


def test_guard_bloquea_staging() -> None:
    """BOD_API=staging-bodega.com sin --allow-prod debe ser bloqueado
    (staging esta en la lista de bloqueo por seguridad: si alguien
    piensa que es prod, podria romper datos de staging)."""
    env = {"BOD_API": "https://staging-bodega.com/api/v1"}
    proc = subprocess.run(
        [PYTHON, str(RUN_ALL), "--only", "nonexistent_test_for_guard"],
        cwd=str(HERE),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = proc.stdout + proc.stderr
    assert "[BLOCK]" in output, (
        f"Guard NO bloqueo staging. Output: {output[:500]}"
    )
    print("[OK] Guard bloqueo staging-bodega.com")


def test_guard_permite_localhost() -> None:
    """BOD_API=http://localhost:8080 NO debe ser bloqueado."""
    env = {"BOD_API": "http://localhost:8080/api/v1"}
    proc = subprocess.run(
        [PYTHON, str(RUN_ALL), "--only", "nonexistent_test_for_guard"],
        cwd=str(HERE),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = proc.stdout + proc.stderr
    assert "[BLOCK]" not in output, (
        f"Guard bloqueo localhost (incorrecto). Output: {output[:500]}"
    )
    # En este caso rc=2 es por "ningun test seleccionado" (el dummy
    # 'nonexistent_test_for_guard' no esta en TESTS).
    print(f"[OK] Guard NO bloqueo localhost (rc={proc.returncode})")


def test_guard_permite_127() -> None:
    """BOD_API=http://127.0.0.1:8080 NO debe ser bloqueado."""
    env = {"BOD_API": "http://127.0.0.1:8080/api/v1"}
    proc = subprocess.run(
        [PYTHON, str(RUN_ALL), "--only", "nonexistent_test_for_guard"],
        cwd=str(HERE),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = proc.stdout + proc.stderr
    assert "[BLOCK]" not in output, (
        f"Guard bloqueo 127.0.0.1 (incorrecto). Output: {output[:500]}"
    )
    print(f"[OK] Guard NO bloqueo 127.0.0.1 (rc={proc.returncode})")


def test_guard_allow_prod_explicito() -> None:
    """BOD_API=production.example.com + --allow-prod NO debe ser bloqueado
    por el guard (puede que el test dummy falle por otra razon, pero
    NO por bloqueo del guard)."""
    env = {"BOD_API": "https://production.bodega.com/api/v1"}
    proc = subprocess.run(
        [PYTHON, str(RUN_ALL), "--allow-prod", "--only", "nonexistent_test_for_guard"],
        cwd=str(HERE),
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = proc.stdout + proc.stderr
    assert "[BLOCK]" not in output, (
        f"--allow-prod no desactivo el guard. Output: {output[:500]}"
    )
    print(f"[OK] --allow-prod desactivo el guard (rc={proc.returncode})")


if __name__ == "__main__":
    tests = [
        test_guard_bloquea_prod,
        test_guard_bloquea_live,
        test_guard_bloquea_staging,
        test_guard_permite_localhost,
        test_guard_permite_127,
        test_guard_allow_prod_explicito,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {t.__name__}: {e}")
            failed += 1
    if failed:
        print(f"\n[EXIT 1] {failed} tests fallaron")
        sys.exit(1)
    print(f"\n[EXIT 0] Todos los {len(tests)} tests pasaron")
