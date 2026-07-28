"""
Modulo: receipts (Recepciones de mercaderia).

FIX (FASE POST-E2E): este modulo estaba documentado en el manual seccion 8
pero NO implementado. La entrada de stock se hacia via
``POST /inventory/movements`` directamente, sin el flujo de 2 pasos
(crear pending + confirmar) que el manual describe.

Esta implementacion agrega:
- ``GET    /api/v1/receipts``            — listar recepciones
- ``POST   /api/v1/receipts``            — crear (estado pending, NO toca stock)
- ``GET    /api/v1/receipts/{id}``       — obtener
- ``POST   /api/v1/receipts/{id}/confirm`` — confirmar (genera movimientos in)
- ``POST   /api/v1/receipts/{id}/cancel``  — cancelar (solo pending)

Estados: ``pending`` -> ``confirmed`` | ``cancelled``.
Al confirmar, la OC relacionada (si existe) pasa a ``received`` y se
genera un ``InventoryMovement`` tipo ``in`` por cada linea.
"""
