"""Módulo ``auth.security`` (LEGACY path, Fase 0/1).

DEPRECATED: usar ``app.core.security`` para nuevos endpoints. Este modulo
se mantiene para compatibilidad con codigo legacy (Fase 0/1) que todavia
no migro a la API canónica.

Fase 10: ahora usa ``get_settings().password_hash_iterations`` (antes tenia
120_000 hardcoded). El default cambio a 600_000 (OWASP 2023), asi que los
hashes existentes se siguen validando (PBKDF2 es determinista con la misma
sal + iterations). Solo se re-hashean en el proximo login exitoso.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from app.core.config import get_settings
from app.db.session import utcnow

SESSION_DURATION = timedelta(hours=12)


def hash_password(password: str, salt: str | None = None) -> str:
    """Hashea password con PBKDF2-HMAC-SHA256.

    Usa el setting ``password_hash_iterations`` (Fase 10: default 600_000,
    OWASP 2023). Antes tenia 120_000 hardcoded.
    """
    iterations = get_settings().password_hash_iterations
    resolved_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        resolved_salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"{resolved_salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    salt, expected_digest = stored_hash.split("$", 1)
    candidate = hash_password(password, salt)
    return secrets.compare_digest(candidate, f"{salt}${expected_digest}")


def issue_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiration():
    return utcnow() + SESSION_DURATION
