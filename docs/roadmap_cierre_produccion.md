# Roadmap de Cierre — Producción Bodegaje

**Fecha:** 2026-07-22
**Autor:** Mavis + nano
**Estado:** BORRADOR EJECUTABLE — basado en docs vigentes y código actual
**Stack:** Backend FastAPI + Postgres 17 + Redis 8 + React 19 + Nginx

---

## TL;DR

El proyecto está **funcional al 100%** (337 unit + 63 integration + 50/51
E2E tests). El "cierre de producción" significa terminar de cerrar las
**15 brechas restantes** que separan "funciona en mi máquina con datos de
prueba" de "atender clientes piloto con SLA, alertas y backup probado".

| Fase | Nombre | Esfuerzo | Salida |
|---|---|---|---|
| **C1** | Higiene técnica | 3-4 días | mypy -50%, tests legacy cerrados |
| **C2** | Runbook operacional | 1 semana | Backup probado, DR documentado, on-call ready |
| **C3** | Observabilidad operativa | 1 semana | Dashboards + alertas en Grafana |
| **C4** | Staging con datos reales | 1 semana | Cliente piloto validado |
| **C5** | Go-live + hardening final | 1 semana | Producción con clientes reales |

**Total:** 5-6 semanas a 1 persona tiempo completo, o 3 semanas con 2.

---

## 0. Punto de partida (verificado)

Lo que **ya está hecho** y no se debe rehacer:

| Capacidad | Doc de soporte |
|---|---|
| 19 módulos backend | `apps/api/app/modules/` |
| 11 migraciones SQL (0001-0009) | `db/migrations/` |
| 337 unit tests + 63 integration + 50/51 E2E | pytest actual |
| CI 5 jobs verde | `.github/workflows/ci.yml` |
| Migración completa a Postgres | commit `cb1950b` |
| Notificaciones in-app en transiciones | `tests/unit/test_notificaciones_automated.py` |
| Outbox + Arq worker para emails | `db/migrations/sqlite/0009` + `apps/api/app/worker.py` |
| Nginx hardened + rate limit | `infra/nginx/` |
| Sentry opcional + logs JSON | `app/core/logging.py` |
| Runbook 21KB | `docs/operations/runbook.md` |
| Batería E2E 9 módulos | `auditoria-fase5/bateria_e2e_demo.py` |
| 4 documentos de propuesta | `docs/propuesta_ejecutables/` |

**Tests today:** 337 unit + 63 integration + 50/51 E2E = **450/451 ✅**

---

## 1. Brechas que separan del go-live

Cruce de `INFORME_FINAL_10_FASES.md §4`, `go_live_testing_runbook.md`,
`plan_mypy.md`, `HANDOFF_SESION_2026-07-15.md` y los 4 docs de
`propuesta_ejecutables/`.

### 1.1 Brechas ALTA (bloqueantes para go-live)

| # | Brecha | Doc fuente | Impacto | Esfuerzo |
|---|---|---|---|---|
| A1 | `warehouses.reject_duplicate_name` falla (test) | propuesta §6.2.1, handoff deuda #4 | UX inconsistente | XS (2h) |
| A2 | `transfers` 410 sin reemplazo claro en docs públicas | handoff deuda, `runbook` | Confusión cliente | S (1d) |
| A3 | mypy 222 errores sin cleanup planeado | `plan_mypy.md` | Deuda arrastrada | M (3-5d) |
| A4 | 3 tests pre-existentes fallan (`test_observability.py` structlog) | informe revisión | CI con noise | S (1d) |
| A5 | Backup Postgres **probado en restore** | runbook §10 | Riesgo de pérdida de datos | S (1d) |
| A6 | Refresh tokens / rate limit por usuario | `INFORME_FINAL §4.1 #4` | Auth bypass potencial | M (2d) |
| A7 | Sin alertas Prometheus → on-call | `INFORME_FINAL §4.2` | Ceguera operativa | M (3d) |
| A8 | `notifications/` (inglés) coexiste con `notificaciones/` (español) | handoff | Confusión devs | XS (4h) |
| A9 | `app.state.db` legacy sync aún activo (residual) | propuesta §3.1 | Doble fuente de verdad | S (1d) |

