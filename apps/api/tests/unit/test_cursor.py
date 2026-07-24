"""Tests para el cursor de paginacion (P0 roadmap Big-O)."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from uuid import UUID, uuid4

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET", "test-secret-must-be-at-least-32-chars-long-XXXX")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.core.cursor import (  # noqa: E402
    CURSOR_VERSION,
    InvalidCursorError,
    apply_cursor,
    decode_cursor,
    encode_cursor,
)
from app.db.models.products import Product  # noqa: E402, F401
from app.db.models.solicitudes import SolicitudRecarga  # noqa: E402
from sqlalchemy import select  # noqa: E402


class CursorEncodeDecodeTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        ts = datetime(2026, 7, 24, 10, 30, 0, tzinfo=timezone.utc)
        uid = UUID("12345678-1234-5678-1234-567812345678")
        c = encode_cursor(ts, uid)
        self.assertTrue(c.startswith(f"{CURSOR_VERSION}~"))
        ca, ci = decode_cursor(c)
        self.assertEqual(ca, ts)
        self.assertEqual(ci, uid)

    def test_decode_invalid_version_raises(self) -> None:
        with self.assertRaises(InvalidCursorError):
            decode_cursor("v999:abcd")

    def test_decode_empty_raises(self) -> None:
        with self.assertRaises(InvalidCursorError):
            decode_cursor("")

    def test_decode_no_version_separator_raises(self) -> None:
        with self.assertRaises(InvalidCursorError):
            decode_cursor("no-tilde-here")

    def test_decode_invalid_base64_raises(self) -> None:
        with self.assertRaises(InvalidCursorError):
            decode_cursor("v1:NOT_BASE64!!!")

    def test_decode_no_internal_separator_raises(self) -> None:
        import base64
        bad = base64.urlsafe_b64encode(b"no_separator_here").decode()
        with self.assertRaises(InvalidCursorError):
            decode_cursor(f"v1:{bad}")

    def test_decode_invalid_timestamp_raises(self) -> None:
        import base64
        bad = base64.urlsafe_b64encode(b"notatimestamp|12345678-1234-5678-1234-567812345678").decode()
        with self.assertRaises(InvalidCursorError):
            decode_cursor(f"v1:{bad}")

    def test_decode_invalid_uuid_raises(self) -> None:
        import base64
        bad = base64.urlsafe_b64encode(b"2026-07-24T10:30:00+00:00|not-a-uuid").decode()
        with self.assertRaises(InvalidCursorError):
            decode_cursor(f"v1:{bad}")


class ApplyCursorTests(unittest.TestCase):
    """Tests de apply_cursor con SQLAlchemy 2.0 select."""

    def test_apply_cursor_none_returns_unchanged(self) -> None:
        stmt = select(SolicitudRecarga).order_by(
            SolicitudRecarga.created_at.desc(),
            SolicitudRecarga.id.desc(),
        )
        before = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        result = apply_cursor(
            stmt, None, SolicitudRecarga.created_at, SolicitudRecarga.id
        )
        after = str(result.compile(compile_kwargs={"literal_binds": True}))
        # Sin cursor, el stmt no agrega WHERE
        self.assertEqual(before, after)

    def test_apply_cursor_empty_string_returns_unchanged(self) -> None:
        stmt = select(SolicitudRecarga)
        before = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        result = apply_cursor(
            stmt, "", SolicitudRecarga.created_at, SolicitudRecarga.id
        )
        after = str(result.compile(compile_kwargs={"literal_binds": True}))
        self.assertEqual(before, after)

    def test_apply_cursor_adds_where_clause(self) -> None:
        stmt = select(SolicitudRecarga).order_by(
            SolicitudRecarga.created_at.desc(),
            SolicitudRecarga.id.desc(),
        )
        ts = datetime(2026, 7, 24, 10, 0, 0, tzinfo=timezone.utc)
        uid = uuid4()
        cursor = encode_cursor(ts, uid)
        result = apply_cursor(
            stmt, cursor, SolicitudRecarga.created_at, SolicitudRecarga.id
        )
        # El stmt debe haber agregado un WHERE con OR/AND
        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("WHERE", compiled)
        # El cursor usa un timestamp que se serializa en el SQL
        # (puede aparecer como texto ISO en literal_binds)
        self.assertTrue(len(compiled) > len(str(stmt)))


if __name__ == "__main__":
    unittest.main()
