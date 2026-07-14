from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from app.db.session import utcnow

SESSION_DURATION = timedelta(hours=12)


def hash_password(password: str, salt: str | None = None) -> str:
    resolved_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        resolved_salt.encode("utf-8"),
        120_000,
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
