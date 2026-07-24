# Documento 4 — Plan de Desarrollo por Sprints

**Proyecto:** Sistema de Gestión de Inventario Multi-Bodega (`bodega`)
**Versión:** 1.0 — 2026-07-22
**Origen:** sección 22.1 (4) de `PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md`,
integrado con el estado real del proyecto (Fase 0–5 cerradas + migración
a Postgres).
**Horizonte:** Sprints S1–S6 cubren la salida a producción completa. S7–S10
son fase 2 según la propuesta original.

---

## 1. Propósito

Convertir la lista de brechas detectadas en los documentos 1, 2 y 3 en un
plan ejecutable por sprints de 1–2 semanas, con criterios de salida
objetivos y dependencias explícitas entre sprints. Es la guía que el equipo
sigue para decidir qué se hace primero y qué se difiere.

---

## 2. Contexto: qué ya está hecho

| Fase | Resultado | Documento de soporte |
|---|---|---|
| 0 | Higiene de secretos, gitleaks en CI | `docs/roadmap-hardening-pre-produccion.md` |
| 1 | Backend conectado a Postgres real | `docs/fases/fase-1-postgres-real.md` |
| 2 | Multibodega física (ubicaciones + stock real) | `docs/fases/fase-2-multibodega-fisica.md` |
| 3 | Solicitudes N-productos (reemplazo de transfers) | `docs/fases/fase-3-solicitudes-n-productos.md` |
| 4 | Replenishment automático | `docs/fases/fase-4-replenishment-automatico.md` |
| 5 | Recepción con escaneo de códigos | `docs/fases/fase-5-recepcion-escaneo.md` |
| 6 | UI de OC | `docs/fases/fase-6-ordenes-compra-ui.md` |
| 7 | SMTP async + Arq worker | `docs/fases/fase-7-smtp-async.md` |
| 8 | Vistas nuevas con Tailwind | `docs/fases/fase-8-vistas-tailwind.md` |
| 9 | Observabilidad (metrics + structlog + health) | `docs/fases/fase-9-observabilidad.md` |
| 10 | Hardening de producción | `docs/fases/fase-10-hardening-produccion.md` |

**Resultado neto al cierre de Fase 10:**

- 19 módulos backend funcionando
- 5 jobs de CI en verde
- 337 tests unitarios + 63 integration + batería E2E 50/51
- Migración completa a Postgres (con `sqlite_legacy` eliminado)

---

## 3. Brechas hacia "producción completa"

De los documentos 1, 2 y 3 sale esta lista priorizada. Se ordenan por
**impacto de producción** × **esfuerzo**.

| # | Brecha | Impacto | Esfuerzo | Sprint propuesto |
|---|---|---|---|---|
| B-01 | `warehouses.reject_duplicate_name` falla (test) | Bajo | XS | S1 |
| B-02 | `reservas_stock` formal (sustituye atomic-only) | Alto | M | S2 |
| B-03 | WebSockets + `outbox_eventos` para tiempo real | Alto | L | S3 |
| B-04 | Clasificación ABC + ranking de rotación | Medio | M | S4 |
| B-05 | Slotting avanzado (zonas/racks/niveles) | Bajo | L | S5 |
| B-06 | Refresh tokens + rate limit | Alto | M | S1 |
| B-07 | Política de backup Postgres documentada y probada | Alto | S | S1 |
| B-08 | Dashboards Grafana + Alertmanager | Medio | M | S6 |
| B-09 | Renovar ADR-0007 PBKDF2 vs Argon2 | Bajo | XS | S1 |
| B-10 | mypy → 0 errores (Sprints 2-5 del `plan_mypy.md`) | Bajo | M | S1–S3 |
| B-11 | Chat operacional por bodega | Bajo | XL | S7+ (fase 2) |
| B-12 | Integración ERP / WhatsApp | Bajo | XL | S8+ (fase 2) |
| B-13 | Lotes, series y vencimientos | Bajo | L | S9+ (fase 2) |
| B-14 | Pronóstico de demanda | Bajo | XL | S10+ (fase 2) |

**Leyenda esfuerzo:** XS = horas, S = 1-2 días, M = 1 sprint, L = 2-3 sprints, XL = > 3 sprints.

---

## 4. Sprints S1–S6 (producción completa)

Cada sprint tiene: **objetivo, entregables, criterios de salida, dependencias
y riesgos**.

### S1 — Higiene técnica rápida (1 semana)

**Objetivo:** cerrar la deuda menor acumulada durante la migración a
Postgres, sin introducir cambios funcionales grandes.

**Entregables:**

