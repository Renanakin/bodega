"""
Seguridad centralizada: hashing de passwords, tokens de sesión, tokens de aprobación.

Reglas de Oro aplicadas:
- R1: nunca usa secretos hardcoded; recibe todo via Settings.
- R6: el código de hash está parametrizado por configuración.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import utcnow
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

log = get_logger(__name__)


# --- Password hashing (R1, R6) ---

def hash_password(password: str, salt: str | None = None) -> str:
    """Hashea una contraseña con PBKDF2-HMAC-SHA256.

    Args:
        password: contraseña en texto plano.
        salt: salt opcional (generado si no se pasa).

    Returns:
        String formato "salt$digest" listo para almacenar.
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
    """Verifica una contraseña contra su hash almacenado.

    Usa compare_digest para evitar timing attacks.
    """
    try:
        salt, expected_digest = stored_hash.split("$", 1)
    except ValueError:
        log.warning("security.invalid_hash_format")
        return False
    candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, f"{salt}${expected_digest}")


# --- Tokens de sesión (R1) ---

def issue_session_token() -> str:
    """Genera un token de sesión criptográficamente seguro (URL-safe)."""
    return secrets.token_urlsafe(32)


def session_expiration() -> Any:
    """Calcula la fecha de expiración de la sesión según Settings."""
    hours = get_settings().session_duration_hours
    return utcnow() + timedelta(hours=hours)


# --- Tokens de aprobación (ADR-0006) ---

class ApprovalTokenError(Exception):
    """Error al validar un token de aprobación."""


class ApprovalTokenExpiredError(ApprovalTokenError):
    pass


class ApprovalTokenInvalidError(ApprovalTokenError):
    pass


def _get_serializer() -> URLSafeTimedSerializer:
    """Devuelve el serializer de approval tokens (ADR-0005/0006, Fase 10).

    Usa ``settings.secret_key`` si esta configurado (defense in depth,
    RECOMENDADO en produccion). Si no, hace fallback a ``jwt_secret``
    (compat dev/test — permite que la API funcione sin setear SECRET_KEY
    en development, donde el aislamiento de secretos no es critico).
    """
    settings = get_settings()
    if settings.secret_key is not None:
        secret = settings.secret_key.get_secret_value()
    else:
        # Fallback: en dev/test usamos jwt_secret. En produccion, el
        # model_validator de Settings rechaza configuration sin secret_key.
        secret = settings.jwt_secret.get_secret_value()
    return URLSafeTimedSerializer(
        secret_key=secret,
        salt="bodegaje-approval-token",
    )


def issue_approval_token(
    orden_id: str,
    supervisor_id: str,
    action: str,
    jti: str,
) -> str:
    """Emite un token de aprobación firmado (ADR-0006).

    Args:
        orden_id: UUID de la orden de compra.
        supervisor_id: UUID del supervisor.
        action: "approve" o "reject".
        jti: UUID único del token (para idempotencia).

    Returns:
        Token URL-safe firmado.
    """
    serializer = _get_serializer()
    payload = {
        "orden_id": orden_id,
        "supervisor_id": supervisor_id,
        "action": action,
        "jti": jti,
    }
    return serializer.dumps(payload)


def verify_approval_token(token: str) -> dict[str, Any]:
    """Verifica y deserializa un token de aprobación.

    Raises:
        ApprovalTokenExpiredError: si el token expiró.
        ApprovalTokenInvalidError: si la firma no es válida.

    Returns:
        Payload original con orden_id, supervisor_id, action, jti.
    """
    settings = get_settings()
    max_age_seconds = settings.approval_token_max_age_days * 24 * 3600
    serializer = _get_serializer()
    try:
        payload = serializer.loads(token, max_age=max_age_seconds)
    except SignatureExpired as e:
        raise ApprovalTokenExpiredError(str(e)) from e
    except BadSignature as e:
        raise ApprovalTokenInvalidError(str(e)) from e
    return payload
