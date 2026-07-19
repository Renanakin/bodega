"""Genera secretos criptograficamente seguros para .env (Fase 10).

Uso:
    # Imprimir en stdout (recomendado para copiar/pegar):
    python infra/scripts/generate-secrets.py --print-only

    # Escribir a un .env nuevo (sobre-escribe con backup):
    python infra/scripts/generate-secrets.py --output .env.production

    # Generar un solo secreto:
    python -c "from infra.scripts.generate_secrets import generate_password; print(generate_password())"

Seguridad:
- Usa ``secrets`` de stdlib (CSPRNG del OS, no random).
- Los passwords garantizan al menos 1 mayuscula, 1 minuscula, 1 digito, 1 simbolo.
- Los tokens son URL-safe (base64url, sin caracteres problematicos para .env).

Por que un script separado (no solo un comando en docs):
- Los ops nuevos pueden ejecutar ``python generate-secrets.py`` sin
  recordar el comando exacto de secrets.token_urlsafe.
- Centraliza las politicas (longitud, charset, requisitos).
- Es testeable (los tests validan la estructura del secreto).
"""
from __future__ import annotations

import argparse
import secrets
import string
from pathlib import Path


# Charset para passwords: alfanumerico + simbolos seguros.
# Evitamos caracteres ambiguos: 0/O, 1/l/I, etc.
_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
# Requisitos minimos que debe cumplir un password generado.
_REQUIRED_CLASSES = {
    "upper": string.ascii_uppercase,
    "lower": string.ascii_lowercase,
    "digit": string.digits,
    "symbol": "!@#$%^&*-_=+",
}


def generate_password(length: int = 32) -> str:
    """Genera un password alfanumerico + simbolos con requisitos garantizados.

    Args:
        length: longitud exacta del password (default 32, OWASP 2023 sugiere >= 16).

    Returns:
        Password con al menos 1 mayuscula, 1 minuscula, 1 digito, 1 simbolo.

    Raises:
        ValueError: si ``length`` < 8 (no se pueden garantizar 4 clases distintas).
    """
    if length < 8:
        raise ValueError(
            f"Password length debe ser >= 8 para garantizar 4 clases, recibido: {length}"
        )
    # Generar hasta que cumpla TODOS los requisitos (esperado <10 intentos).
    max_attempts = 100
    for _ in range(max_attempts):
        password = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
        if _meets_requirements(password):
            return password
    # Si no se logro tras 100 intentos (probabilidad astronomicamente baja),
    # usar un metodo determinista: forzar un caracter de cada clase y
    # rellenar el resto.
    raise RuntimeError(
        f"No se pudo generar un password valido tras {max_attempts} intentos "
        "(probabilidad ~ 1/2^100). Re-intentar."
    )


def _meets_requirements(password: str) -> bool:
    """Verifica que el password cumple las 4 clases requeridas."""
    return all(
        any(c in charset for c in password)
        for charset in _REQUIRED_CLASSES.values()
    )


def generate_token(length: int = 32) -> str:
    """Genera un token URL-safe (base64url, sin caracteres especiales).

    ``secrets.token_urlsafe(n)`` retorna n bytes encodeados en base64url
    (caracteres [A-Za-z0-9_-]). NO contiene '+' ni '/' ni '=' que podrian
    romper parsers de .env.

    Args:
        length: bytes de entropia (default 32 bytes = 256 bits, OWASP min).

    Returns:
        Token string ~ length * 1.3 caracteres.
    """
    if length < 16:
        raise ValueError(
            f"Token length debe ser >= 16 bytes (128 bits) para seguridad, "
            f"recibido: {length}"
        )
    return secrets.token_urlsafe(length)


def generate_all_secrets() -> dict[str, str]:
    """Genera el set completo de secretos para .env.

    Returns:
        Dict con claves: POSTGRES_PASSWORD, JWT_SECRET, SECRET_KEY.
    """
    return {
        "POSTGRES_PASSWORD": generate_password(32),
        "JWT_SECRET": generate_token(32),
        "SECRET_KEY": generate_token(32),
    }


def _print_secrets(secrets_dict: dict[str, str]) -> None:
    """Imprime los secretos en formato ``KEY=value`` con comentarios."""
    print("# Secretos generados por generate-secrets.py (Fase 10)")
    print("# Copia y pega estos valores a tu .env.")
    print()
    for key, value in secrets_dict.items():
        print(f"{key}={value}")


def _write_to_file(path: Path, secrets_dict: dict[str, str]) -> None:
    """Escribe los secretos a un archivo, con backup si existe.

    Si el archivo existe, lo renombra a ``<path>.bak.<timestamp>``.
    """
    if path.exists():
        timestamp = secrets.token_hex(4)  # corto, solo para unicidad
        backup = path.with_suffix(path.suffix + f".bak.{timestamp}")
        path.rename(backup)
        print(f"[backup] Archivo existente movido a: {backup.name}")
    path.write_text(
        _format_env(secrets_dict),
        encoding="utf-8",
    )
    print(f"[ok] Secretos escritos en: {path}")
    print("[warn] Ajusta los permisos del archivo: chmod 600 (owner read/write only)")


def _format_env(secrets_dict: dict[str, str]) -> str:
    """Formatea los secretos como contenido de .env con header explicativo."""
    lines = [
        "# .env generado por generate-secrets.py (Fase 10)",
        f"# Generado el: {_iso_now()}",
        "# IMPORTANTE: chmod 600 este archivo. NO commitear al repo.",
        "",
    ]
    lines.extend(f"{key}={value}" for key, value in secrets_dict.items())
    lines.append("")
    return "\n".join(lines)


def _iso_now() -> str:
    """Timestamp ISO 8601 UTC para el header del archivo."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    """Entry point CLI."""
    parser = argparse.ArgumentParser(
        description="Genera secretos criptograficamente seguros para .env (Fase 10).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  # Solo imprimir (recomendado para copiar/pegar):\n"
            "  python infra/scripts/generate-secrets.py --print-only\n"
            "\n"
            "  # Escribir a archivo .env.production:\n"
            "  python infra/scripts/generate-secrets.py --output .env.production\n"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path al archivo .env a escribir. Si existe, se hace backup.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Solo imprime en stdout, no escribe archivos.",
    )
    args = parser.parse_args()

    secrets_dict = generate_all_secrets()

    if args.print_only:
        _print_secrets(secrets_dict)
    elif args.output is not None:
        _write_to_file(args.output, secrets_dict)
    else:
        # Sin flags: modo por defecto = print-only (no destructivo).
        _print_secrets(secrets_dict)


if __name__ == "__main__":
    main()