- B-01: fix de validación 409 en `warehouses/router.py` + test verde.
- B-06a: agregar `refresh_tokens` tabla + endpoint `/auth/refresh` con
  rotación (RFC 6749). Backward-compat: si el cliente no envía refresh,
  se sigue aceptando el access token hasta su expiración.
- B-06b: rate limit por IP/usuario via `slowapi` en `/auth/login` y
  `/auth/refresh` (10/min por IP, 5/min por username).
- B-07: `docs/operations/backup-restore-runbook.md` con script
  `pg_dump` diario + restore probado. Cron configurado.
- B-09: ADR-0007 PBKDF2 vs Argon2 publicado.
- B-10 Sprint 1: anotar `auth/repository.py`, `modules/ordenes_compra/*`,
  reducir ~20 errores mypy.

**Criterios de salida:**

- CI verde con los 5 jobs.
- `pytest -k test_warehouses` 100% verde.
- `pytest tests/integration/test_auth.py` cubre refresh + rate limit.
- Backup runbook ejecutable end-to-end en local.

**Riesgos:** el rate limit puede romper la batería E2E si se ejecuta
rápido → ajustar límites durante los tests con `RATE_LIMIT_DISABLED=1`.

---

### S2 — Reservas de stock (1.5 semanas)

**Objetivo:** introducir `reservas_stock` para que múltiples solicitudes
sobre el mismo producto no se pisen, manteniendo la atomicidad de
Postgres como respaldo.

**Entregables:**

- B-02: tabla `stock_reservas(id, id_solicitud, id_producto, id_bodega,
  cantidad, created_at, expires_at)` con FK CASCADE a `solicitudes_recarga`.
- Endpoint `POST /solicitudes` valida `cantidad_disponible = quantity -
  sum(reservas_activas) >= solicitada` antes de crear la solicitud.
- Al recibir la solicitud, las reservas se cierran (`status='consumed'`)
  o se cancelan si se rechaza.
- Migración `0010_stock_reservas.sql` (Postgres) + mirror SQLite.
- Tests de concurrencia que validan el invariante.

**Criterios de salida:**

- `tests/integration/test_concurrent_reservas.py` verde con 50 workers
  compitiendo por 100 unidades → nunca se sobreasigna.
- Batería E2E 51/51.
- mypy: -10 errores adicionales.

**Dependencias:** S1 cerrado.

**Riesgos:** reservas huérfanas si una solicitud queda en estado
indefinido → cron de limpieza cada 6h que cancela reservas con
`expires_at < now()`.

---

### S3 — Tiempo real con WebSockets + outbox de eventos (2 semanas)

**Objetivo:** la UI recibe actualizaciones sin polling. Sigue el patrón
Outbox de la sección 11 de la propuesta.

**Entregables:**

- B-03: tabla `outbox_eventos(id, aggregate_type, aggregate_id,
  event_type, payload, created_at, published_at)` con índice
  `(published_at, created_at)`.
- Worker (Arq) que cada 1s lee eventos con `published_at IS NULL`, los
  publica a Redis Pub/Sub y marca `published_at`.
- Endpoint WS `/ws/notifications?token=...` suscribe al cliente al canal
  `user:{user_id}`. Heartbeat cada 30s.
- Frontend: hook `useWebSocket()` reconecta con backoff exponencial.
- Reemplaza el polling de 30s en la página de notificaciones.

**Criterios de salida:**

- Latencia end-to-end evento → UI < 2s en condiciones normales.
- Test de integración: WS recibe evento publicado por una request HTTP
  distinta.
- mypy: -20 errores.

**Dependencias:** S2 cerrado.

**Riesgos:** WS detrás de Nginx requiere `Upgrade` y `Connection` headers
configurados. Cuidar que el `proxy_read_timeout` no corte conexiones
inactivas (default 60s, ajustar a 3600s).

---

### S4 — Clasificación ABC y ranking de ventas (1.5 semanas)

**Objetivo:** generar insumos para slotting y reabastecimiento. Una
vistas materializadas se refresca diariamente.

**Entregables:**

- B-04: tabla `ventas_producto_diaria(id_producto, fecha, unidades,
  monto)` poblada por job diario.
- Vista materializada `ranking_productos_periodo(periodo, rank_unidades,
  rank_monto)`.
- Vista materializada `clasificacion_abc_producto(id_producto, clase_a_b_c,
  periodo_fin)`.
- Job Arq `calcular_abc_job` corre a las 02:00; refresh las VMs.
- Endpoints `GET /reports/abc?periodo=2026-Q3`,
  `GET /reports/ranking?top=20&periodo=...`.

**Criterios de salida:**

- Tres meses de datos seed: ABC se calcula estable.
- `tests/integration/test_reports.py` valida que la suma de A+B+C cubre
  100% de las ventas.

