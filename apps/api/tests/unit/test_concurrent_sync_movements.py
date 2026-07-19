"""
Tests de concurrencia sync para ``begin_immediate_transaction`` (regresion [T-1]).

FIX [T-1 auditoria-fase-1-2-2026-07-14]: ``_immediate_transaction`` ahora
delega en ``SQLiteDatabase.begin_immediate_transaction()`` que SI adquiere
el ``RLock``. Antes se accedía a ``self._db._connection`` directamente
y se saltaba el lock — esto permitia que dos writers emitieran
``BEGIN IMMEDIATE`` simultaneamente sobre la misma conexion.

Estos tests validan el contrato del nuevo método:
- Adquiere ``self._lock`` (un segundo thread que pide el lock queda bloqueado).
- Emite ``BEGIN IMMEDIATE`` en la conexion.
- Hace ``commit`` al salir normal del bloque.
- Hace ``rollback`` al lanzar una excepcion dentro del bloque.
- Es re-entrante (varios ``begin_immediate_transaction`` anidados
  funcionan via ``RLock``).

FIX Deuda #3 (resuelta): ``MovementEngine.register()`` ahora hace
TODAS las operaciones (incluidas las lecturas de warehouse/product/
stock_level) bajo el ``_immediate_transaction()``. Antes las lecturas
estaban fuera del lock, lo que permitia oversell en SQLite in-memory
multi-thread. Ver ``tests/unit/test_movement_engine_thread_safety.py``
para los tests E2E end-to-end del flujo completo con 2/5 threads
concurrentes.
"""
from __future__ import annotations

import threading
import time
import unittest

from app.db.session import create_database


class BeginImmediateTransactionTestCase(unittest.TestCase):
    """Tests del nuevo ``SQLiteDatabase.begin_immediate_transaction()``."""

    def setUp(self) -> None:
        self.db = create_database(":memory:")

    def tearDown(self) -> None:
        self.db.close()

    def test_emits_begin_immediate_and_commits(self) -> None:
        """BEGIN IMMEDIATE se emite; el commit persiste la fila."""
        with self.db.begin_immediate_transaction():
            self.db.execute("CREATE TABLE t (x INT)")
            self.db.execute("INSERT INTO t VALUES (42)")

        # Tras commit, la fila debe persistir (estamos fuera de transaccion).
        row = self.db.query_one("SELECT x FROM t")
        self.assertIsNotNone(row)
        self.assertEqual(row["x"], 42)

    def test_rollback_on_exception(self) -> None:
        """Una excepcion dentro del bloque dispara ROLLBACK."""
        self.db.execute("CREATE TABLE t (x INT)")

        with self.assertRaises(RuntimeError), self.db.begin_immediate_transaction():
            self.db.execute("INSERT INTO t VALUES (1)")
            raise RuntimeError("boom")

        # La fila insertada debe haberse perdido.
        row = self.db.query_one("SELECT x FROM t")
        self.assertIsNone(row)

    def test_rlock_serializes_writers(self) -> None:
        """Un segundo thread que pide ``begin_immediate_transaction`` se bloquea
        hasta que el primero sale del bloque. Esto es exactamente lo que
        el bug [T-1] rompía antes del fix.
        """
        acquired_at: dict[str, float] = {}
        finished_at: dict[str, float] = {}

        def worker_a() -> None:
            with self.db.begin_immediate_transaction():
                acquired_at["a"] = time.monotonic()
                time.sleep(0.3)  # simula trabajo bajo el lock
            finished_at["a"] = time.monotonic()

        def worker_b() -> None:
            # Espera activa corta para garantizar que A adquiere primero.
            time.sleep(0.05)
            with self.db.begin_immediate_transaction():
                acquired_at["b"] = time.monotonic()
            finished_at["b"] = time.monotonic()

        ta = threading.Thread(target=worker_a)
        tb = threading.Thread(target=worker_b)
        ta.start()
        tb.start()
        ta.join(timeout=5)
        tb.join(timeout=5)
        self.assertFalse(ta.is_alive(), "thread A hung")
        self.assertFalse(tb.is_alive(), "thread B hung")

        # A debe haber adquirido ANTES que B.
        self.assertLess(acquired_at["a"], acquired_at["b"])
        # B debe haber adquirido DESPUÉS de que A terminara
        # (A tardó ~0.3s bajo el lock; B debe entrar después).
        self.assertGreater(acquired_at["b"], finished_at["a"] - 0.05)

    def test_rlock_is_reentrant(self) -> None:
        """``begin_immediate_transaction`` puede anidarse (vía RLock)."""
        with self.db.begin_immediate_transaction():
            self.db.execute("CREATE TABLE t (x INT)")
            with self.db.begin_immediate_transaction():
                self.db.execute("INSERT INTO t VALUES (1)")

        row = self.db.query_one("SELECT x FROM t")
        self.assertEqual(row["x"], 1)

    def test_does_not_double_begin_when_already_in_transaction(self) -> None:
        """Si la conexión ya está en transacción, NO emite otro BEGIN.

        Esto evita el caso patológico que el bug [T-1] generaba: dos
        threads veían ``in_transaction == False`` simultáneamente y
        ambos emitían ``BEGIN IMMEDIATE``.
        """
        with self.db.begin_immediate_transaction():
            in_tx_inside = self.db._connection.in_transaction  # noqa: SLF001
            self.assertTrue(in_tx_inside)
        # Fuera del bloque, la transacción ya terminó.
        in_tx_after = self.db._connection.in_transaction  # noqa: SLF001
        self.assertFalse(in_tx_after)


if __name__ == "__main__":
    unittest.main()
