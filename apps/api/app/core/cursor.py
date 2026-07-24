"""
Cursor pagination helpers (P0 del roadmap Big-O).

Proposito:
- Reemplazar paginacion por `skip/offset` (O(n) en BD) por cursor
  O(log n + p) donde p = limit.
- Cursor es un string opaco (base64-encoded) que el cliente pasa
  sin entenderlo. Esto permite cambiar el esquema del cursor sin
  romper clientes (version implicita en el encoding).

Formato del cursor (interno, versionado):
    v1:<base64>     # version + payload base64
    payload = "<iso_timestamp>|<uuid>"

El cursor apunta al ULTIMO item de la pagina anterior. La siguiente
pagina devuelve items con (created_at, id) ESTRICTAMENTE MENOR que el
cursor (asumiendo orden DESC, que es el caso en todos nuestros listados).

Uso tipico:
    from app.core.cursor import decode_cursor, encode_cursor, apply_cursor

    # En el query:
    stmt = select(Model).order_by(Model.created_at.desc(), Model.id.desc())
    stmt = apply_cursor(stmt, cursor, Model.created_at, Model.id)
    stmt = stmt.limit(limit + 1)  # +1 para detectar has_more
    rows = (await session.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None

Big-O:
    - skip/offset en BD: O(n) (la BD tiene que leer y descartar n filas)
    - cursor (created_at, id) con indice: O(log n + p)

Requiere que la tabla tenga indice en (created_at, id) o equivalente
para que el seek sea O(log n). En nuestro caso ya tenemos
`solicitudes_recarga(estado, created_at)` y
`ordenes_compra(estado, created_at)`, mas el PK `id`.
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.sql import ColumnElement

# Version del formato. Si cambia el esquema, bump y manejamos fallback.
# Usamos '~' como separador interno porque ':' rompe los query strings
# URL (algunos clientes lo interpretan como puerto).
CURSOR_VERSION = "v1"
VERSION_SEP = "~"
INNER_SEP = "|"


class InvalidCursorError(ValueError):
    """Cursor malformado o de version incompatible."""


def encode_cursor(created_at: datetime, id: UUID | str) -> str:
    """Serializa un cursor a partir del ultimo item de la pagina.

    Args:
        created_at: timestamp del item.
        id: UUID del item (o string si es otra PK).

    Returns:
        String opaco (base64) listo para devolver al cliente.
        Formato: 'v1~<base64>' (sin ':' que rompe URLs).
    """
    payload = f"{created_at.isoformat()}{INNER_SEP}{str(id)}"
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return f"{CURSOR_VERSION}{VERSION_SEP}{encoded}"


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Deserializa un cursor del cliente.

    Raises:
        InvalidCursorError: si el formato es invalido o la version no coincide.
    """
    if not cursor:
        raise InvalidCursorError("cursor vacio")
    if VERSION_SEP not in cursor:
        raise InvalidCursorError("cursor sin separador de version")
    version, encoded = cursor.split(VERSION_SEP, 1)
    if version != CURSOR_VERSION:
        raise InvalidCursorError(
            f"version de cursor no soportada: {version!r} (esperado {CURSOR_VERSION!r})"
        )
    try:
        raw = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception as e:
        raise InvalidCursorError(f"cursor no es base64 valido: {e}") from e
    if INNER_SEP not in raw:
        raise InvalidCursorError("cursor base64 sin separador interno")
    ts_str, id_str = raw.split(INNER_SEP, 1)
    try:
        created_at = datetime.fromisoformat(ts_str)
    except ValueError as e:
        raise InvalidCursorError(f"timestamp invalido en cursor: {ts_str!r}") from e
    try:
        id_uuid = UUID(id_str)
    except ValueError as e:
        raise InvalidCursorError(f"id invalido en cursor: {id_str!r}") from e
    return created_at, id_uuid


def apply_cursor(
    stmt: Any,
    cursor: str | None,
    created_at_col: Any,
    id_col: Any,
) -> Any:
    """Aplica un cursor a un SELECT ordenando por (created_at DESC, id DESC).

    El cursor apunta al ULTIMO item de la pagina anterior. La siguiente
    pagina devuelve items con (created_at, id) estrictamente menor.

    Args:
        stmt: query SQLAlchemy.
        cursor: string opaco del cliente, o None para primera pagina.
        created_at_col: columna de timestamp (Model.created_at).
        id_col: columna de PK (Model.id).

    Returns:
        stmt con el WHERE adicional para el cursor (o sin cambios si cursor es None).
    """
    if not cursor:
        return stmt
    ca, ci = decode_cursor(cursor)
    # Para orden DESC: (created_at, id) < (cursor_ca, cursor_ci)
    # Se traduce a:
    #   created_at < cursor_ca
    #   OR (created_at = cursor_ca AND id < cursor_ci)
    where_clause: ColumnElement = or_(
        created_at_col < ca,
        and_(created_at_col == ca, id_col < ci),
    )
    return stmt.where(where_clause)


__all__ = [
    "CURSOR_VERSION",
    "InvalidCursorError",
    "apply_cursor",
    "decode_cursor",
    "encode_cursor",
]
