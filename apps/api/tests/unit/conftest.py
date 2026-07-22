"""
Conftest para tests unitarios.

Las fixtures async (async_engine, async_session) viven en tests/conftest.py
para ser compartidas con integration. Este archivo solo añade lo específico
de unit tests.

Los tests que usan ``unittest.IsolatedAsyncioTestCase`` con el patrón
async (engine SQLite temporal + AsyncSession seed) replican el helper
inline (``_AsyncTestBase``) en cada módulo. Esto es intencional:
pytest fixtures no funcionan dentro de unittest.TestCase, y la
inversión de dependencias de unittest requiere setUp explícito.
"""

from __future__ import annotations
