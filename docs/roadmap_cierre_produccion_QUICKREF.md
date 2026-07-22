# Roadmap de Cierre — QuickRef

**5 fases · 5-6 semanas · 1 persona** → producción con cliente piloto

## Fases

| Fase | Nombre | Sem | Salida clave |
|---|---|---|---|
| **C1** | Higiene técnica | 1 | mypy 222→50, tests legacy cerrados, ADR-0007 |
| **C2** | Runbook operacional | 1 | Backup probado end-to-end, DR documentado |
| **C3** | Observabilidad operativa | 1 | 3 dashboards + 6 alertas en Grafana |
| **C4** | Staging con cliente piloto | 1 | 1 cliente real validó staging |
| **C5** | Go-live + hardening | 1 | HTTPS + pen-test + producción activa |

## Brechas (15 totales)

**ALTA (9):** A1 fix warehouses 409 · A2 docs transfers deprecated · A3 mypy
222 errores · A4 fix 3 tests observability · A5 backup probado · A6 refresh
tokens + rate limit user · A7 alertas Prometheus · A8 notifications/ vs
notificaciones/ · A9 limpiar `app.state.db` legacy

**MEDIA (4):** M1 OpenTelemetry · M4 ADR-0007 · M5 tests carga k6 · M6 cache Redis

**BAJA (7):** B1-B7 fase 2 (WebSockets, ABC, slotting, chat, multi-region, SOC2, etc.)

## Calendario

```
W1 (22-26 jul)  ── C1 Higiene ───────────────
W2 (29 jul-2 ago) ── C2 Runbook ──────────────
W3 (5-9 ago)     ── C3 Observabilidad ───────
W4 (12-16 ago)   ── C4 Staging + piloto ─────
W5 (19-23 ago)   ── C5 Go-live ──────────────
W6 (26-30 ago)   ── C5 + buffer ─────────────
```

## Primer paso (2 horas)

```
1. Crear branch sprint/c1-higiene
2. Fix A1: warehouses/router.py → 409 limpio
3. PR + CI verde + merge
```

## Estado actual (no rehacer)

- ✅ 19 módulos backend
- ✅ 11 migraciones SQL (0001-0009)
- ✅ 337 unit + 63 integration + 50/51 E2E
- ✅ CI 5 jobs verde
- ✅ Postgres migrado (commit cb1950b)
- ✅ Notificaciones in-app en transiciones
- ✅ Outbox + Arq worker para emails
- ✅ Nginx hardened + Sentry + logs JSON
- ✅ 4 docs propuesta_ejecutables/

## Criterio de éxito del cierre

Cumplir los 12 criterios de aceptación de la propuesta §20.
Resultado esperado: **11/12 plenos + 1/12 parcial** (WebSockets = fase 2).

## Riesgos principales

1. **Una sola persona** → tags por fase permiten retomar fácil
2. **Cliente piloto con feedback negativo** → buffer de 1 semana
3. **mypy Sprint 3 rompe código** → 337 tests como red de seguridad
4. **Restore lento** → probar en C2 antes de C5
5. **Alertas ruidosas** → thresholds generosos al inicio

## Decisiones pendientes

- Staging: misma máquina / VPS aparte → **aparte**
- Grafana: self-hosted / cloud free → **cloud free**
- Cliente piloto: 1 / varios → **1 primero**
- HTTPS: certbot / cloud LB → **según deploy**
- Pen-test: interno / externo → **interno (OWASP ZAP)**

Ver documento completo: [`roadmap_cierre_produccion.md`](./roadmap_cierre_produccion.md)
