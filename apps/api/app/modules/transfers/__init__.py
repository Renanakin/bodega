"""
Transfers (DEPRECATED — reemplazado por solicitudes_recarga en Fase 3).

Este módulo se mantiene por compatibilidad con frontend legacy y reportes
historicos durante 6 meses (ver ADR-0003). Plan de retiro:
- Fase 3 (ahora): marca deprecated, agrega endpoint /derived.
- Fase 4+: el frontend migra a /api/v1/solicitudes.
- Mes 6 (aprox): retirar este modulo completamente.

Las escrituras (POST/PATCH/DELETE) responden 410 Gone con sugerencia
de usar /api/v1/solicitudes. Solo los GETs siguen funcionando.

Reglas:
- R1/R2/R3: este modulo no agrega logica nueva; delega en SolicitudService
  para el endpoint /derived.
"""