### 1.2 Brechas MEDIA (mejoras de calidad)

| # | Brecha | Doc fuente | Esfuerzo |
|---|---|---|---|
| M1 | Tracing distribuido OpenTelemetry | `INFORME_FINAL §4.2 #6` | L (5-7d) |
| M2 | Migración gradual de CSS plano a Tailwind | `INFORME_FINAL §4.2 #9` | XL (meses) |
| M3 | i18n (inglés además de español) | `INFORME_FINAL §4.2 #8` | L (5-7d) |
| M4 | ADR-0007 (PBKDF2 vs Argon2) | propuesta §6, deuda #6 | XS (2h) |
| M5 | Tests de carga con k6 (100 req/seg) | `INFORME_FINAL §4.2 #5` | M (3d) |
| M6 | Cache de queries frecuentes en Redis | `INFORME_FINAL §4.2 #15` | M (3d) |

### 1.3 Brechas BAJA (nice-to-have / fase 2)

| # | Brecha | Esfuerzo |
|---|---|---|
| B1 | WebSockets + outbox_eventos (tiempo real UI) | L (10d) |
| B2 | Reservas formales de stock | M (5d) |
| B3 | Clasificación ABC + ranking rotación | M (5d) |
| B4 | Slotting avanzado (zonas/racks/niveles) | L (10d) |
| B5 | Chat operacional | XL (meses) |
| B6 | Multi-region con read replicas | XL (meses) |
| B7 | SOC2 / ISO 27001 | XL (meses) |

**Total para go-live:** 9 brechas ALTA + 4 MEDIA críticas (M1, M4, M5) = **13 ítems**.

---

## 2. Plan por fases (C1-C5)

Cada fase tiene: objetivo, tareas, criterios de salida, riesgos.

### C1 — Higiene técnica (3-4 días)

**Objetivo:** cerrar las brechas técnicas chicas que no requieren
arquitectura, dejando el repo en estado "CI verde + deuda mínima".

**Tareas (12):**

1. **A1** — Fix `warehouses/router.py` para devolver 409 limpio en
   `reject_duplicate_name`. Test verde.
2. **A2** — Actualizar README + docs usuario para reflejar que
   `transfers` está deprecado y reemplazado por `solicitudes`.
3. **A4** — Fix 3 tests `test_observability.py` (structlog caplog config).
4. **A8** — Decidir: ¿se borra `notifications/` (inglés) o se mergea
   con `notificaciones/`? Documentar y ejecutar.
5. **A9** — Borrar `app.state.db` residual. Verificar que ningún
   router lo usa.
6. **M4** — Escribir ADR-0007 (PBKDF2 decisión + justificación).
7. **C1.7** — `mypy Sprint 1` de `plan_mypy.md` (`dict/list/tuple` con
   tipos en 33+5+3 líneas). Resultado: 222 → 178.
8. **C1.8** — `mypy Sprint 2` (`model_validate` en 6 routers).
   Resultado: 178 → 156.
9. **C1.9** — `mypy Sprint 3` agresivo (anotar ~110 funciones).
   Resultado: 156 → 50.
10. **C1.10** — Limpiar TODOs muertos en código. Buscar con
    `Select-String -Pattern "TODO|FIXME|XXX"` y decidir.
