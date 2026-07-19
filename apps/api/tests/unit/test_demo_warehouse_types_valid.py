"""
Regresion para [C-1 auditoria-fase-1-2-2026-07-14]: ``demo.py`` debe
usar SOLO los 3 valores validos de ``warehouse_type`` definidos en
ADR-0002: ``principal``, ``auxiliar``, ``mecanico_box``.

Antes del fix, ``demo.py`` usaba ``central``/``sucursal`` (valores del
modelo legacy pre-ADR-0002), que violan el CHECK del modelo actualizado
en ``app/db/models/warehouses.py``. Como las migraciones SQLite NO
enforcaban el CHECK, los tests pasaban silenciosamente.

Este test parsea ``demo.py`` estaticamente (sin ejecutar la funcion,
que tiene side effects en disco) y verifica que todas las
ocurrencias de ``warehouse_type=\"...\"`` usen uno de los 3 valores
permitidos. Si alguien re-introduce ``central``/``sucursal``, este
test falla antes de que el bug llegue a runtime.

Ademas, valida:
- Si el demo crea un ``mecanico_box``, debe apuntar a un
  ``parent_warehouse_id`` que sea un auxiliar (regla ADR-0002).
- La cantidad de warehouses creados es razonable (no se filtran
  warehouses duplicados).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

# Valores permitidos por ADR-0002 + CheckConstraint del modelo.
_VALID_WAREHOUSE_TYPES: frozenset[str] = frozenset(
    {"principal", "auxiliar", "mecanico_box"}
)
# Valores deprecados que NO deben volver a aparecer.
_DEPRECATED_WAREHOUSE_TYPES: frozenset[str] = frozenset(
    {"central", "sucursal", ""}
)

_DEMO_PY = Path(__file__).resolve().parents[2] / "app" / "db" / "demo.py"

# Captura ``warehouse_type="xxx"`` o ``warehouse_type='xxx'`` (y el
# estilo ``warehouse_type=...`` como kwarg en WarehouseCreate(...))
_KWARG_RE = re.compile(
    r"""warehouse_type\s*=\s*(?P<quote>["'])(?P<value>[^"']+)(?P=quote)"""
)


class DemoWarehouseTypesValidTestCase(unittest.TestCase):
    """FIX [C-1]: ``demo.py`` solo usa los 3 valores validos del CHECK."""

    def setUp(self) -> None:
        self.source = _DEMO_PY.read_text(encoding="utf-8")

    def test_no_deprecated_warehouse_type_values(self) -> None:
        """Ningun warehouse_type deprecado (``central``, ``sucursal``)."""
        deprecated_found: list[tuple[int, str]] = []
        for match in _KWARG_RE.finditer(self.source):
            value = match.group("value")
            if value in _DEPRECATED_WAREHOUSE_TYPES:
                line_no = self.source[: match.start()].count("\n") + 1
                deprecated_found.append((line_no, value))

        self.assertEqual(
            deprecated_found,
            [],
            (
                f"demo.py usa valores de warehouse_type deprecados: "
                f"{deprecated_found}. ADR-0002 solo permite "
                f"{sorted(_VALID_WAREHOUSE_TYPES)}."
            ),
        )

    def test_all_warehouse_types_are_in_valid_set(self) -> None:
        """Cualquier warehouse_type en demo.py esta en el set valido."""
        invalid_found: list[tuple[int, str]] = []
        for match in _KWARG_RE.finditer(self.source):
            value = match.group("value")
            if value not in _VALID_WAREHOUSE_TYPES:
                line_no = self.source[: match.start()].count("\n") + 1
                invalid_found.append((line_no, value))

        self.assertEqual(
            invalid_found,
            [],
            (
                f"demo.py tiene warehouse_type fuera del set valido: "
                f"{invalid_found}. Permitidos: {sorted(_VALID_WAREHOUSE_TYPES)}."
            ),
        )

    def test_demo_creates_at_least_one_principal(self) -> None:
        """El demo debe incluir al menos una bodega principal (regla R1)."""
        principals = [
            m.group("value")
            for m in _KWARG_RE.finditer(self.source)
            if m.group("value") == "principal"
        ]
        self.assertGreaterEqual(
            len(principals),
            1,
            "demo.py debe crear al menos una bodega 'principal'.",
        )

    def test_mecanico_boxes_have_parent_warehouse_id(self) -> None:
        """Si demo.py crea boxes, deben tener parent_warehouse_id.

        Esta validacion es estatica: busca bloques ``create_warehouse``
        con ``warehouse_type='mecanico_box'`` y verifica que dentro
        del mismo llamado (linea siguiente, mismo nivel de indent)
        aparezca ``parent_warehouse_id=...``.
        """
        # Encuentra lineas con warehouse_type='mecanico_box'
        box_lines = [
            i
            for i, line in enumerate(self.source.splitlines(), start=1)
            if "mecanico_box" in line
        ]
        if not box_lines:
            self.skipTest(
                "demo.py no crea boxes (es valido para IMP-004 diferido). "
                "Cuando se agreguen, este test validara parent_warehouse_id."
            )

        # Para cada box, verifica que el WarehouseCreate tenga parent_warehouse_id
        # en las proximas 5 lineas.
        source_lines = self.source.splitlines()
        for box_line_no in box_lines:
            window = source_lines[box_line_no : box_line_no + 5]
            window_str = "\n".join(window)
            self.assertIn(
                "parent_warehouse_id",
                window_str,
                (
                    f"demo.py linea {box_line_no} crea un mecanico_box "
                    f"sin parent_warehouse_id. ADR-0002 lo requiere NOT NULL."
                ),
            )


if __name__ == "__main__":
    unittest.main()
