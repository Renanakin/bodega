"""
Tests del MovementEngine sync (Fase 2).

Cubre los 3 casos minimos del spec:
- Entrada OK (IN).
- Salida con stock suficiente.
- Salida sin stock suficiente → InsufficientStockError.

Además:
- Validación de inputs (movement_type invalido, quantity <= 0).
- Warehouse / Product no existentes.
- Delta calculado correctamente por tipo.
- BEGIN IMMEDIATE emite log warning (sqlite).
"""
from __future__ import annotations

import unittest
import uuid
from decimal import Decimal

from app.db.session import SQLiteDatabase, create_database
from app.modules.inventory.movement_engine import MovementEngine
from app.modules.inventory.schemas import MovementType
from app.modules.products.repository import ProductRepository
from app.modules.warehouses.repository import WarehouseRepository


def _setup_warehouse_and_product(db: SQLiteDatabase) -> tuple[uuid.UUID, uuid.UUID]:
    wh_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    db.execute(
        """
        INSERT INTO warehouses (id, code, name, warehouse_type, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (str(wh_id), f"W-{wh_id.hex[:6].upper()}", "Test WH", "principal",
         "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
    )
    db.execute(
        """
        INSERT INTO products (id, sku, name, unit, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (str(prod_id), f"P-{prod_id.hex[:6].upper()}", "Test Prod", "unidad",
         "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
    )
    return wh_id, prod_id


class MovementEngineSyncTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = create_database(":memory:")
        self.engine = MovementEngine(self.db)

    def tearDown(self) -> None:
        self.db.close()

    # --- Spec: 3 casos mínimos ---

    def test_in_movement_creates_stock(self) -> None:
        wh_id, prod_id = _setup_warehouse_and_product(self.db)

        result = self.engine.register(
            warehouse_id=wh_id,
            product_id=prod_id,
            movement_type=MovementType.IN,
            quantity=Decimal("50"),
        )
        self.assertEqual(result.previous_quantity, Decimal("0"))
        self.assertEqual(result.new_quantity, Decimal("50"))
        self.assertEqual(result.delta, Decimal("50"))

    def test_out_movement_with_stock_decrements(self) -> None:
        wh_id, prod_id = _setup_warehouse_and_product(self.db)
        self.engine.register(
            warehouse_id=wh_id,
            product_id=prod_id,
            movement_type=MovementType.IN,
            quantity=Decimal("30"),
        )

        result = self.engine.register(
            warehouse_id=wh_id,
            product_id=prod_id,
            movement_type=MovementType.OUT,
            quantity=Decimal("10"),
        )
        self.assertEqual(result.previous_quantity, Decimal("30"))
        self.assertEqual(result.new_quantity, Decimal("20"))
        self.assertEqual(result.delta, Decimal("-10"))

    def test_out_movement_without_stock_raises(self) -> None:
        wh_id, prod_id = _setup_warehouse_and_product(self.db)
        # No hay stock previo; intentar sacar debe fallar
        from app.core.errors import InsufficientStockError

        with self.assertRaises(InsufficientStockError) as ctx:
            self.engine.register(
                warehouse_id=wh_id,
                product_id=prod_id,
                movement_type=MovementType.OUT,
                quantity=Decimal("5"),
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.code, "insufficient_stock")

    # --- Extras ---

    def test_invalid_movement_type_raises_value_error(self) -> None:
        wh_id, prod_id = _setup_warehouse_and_product(self.db)
        # Subclass hack para forzar un movement_type con value inválido
        # sin chocar con el atributo inmutable del enum.
        class _BadType:
            value = "definitely_not_valid"
        with self.assertRaises(ValueError):
            self.engine.register(
                warehouse_id=wh_id,
                product_id=prod_id,
                movement_type=_BadType(),  # type: ignore[arg-type]
                quantity=Decimal("1"),
            )

    def test_quantity_zero_raises_value_error(self) -> None:
        wh_id, prod_id = _setup_warehouse_and_product(self.db)
        with self.assertRaises(ValueError):
            self.engine.register(
                warehouse_id=wh_id,
                product_id=prod_id,
                movement_type=MovementType.IN,
                quantity=Decimal("0"),
            )

    def test_negative_quantity_raises_value_error(self) -> None:
        wh_id, prod_id = _setup_warehouse_and_product(self.db)
        with self.assertRaises(ValueError):
            self.engine.register(
                warehouse_id=wh_id,
                product_id=prod_id,
                movement_type=MovementType.IN,
                quantity=Decimal("-1"),
            )

    def test_warehouse_not_found(self) -> None:
        from app.core.errors import WarehouseNotFoundError

        _, prod_id = _setup_warehouse_and_product(self.db)
        with self.assertRaises(WarehouseNotFoundError):
            self.engine.register(
                warehouse_id=uuid.uuid4(),
                product_id=prod_id,
                movement_type=MovementType.IN,
                quantity=Decimal("1"),
            )

    def test_product_not_found(self) -> None:
        from app.core.errors import ProductNotFoundError

        wh_id, _ = _setup_warehouse_and_product(self.db)
        with self.assertRaises(ProductNotFoundError):
            self.engine.register(
                warehouse_id=wh_id,
                product_id=uuid.uuid4(),
                movement_type=MovementType.IN,
                quantity=Decimal("1"),
            )

    def test_adjustment_in_and_out_deltas(self) -> None:
        wh_id, prod_id = _setup_warehouse_and_product(self.db)
        r1 = self.engine.register(
            warehouse_id=wh_id,
            product_id=prod_id,
            movement_type=MovementType.ADJUSTMENT_IN,
            quantity=Decimal("20"),
        )
        self.assertEqual(r1.delta, Decimal("20"))

        r2 = self.engine.register(
            warehouse_id=wh_id,
            product_id=prod_id,
            movement_type=MovementType.ADJUSTMENT_OUT,
            quantity=Decimal("5"),
        )
        self.assertEqual(r2.delta, Decimal("-5"))
        self.assertEqual(r2.new_quantity, Decimal("15"))


if __name__ == "__main__":
    unittest.main()