11. **C1.11** — Consolidar `app/modules/auth/security.py` en
    `app/core/security.py` (deuda #2 del informe).
12. **C1.12** — Tag `v1.0.0-rc1` al cerrar.

**Criterios de salida:**

- `pytest` verde: 450+ tests
- `mypy apps/api` ≤ 50 errores
- 0 TODO/FIXME en código de producción
- `git tag v1.0.0-rc1` pusheado

**Riesgos:** el mypy Sprint 3 puede romper imports. Mitigación:
trabajar en branch aparte, mergear con PR + CI verde.

---

### C2 — Runbook operacional probado (1 semana)

**Objetivo:** demostrar que las operaciones de disaster recovery
funcionan end-to-end. **Esto es lo que falta para go-live.**

**Tareas (8):**

1. **A5.1** — Script `pg_dump` diario: configurar cron en
   `infra/scripts/backup_postgres.sh` (ya existe, validar).
2. **A5.2** — Script `pg_restore` en local: validar que un backup
   de 100 MB se restaura en <5 min.
3. **A5.3** — **Test de restore real**: tomar un backup, matar el
   contenedor Postgres, restaurar, verificar que los 337 tests
   siguen pasando contra la BD restaurada.
4. **A5.4** — Política de retención documentada: 7 diarios + 4
   semanales + 3 mensuales. Script de pruning.
5. **A5.5** — DR runbook: `docs/operations/disaster-recovery.md` con
   3 escenarios (BD caída, Redis caído, servicio caído).
6. **A5.6** — `pre-deploy-check.sh` ampliado: 12 checks (los 10
   actuales + verificar backup + verificar restore reciente).
7. **A5.7** — Smoke E2E post-restore: levantar la BD del backup,
   correr `bateria_e2e_demo.py`, debe pasar 50/51.
8. **A5.8** — Rotación de secretos documentada y probada: ejecutar
   `infra/scripts/generate-secrets.py`, reiniciar servicio, validar
   que los tokens emitidos antes son rechazados.

**Criterios de salida:**

- Backup diario automatizado y verificado.
- Restore probado en <10 min desde snapshot de 1 día.
- 3 escenarios de DR con runbook ejecutable.
- `pre-deploy-check.sh` 12/12 verde.

**Riesgos:** el restore puede tomar más tiempo del estimado. Si > 30
min, documentar y ajustar SLA.

---

### C3 — Observabilidad operativa (1 semana)

**Objetivo:** que un operador sepa qué pasa sin tener que SSH al
servidor.

**Tareas (10):**

1. **A7.1** — Levantar Prometheus + Grafana + Alertmanager vía
   `docker-compose.observability.yml` (nuevo).
2. **A7.2** — Dashboard "API Overview": latencia p50/p95/p99, status
   codes, RPS, errores 4xx/5xx por endpoint.
3. **A7.3** — Dashboard "Negocio": solicitudes/hora, OC pendientes,
   stock bajo-mínimo por bodega, emails en outbox.
4. **A7.4** — Dashboard "Infra": CPU/mem/disk por contenedor, pool
   Postgres en uso, Redis hit rate.
5. **A7.5** — Alertas (4 mínimas + 2 críticas):
   - `5xx_rate > 1% por 5min` → on-call
   - `outbox_pendientes > 100 por 10min` → on-call
   - `p95_latency > 1s por 5min` → warning
   - `disk_free < 10% por 1h` → warning
   - `postgres_connections > 80% pool` → warning
   - `redis_down > 30s` → critical
6. **A7.6** — Runbook por alerta: cada alerta tiene un `docs/operations/alerts/<nombre>.md`.
7. **A7.7** — Test de alerta: matar Redis local, verificar que la
   alerta llega al canal configurado en <2 min.
8. **A7.8** — Sentry team plan: configurar proyecto + alertas
   (errores nuevos, regresiones).
9. **A7.9** — Dashboards exportables como JSON en
   `infra/grafana/dashboards/`.
10. **A7.10** — `docs/operations/observability-runbook.md` con cómo
    responder a cada alerta.

**Criterios de salida:**

- 3 dashboards en Grafana con datos reales.
- 6 alertas probadas (al menos 1 simulada).
- 1 runbook por alerta.

**Riesgos:** las alertas pueden ser ruidosas al principio. Empezar
con umbrales generosos.

---

### C4 — Staging con datos de cliente piloto (1 semana)

**Objetivo:** validar el sistema en un ambiente separado con datos
realistas, antes de exponer a clientes reales.

**Tareas (7):**

1. **C4.1** — Levantar ambiente staging (Docker Compose separado,
   puertos 8001/5433/6380).
2. **C4.2** — Seed con `seed_load_test_data.py --size large`
   (10 bodegas, 200 productos, 1000 movimientos).
3. **C4.3** — Crear 3 usuarios de prueba por rol (admin,
   supervisor, operador origen, operador destino).
4. **C4.4** — Smoke E2E 51/51 contra staging.
5. **C4.5** — Carga sintética: `load_test.py --profile normal` (50
   RPS durante 5 min) sin errores > 1%.
6. **C4.6** — Cliente piloto: invitar a 1 cliente real (con NDA) a
   usar staging durante 3 días. Recolectar feedback.
7. **C4.7** — Informe de staging: `docs/operations/staging-2026-W30.md`
   con hallazgos y bugs encontrados.

**Criterios de salida:**

- Staging up durante 5 días consecutivos sin caídas.
- 1 cliente piloto completó su flujo de trabajo.
- Informe con 0 bugs críticos y < 5 bugs menores.

**Riesgos:** el cliente piloto puede encontrar flujos no pensados.
Documentar como deuda de fase 2.

---

### C5 — Go-live + hardening final (1 semana)

**Objetivo:** producción con clientes reales y SLA definido.

**Tareas (8):**

1. **A6.1** — Implementar refresh tokens (tabla + endpoint
   `/auth/refresh` + rotación). Backward-compat.
2. **A6.2** — Rate limit por usuario (no solo por IP) en
   `/auth/login` y `/auth/refresh` via `slowapi`.
3. **C5.3** — Habilitar HTTPS con certbot o similar (según cloud).
4. **C5.4** — Cabeceras de seguridad en Nginx (HSTS, X-Frame-Options,
   CSP). Verificar con `securityheaders.com`.
5. **C5.5** — Pen-test automatizado: OWASP ZAP contra staging,
   revisar reporte, cerrar vulnerabilidades altas.
6. **C5.6** — Despliegue de producción con `go_live_runbook.md`
   paso a paso. Backup pre-deploy verificado.
7. **C5.7** — Smoke E2E contra producción (con 1 bodega y 1 producto
   de prueba). 51/51.
8. **C5.8** — Tag `v1.0.0` + comunicado a stakeholders.

**Criterios de salida:**

- Producción con 1 cliente real activo.
- HTTPS + cabeceras de seguridad + rate limit funcional.
- Pen-test sin vulnerabilidades altas.
- SLA documentado (99.5% uptime target).

**Riesgos:** el primer deploy a producción es el de mayor riesgo.
Tener a 2 personas en línea durante las primeras 24h.

---

## 3. Calendario propuesto

| Semana | Fase | Foco |
|---|---|---|
| W1 (22-26 jul) | **C1** Higiene | mypy, fix tests, ADR-0007 |
| W2 (29 jul-2 ago) | **C2** Runbook | backup probado, DR |
| W3 (5-9 ago) | **C3** Observabilidad | Grafana + alertas |
| W4 (12-16 ago) | **C4** Staging | cliente piloto |
| W5 (19-23 ago) | **C5** Go-live | refresh tokens + HTTPS + pen-test |
| W6 (26-30 ago) | **C5** Go-live (cont.) | deploy + smoke + tag v1.0.0 |

**Buffer:** 1 semana de contingencia entre C5 y el anuncio público.

---

## 4. Recursos necesarios

| Recurso | Costo / Disponibilidad |
|---|---|
| 1 BE senior (tú) | 5-6 semanas tiempo completo |
| 0.5 FE para issues de UI en staging | 1-2 días en C4 |
| 0.25 DevOps para alertas + HTTPS | 2-3 días en C3 y C5 |
| 1 cliente piloto con NDA | comprometer en W3 |
| 1 VPS staging (mínimo 4GB RAM) | $20-30 USD/mes |
| 1 dominio + cert TLS | $15/año + certbot |

**Opcional** (acelera C3-C5):
- Cuenta Grafana Cloud free tier (10k series)
- Sentry team plan ($26/mes)
- Pen-test externo ($500-2000 USD)

---

## 5. Criterios de salida agregados (cierre total)

Cuando C1-C5 estén cerrados, el sistema cumple los **12 criterios de
aceptación de la propuesta original** (§20):

| # | Criterio | Cubierto por |
|---|---|---|
| 1 | Autenticación y autorización | ✅ RF-01..04 + A6 refresh tokens |
| 2 | Stock consistente | ✅ tests concurrent + isolation PG |
| 3 | Trazabilidad completa | ✅ audit + kardex |
| 4 | Transferencias E2E | ✅ vía solicitudes |
| 5 | Compras E2E | ✅ |
| 6 | Notificaciones tiempo real | ⚠️ polling (WebSockets = fase 2) |
| 7 | Auditoría habilitada | ✅ |
| 8 | Backups verificados | ✅ C2 |
| 9 | Monitoreo y alertas | ✅ C3 |
| 10 | CI/CD operativo | ✅ |
| 11 | Staging validado | ✅ C4 |
| 12 | Documentación completa | ✅ + 4 docs propuesta_ejecutables |

**Resultado:** 11/12 plenos + 1/12 parcial (notificaciones en tiempo
real diferidas a fase 2 con WebSockets).

---

## 6. Riesgos globales

1. **Una sola persona.** Si nano se ausenta 1+ semana, el calendario
   se corre. Mitigación: cada fase cierra con tag, fácil de retomar.
2. **Cliente piloto con feedback negativo.** Puede forzar re-trabajo
   de UI/UX en C5. Mitigación: 1 semana de buffer.
3. **Mypy Sprint 3 rompe código.** Los ~110 type hints pueden
   introducir bugs sutiles. Mitigación: PR + review + CI + 337 tests.
4. **Restore lento.** Si pg_restore > 30 min, no cumplimos RTO.
   Mitigación: probar antes en C2, ajustar estrategia si necesario.
5. **Alertas ruidosas.** Grafana puede tirar 100 alertas/día. Mitigación:
   thresholds altos al inicio, ajustar en sprint siguiente.

---

## 7. Decisiones a tomar antes de empezar

| Decisión | Opciones | Recomendación |
|---|---|---|
| ¿Staging en misma máquina o VPS aparte? | misma / aparte | **aparte** (C4) |
| ¿Grafana self-hosted o cloud? | self / cloud free | **cloud free** (C3) |
| ¿Cliente piloto único o varios? | 1 / varios | **1 primero** (C4) |
| ¿HTTPS con certbot o cloud LB? | certbot / LB | **según deploy**: LB en cloud, certbot en VPS |
| ¿Pen-test interno o externo? | interno / externo | **interno** (C5) |

---

## 8. Hand-off al equipo

Cuando el roadmap esté en ejecución, cada cierre de fase debe
producir:

1. Commit con tag (`v1.0.0-rc1`, `v1.0.0-rc2`, ...).
2. Entrada en `docs/HANDOFF_SESION_<fecha>.md` con resumen de la
   fase.
3. Actualización de este roadmap con checkmarks ✅.
4. Comunicado a stakeholders si la fase toca features de usuario.

---

## 9. Referencias

- `docs/INFORME_FINAL_10_FASES.md` — cierre del roadmap previo
- `docs/HANDOFF_SESION_2026-07-15.md` — handoff de la última sesión
- `docs/go_live_runbook.md` + `docs/go_live_testing_runbook.md` —
  runbooks de deploy y testing
- `docs/operations/runbook.md` — runbook de operaciones (21KB)
- `docs/plan_mypy.md` — Sprints 1-5 de reducción mypy
- `docs/propuesta_ejecutables/01..04_*.md` — los 4 docs ejecutivos
- `docs/roadmap-hardening-pre-produccion.md` — Fase 0 ya cerrada
- `docs/fases/fase-10-hardening-produccion.md` — última fase
  ejecutada

---

**Próximo paso:** abrir branch `sprint/c1-higiene` y empezar por la
tarea **A1** (fix warehouses 409, 2 horas, alto ROI).