**Dependencias:** S1 cerrado.

**Riesgos:** el primer cálculo de ABC sobre datos seed sintéticos puede
ser sesgado → usar solo para validar el motor, no para producción.

---

### S5 — Slotting avanzado (2 semanas)

**Objetivo:** modelo físico fino de la bodega (zona, rack, nivel,
posición), con recomendaciones automáticas de reubicación.

**Entregables:**

- B-05: tablas `warehouse_zonas`, `warehouse_racks`, `warehouse_niveles`,
  `warehouse_posiciones` con jerarquía estricta.
- Tabla `product_slotting(id_producto, id_posicion, es_primaria, slotting_score)`.
- Tabla `slotting_sugerencias(id_producto, id_posicion_sugerida, score,
  motivo, created_at)`.
- Job diario que genera sugerencias usando clasificación ABC + frecuencia
  de picking (si está disponible).
- Endpoint `POST /ubicaciones/{id}/asignar-producto` con validación
  (capacidad, incompatibilidad, criticidad).

**Criterios de salida:**

- Batería E2E incluye escenario "re-slotting de 20 productos".
- Sin sobreasignación: cada `product_slotting` con `es_primaria=true` es
  único por producto.
- Migración reversible: `downgrade()` borra todo el slotting sin
  afectar a `stock_levels`.

**Dependencias:** S4 cerrado (necesita clasificación ABC para puntuar).

**Riesgos:** el modelo de 4 niveles de jerarquía es complejo de migrar
desde el modelo actual de 3 (pasillo/estantería/altura) → planificar
migración con periodo de coexistencia.

---

### S6 — Observabilidad operativa (1.5 semanas)

**Objetivo:** dashboards y alertas que permiten a operaciones dormir
tranquilo.

**Entregables:**

- B-08: docker-compose con Prometheus + Grafana + Alertmanager.
- Dashboards: API latency, error rate, eventos outbox pendientes, OC
  pendientes de aprobación, productos bajo-mínimo, uso de pool Postgres.
- Alertas:
  - 5xx > 1% en 5 min → Slack/PagerDuty.
  - outbox pendientes > 100 en 10 min → on-call.
  - Postgres connections > 80% del pool → warning.
  - Disco < 10% libre en 1h → warning.
- `docs/operations/observability-runbook.md` con cómo responder a cada
  alerta.

**Criterios de salida:**

- Cada alerta tiene un runbook enlazado.
- Dashboard importable vía JSON en `infra/grafana/dashboards/`.
- Simulación de incidente: matar Redis, ver alerta, ver runbook, restaurar.

**Dependencias:** ninguna (independiente).

**Riesgos:** las alertas pueden ser ruidosas al principio → empezar con
umbrales generosos e ir ajustando con datos reales.

---

## 5. Diagrama de dependencias entre sprints

```
S1 ──┬──► S2 ──► S3
     │              │
     ├──► S4 ───────┼──► S5
     │              │
     └──► S6 (independiente)
```

- **S1** es prerequisito de S2, S3, S4, S5.
- **S2** es prerequisito de S3.
- **S4** es prerequisito de S5.
- **S6** puede correr en paralelo con cualquiera.

---

## 6. Calendario tentativo

| Sprint | Semanas | Acumulado | Salida al final |
|---|---|---|---|
| S1 | 1 | 1 | Higiene + refresh tokens + rate limit + backup runbook |
| S2 | 1.5 | 2.5 | Reservas de stock operativas |
| S3 | 2 | 4.5 | WebSockets en producción, sin polling |
| S4 | 1.5 | 6 | ABC + ranking en reportes |
| S5 | 2 | 8 | Slotting + recomendaciones |
| S6 | 1.5 | 9.5 | Observabilidad completa, on-call listo |

**Total:** ~10 semanas para "producción completa" según la propuesta
(sección 16, que estimaba 10–14 semanas).

---

## 7. S7–S10: roadmap fase 2 (fase 2 según propuesta)

Estos sprints no son bloqueantes para go-live, pero se planifican para
después de S6. Resumen:

### S7 — Chat operacional

- Tablas `chat_canales`, `chat_mensajes`, `chat_adjuntos`.
- Endpoints `POST /chat/canales/{id}/mensajes` + WS `/ws/chat/canal/{id}`.
- Frontend: panel lateral en páginas de solicitud/OC/transferencia.
- Conversión mensaje → borrador de solicitud (template-based).

### S8 — Integraciones externas

- Webhook genérico de proveedor (entrada de OC por API).
- Integración con SII (DTE) si aplica al cliente.
- Adapter de WhatsApp via API oficial (Meta Cloud).
- Sincronización con ERP (SAP B1 / Odoo) según cliente.

