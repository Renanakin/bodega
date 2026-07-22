"""Shim de compatibilidad: ``app.modules.auth.security`` → ``app.core.security``.

C1.11 (cierre de producción): consolidar las dos implementaciones de
hashing/sesión que existían en paralelo. Ahora este módulo solo
re-exporta desde ``app.core.security``, manteniendo la API legacy
para callers que importaban desde acá (9 archivos de tests +
``app.db.demo`` + ``app.modules.auth.service``).

Migración de callers: la recomendación es migrar a::

    from app.core.security import hash_password, verify_password

Este shim se conservará por 6 meses y luego se eliminará
(ver ADR-0007 PBKDF2 + decisión de C1.11).
"""

from __future__ import annotations

from app.core.security import (  # noqa: F401
    hash_password,
    issue_session_token,
    session_expiration,
    verify_password,
)

# Backward-compat aliases: la versión legacy tenía nombres diferentes
# (``issue_token`` en lugar de ``issue_session_token``).
issue_token = issue_session_token

__all__ = [
    "hash_password",
    "verify_password",
    "issue_token",
    "issue_session_token",
    "session_expiration",
]
