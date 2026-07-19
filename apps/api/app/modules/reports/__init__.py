"""Reportes operacionales: KPIs ejecutivo, agregaciones para export (Fase 8).

Endpoints:
- ``GET /api/v1/reports/ejecutivo``             — JSON con KPIs agregados.
- ``GET /api/v1/reports/inventario``            — placeholder CSV (Fase 6 ya
  expone el inventario via ``/inventory/stock``; aqui solo se documenta la
  ruta para que el front la pueda consumir si quiere).
- ``GET /api/v1/reports/transferencias``        — placeholder CSV.
- ``GET /api/v1/reports/historial``             — placeholder CSV.

El endpoint ejecutivo es la novedad de Fase 8: snapshot agregado que el
ReportPage consume para renderizar la tab "Ejecutivo" y para el export PDF
(generado en el cliente con `jsPDF` para evitar dependencia server-side).
"""