### S9 — Lotes, series y vencimientos

- Tabla `product_lotes(id, id_producto, codigo_lote, fecha_vencimiento,
  cantidad_inicial)`.
- Movimientos referencian lote.
- Alertas de vencimiento T-30, T-7, T-1.

### S10 — Pronóstico de demanda

- Job diario que predice consumo por producto usando histórico.
- Tabla `demanda_predicha(id_producto, fecha, unidades_predichas,
  intervalo_confianza)`.
- Integración con `replenishment_rules` para ajustar `min_quantity`
  automáticamente.

---

## 8. Convenciones de los sprints

Cada sprint sigue este molde (heredado de
`docs/roadmap-hardening-pre-produccion.md`):

- **Objetivo** — qué entrega al final.
- **Pre-requisitos** — qué sprints/estados deben estar listos.
- **Tareas** — numeradas, idealmente con subagente `coder` asignado.
- **Criterios de salida** — qué se valida para cerrar.
- **Riesgos** — qué puede romperse.
- **Métricas de éxito** — cómo se mide en retrospectiva.

Reglas globales:

- **No commit directo a `main`**: PR por sprint.
- **CI debe pasar antes de pedir review**.
- **No avanzar al siguiente sin cerrar el actual**.
- **Batería E2E 51/51** es el smoke test mínimo de cualquier sprint.
- **Conventional Commits** en todos los mensajes.

---

## 9. Métricas de éxito agregadas (al cierre de S6)

| Métrica | Hoy | Meta S6 |
|---|---|---|
| Tests passing | 337 unit + 63 int + 50/51 E2E | 400 unit + 80 int + 51/51 E2E |
| Cobertura | ~77% | ≥ 80% |
| Latencia p95 (común) | < 200ms (medido E2E) | < 200ms |
| mypy errores | 214 | 0 (S1–S3) + 0 (S4–S6) |
| WebSockets conectados | 0 | ≥ 10 simultáneos en staging |
| Alertas en Grafana | 0 | 4 alertas operativas |
| Backups automatizados | 0 | 1 diario + 1 restore mensual |
| Sprints cerrados a tiempo | 5/5 (Fase 0–10) | 11/11 (S1–S6) |

---

## 10. Riesgos globales del plan

1. **Dependencia de un solo perfil técnico.** Hoy el equipo es
   efectivamente una persona (tú). Si la capacidad cae, S3 y S5 son los
   más sensibles.
2. **WebSockets añaden superficie operativa.** Nginx, proxies, balanceadores
   y CORS se vuelven más sensibles. S3 debe dedicar 30% a hardening
   operativo, no solo a la feature.
3. **ABC sobre datos sintéticos puede inducir a decisiones malas.** En S4,
   dejar claro que las recomendaciones de slotting no se aplican
   automáticamente hasta tener ≥3 meses de datos reales.
4. **Migración a Postgres aún joven.** El backup runbook (B-07) es el
   primer paso de operaciones. Antes de S3, asegurar que el restore
   funciona bajo presión.
5. **Deuda técnica no documentada en `mypy` y `gitleaks`.** Si S1 no
   cierra B-10, los sprints siguientes acumularán más errores.

---

## 11. Próximo paso concreto

Si se aprueba este plan, el **primer paso** es:

1. Crear branch `sprint/s1-higiene`.
2. Abrir issue con las tareas de S1 (B-01, B-06, B-07, B-09, B-10).
3. Asignar subagente `coder` para B-01 y B-09 (XS, alto ROI).
4. Mientras corre, hacer B-07 (backup runbook) a mano, ya que requiere
   probar en local.
5. PR + review + merge antes de empezar S2.

---

## 12. Anexo — estimación detallada por tarea

| Tarea | Horas estimadas | Quién |
|---|---|---|
| B-01 fix warehouses 409 | 2 | coder |
| B-06 refresh tokens + rate limit | 16 | coder |
| B-07 backup runbook | 8 | humano + coder |
| B-09 ADR-0007 | 1 | humano |
| B-10 mypy Sprint 1 | 8 | coder |
| B-02 reservas_stock | 24 | coder |
| B-03 WebSockets + outbox | 40 | coder |
| B-04 ABC + ranking | 24 | coder |
| B-05 slotting | 40 | coder |
| B-08 observabilidad dashboards | 24 | coder |
| **Total S1–S6** | **187 horas** | ≈ 4.7 semanas-hombre |

> Las horas son estimación de esfuerzo de desarrollo, no incluyen review,
> testing manual, ni overhead. Una persona a tiempo completo termina S1–S6
> en 9–10 semanas naturales (alineado con la sección 6).
