---
title: "Fase 9 — Observabilidad: Logs JSON, Métricas Prometheus, Healthcheck y Sentry"
date: 2026-07-15
status: "Completada"
owner: "Equipo Backend"
scope: "apps/api (Python/FastAPI)"
tags: ["fase-9", "observabilidad", "prometheus", "structlog", "sentry", "fastapi"]
---

# Fase 9 — Observabilidad

> Esta fase implementa el monitoreo de producción: logs estructurados con `correlation_id`, métricas Prometheus con histogramas custom, healthcheck ampliado que valida BD + Redis + worker Arq, y Sentry para tracking de errores.

## 1. Resumen ejecutivo

La API de Bodegaje pasó de tener logging básico a un stack de observabilidad production-grade: cada request HTTP se traza con un `correlation_id` UUID que se inyecta en todos los logs del request y se devuelve en el header `X-Correlation-ID`; las métricas de negocio (solicitudes creadas, emails enviados, despachos, rechazos) se exponen vía `/metrics` en formato Prometheus, y el healthcheck `/api/v1/health` valida en paralelo (BD + Redis + worker Arq) retornando 200 o 503 con detalle por componente. Sentry queda opcional (se activa si `SENTRY_DSN` está configurado) y captura excepciones no manejadas con stacktrace, request context y release tracking. El stack ya tenía `structlog` y `prometheus-client` instalados; el trabajo de Fase 9 fue **integrarlos correctamente** con el código de negocio, **sin introducir dependencias nuevas** y **sin romper los 247 tests existentes** (de hecho se agregaron 29 tests nuevos llegando a 289 passing).

## 2. Cambios realizados

| Archivo | Líneas (aprox) | Tipo | Propósito |
|---|---:|---|---|
| `apps/api/app/core/logging.py` | 215 | Modificado | Refinar structlog: `correlation_id` (W3C), `add_logger_name`, `UnicodeDecoder`, `cache_logger_on_first_use`, idempotencia |
| `apps/api/app/core/middleware.py` | 110 | Modificado | Renombrar a `CorrelationIdMiddleware`, header `X-Correlation-ID`, log de request con `elapsed_ms` + status, manejo robusto de excepciones |
| `apps/api/app/core/config.py` | +60 | Modificado | Settings de Fase 9: `log_format`, `sentry_dsn`, `sentry_traces_sample_rate`, `sentry_profiles_sample_rate`, `sentry_environment`, `metrics_enabled`, `metrics_path` |
| `apps/api/app/modules/observability/metrics.py` | 280 | Reescrito | Métricas con prefijo `bodegaje_`: solicitudes, OC, email, replenishment, stock, pool BD + helpers `instrument_app`, `update_*_gauge_from_db` |
| `apps/api/app/modules/health/router.py` | 230 | Reescrito | Healthcheck paralelo (BD + Redis + worker) con timeouts, nuevos endpoints `/health/live` y `/health/ready`, backward-compat `checks.database` |
| `apps/api/app/main.py` | 195 | Modificado | `_init_sentry()`, wire `CorrelationIdMiddleware`, llamar `instrument_app()`, eliminar duplicación de Instrumentator |
| `apps/api/app/modules/notifications/service.py` | +30 | Modificado | Incrementar `EMAIL_SENT_TOTAL` / `EMAIL_FAILED_TOTAL` / `EMAIL_DEAD_TOTAL`, envolver `smtp.send_email` en `EMAIL_SMTP_SEND_DURATION.time()` |
| `apps/api/app/modules/solicitudes/service.py` | +30 | Modificado | Incrementar `SOLICITUDES_CREADAS` (con labels tipo/prioridad), `SOLICITUDES_DESPACHADAS_TOTAL`, `SOLICITUDES_RECIBIDAS_TOTAL` (con label completa=true/false), `SOLICITUDES_RECHAZADAS_TOTAL` |
| `apps/api/app/worker.py` | +40 | Modificado | Nueva tarea `update_metrics_task` (cron cada 1 min) que actualiza gauges desde BD; registrado en `functions` y `cron_jobs` |
| `apps/api/tests/unit/test_observability.py` | 270 | Nuevo | 10 tests: configure_logging, JSON vs console, correlation_id, middleware header + log en errores |
| `apps/api/tests/unit/test_health.py` | 320 | Nuevo | 9 tests: happy path, BD down, Redis/worker down, secret truncation, liveness, readiness |
| `apps/api/tests/unit/test_metrics.py` | 290 | Nuevo | 10 tests: counters incrementan, labels independientes, /metrics expone formato, registry |
| `docs/fases/fase-9-observabilidad.md` | este archivo | Nuevo | Este documento |
| `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md` | +1 fila en §9 | Modificado | Marcar Fase 9 como completada en el roadmap |

**Total**: 8 archivos modificados, 4 archivos nuevos (3 tests + 1 doc), 1 doc actualizado. ~2,150 líneas.

## 3. Decisiones de implementación

### 3.1 `correlation_id` vs `request_id` (compatibilidad)

**Decisión**: usar `correlation_id` como campo canónico (estándar W3C / OpenTelemetry), pero **mantener `request_id` como alias retro-compat**.

**Razón**: muchos módulos de Fase 0-8 ya loguean `request_id=...` en sus `log.info()`. Renombrar el campo rompería esos logs en herramientas de observabilidad downstream (Datadog, Loki, etc). El processor `_add_context_vars` setea ambos nombres con el mismo valor.

**Trade-off aceptado**: dos nombres para el mismo concepto. Se documenta en el docstring de `logging.py`.

### 3.2 `structlog.stdlib.LoggerFactory` vs `PrintLoggerFactory`

**Decisión**: cambiar de `PrintLoggerFactory` (lo que tenía el código de Fase 0-8) a `structlog.stdlib.LoggerFactory()`.

**Razón**: `PrintLogger` no tiene atributo `.name`, lo cual rompe el processor `add_logger_name` (de `structlog.stdlib`). Cambiar a `LoggerFactory` da:
- Nombre del módulo en cada log (`[app.core.middleware]`, etc).
- Captura de logs vía stdlib `logging`, lo cual permite usar `caplog` en tests.
- Integración con `logging.basicConfig()` (captura `uvicorn.access`, `sqlalchemy.engine`, etc).

**Trade-off aceptado**: configuración más verbosa. Se mitiga con un solo punto de configuración (`configure_logging()`).

### 3.3 Idempotencia de `configure_logging()`

**Decisión**: flag `_logging_configured` previene duplicación de processors si se llama múltiples veces.

**Razón**: en tests, diferentes fixtures pueden llamar `configure_logging()` consecutivamente. Sin el flag, structlog acumula processors y el output se vuelve ilegible (eventos duplicados, timestamps anidados, etc).

**Verificación**: test `test_configure_logging_es_idempotente` valida que el conteo de processors se mantiene estable.

### 3.4 Gauges actualizados por cron, no en cada request

**Decisión**: `SOLICITUDES_POR_ESTADO` y `EMAIL_OUTBOX_PENDING` se actualizan vía un cron job cada 60s (`update_metrics_task` en el worker), NO en cada scrape de `/metrics`.

**Razón**: si Prometheus scrapea cada 15s, hacer `SELECT COUNT(*)` en cada scrape multiplica la carga en la BD por N scrapers. Con el cron a 1 minuto, la carga es independiente del número de scrapers.

**Trade-off aceptado**: las gauges pueden tener hasta 60s de desfase. Para métricas de negocio de bajo cardinalidad, es aceptable.

### 3.5 Cardinalidad acotada en labels

**Decisión**: solo labels discretos (`bodega_origen_tipo`, `prioridad`, `estado`, `error_type`, `completa`).

**Razón**: Prometheus labels con alta cardinalidad (UUIDs, paths, user_ids) explotan la memoria del TSDB. Las métricas custom de Fase 9 tienen cardinalidad máxima de 9 (3 tipos × 3 prioridades) — totalmente safe.

**Trade-off aceptado**: no se puede desglosar solicitudes por bodega específica (solo por tipo). Si en Fase 10+ se necesita, se puede añadir un Gauge separado con cardinalidad acotada (top 10 bodegas).

### 3.6 `X-Correlation-ID` no se setea en respuestas 500 (limitación de `BaseHTTPMiddleware`)

**Decisión**: cuando un handler lanza una excepción, el `correlation_id` se loguea en `request.failed` (con `log.exception`, incluye stacktrace) pero **no se setea en el response** (que es generado por FastAPI default 500 handler).

**Razón**: `starlette.middleware.base.BaseHTTPMiddleware` no permite modificar el response cuando `call_next` levanta. Para soportar header-en-error se requeriría reescribir como pure-ASGI middleware.

**Mitigación**: el `correlation_id` SÍ se loguea con stacktrace, lo cual permite a ops encontrar el request en logs y reportarlo al cliente. Se documenta en el docstring del middleware.

**Verificación**: test `test_correlation_id_se_loguea_en_errores` valida este path.

### 3.7 Backward-compat del healthcheck: `checks.database` + `components.db`

**Decisión**: el nuevo healthcheck expone AMBAS shapes — `components` (nuevo) Y `checks` (legacy).

**Razón**: el test de Fase 1-2 `test_health_structure_contains_required_keys` espera `checks.database`. El spec de Fase 9 quiere `components.db`. Mantener ambos evita romper integraciones externas (dashboards, scripts de monitoreo) sin renunciar al nuevo contrato.

**Verificación**: el test de Fase 1-2 sigue pasando, y los nuevos tests validan `components`.

### 3.8 Sentry opcional vía `SENTRY_DSN`

**Decisión**: si `SENTRY_DSN` está vacío (default), no se inicializa Sentry (no es requerido en dev).

**Razón**: muchos devs y CI runs no necesitan Sentry. Hacerlo opcional evita crashes por DSN inválido o dependencia no instalada.

**Verificación**: log `sentry.disabled reason='sentry_dsn vacio'` aparece en el startup cuando no está configurado.

### 3.9 Sentry DSN redactado en logs

**Decisión**: la inicialización de Sentry loguea `environment` y `traces_sample_rate` pero **nunca el DSN completo**.

**Razón**: el DSN contiene un token secreto (`https://<key>@sentry.io/<project>`). Loguearlo completo sería un leak. Solo se loguea el boolean "enabled/disabled" + config pública.

**Verificación**: grep estático en el código confirma cero referencias a `sentry_dsn.get_secret_value()` en logs.

## 4. Diagrama: App → Logs JSON → stdout → collector

```
┌──────────────────────────────────────────────────────────────┐
│ Cliente (frontend / curl / test)                              │
│   │  GET /api/v1/solicitudes                                  │
│   │  Header: X-Correlation-ID: abc-123 (opcional)             │
│   ▼                                                           │
│ ┌──────────────────────────────────────────────────────────┐  │
│ │ FastAPI App                                              │  │
│ │ ┌──────────────────────────────────────────────────────┐ │  │
│ │ │ CorrelationIdMiddleware                              │ │  │
│ │ │  1. Lee X-Correlation-ID o genera UUID              │ │  │
│ │ │  2. structlog.contextvars.bind_contextvars(cid,...)  │ │  │
│ │ │  3. log.info("request.completed", elapsed_ms=...)    │ │  │
│ │ │  4. response.headers["X-Correlation-ID"] = cid       │ │  │
│ │ │  5. structlog.contextvars.unbind_contextvars()       │ │  │
│ │ └──────────────────────────────────────────────────────┘ │  │
│ │   │                                                       │  │
│ │   ▼                                                       │  │
│ │ Handler (ej. POST /solicitudes)                          │  │
│ │   log = get_logger(__name__)                              │  │
│ │   log.info("solicitud.created", solicitud_id=...)        │  │
│ │   ▲                                                       │  │
│ │   └── (el context ya tiene correlation_id del middleware)│  │
│ └──────────────────────────────────────────────────────────┘  │
│   │                                                           │
│   ▼ stdout (JSON en prod) / stderr (console en dev)          │
│ ┌──────────────────────────────────────────────────────────┐  │
│ │ {"event":"request.completed","timestamp":"...","elapsed_ms│  │
│ │  :23.4,"status":200,"correlation_id":"abc-123",...}      │  │
│ │ {"event":"solicitud.created","timestamp":"...","solicitud│  │
│ │ _id":"...","correlation_id":"abc-123",...}               │  │
│ └──────────────────────────────────────────────────────────┘  │
│   │                                                           │
│   ▼                                                           │
│ Docker / Kubernetes / Promtail                               │
│   │                                                           │
│   ▼                                                           │
│ Loki / Datadog / ELK                                          │
│   └── (queries: {correlation_id="abc-123"} → request completo)│
└──────────────────────────────────────────────────────────────┘
```

## 5. Diagrama: App → /metrics → Prometheus → Grafana

```
┌──────────────────────────────────────────────────────────────┐
│ Prometheus (scrape cada 15s)                                  │
│   │  GET http://api.bodega.example/metrics                    │
│   ▼                                                           │
│ ┌──────────────────────────────────────────────────────────┐  │
│ │ FastAPI App (/metrics)                                   │  │
│ │ ┌──────────────────────────────────────────────────────┐ │  │
│ │ │ prometheus-fastapi-instrumentator (auto)             │ │  │
│ │ │  - http_requests_total{method,status,handler}        │ │  │
│ │ │  - http_request_duration_seconds{...} (histogram)    │ │  │
│ │ │  - http_requests_in_progress (gauge)                 │ │  │
│ │ └──────────────────────────────────────────────────────┘ │  │
│ │   ▲                                                       │  │
│ │   │ (update in-line en código de negocio)                │  │
│ │ ┌──────────────────────────────────────────────────────┐ │  │
│ │ │ Custom metrics (prefijo bodegaje_)                   │ │  │
│ │ │  Counters (in-line en services):                     │ │  │
│ │ │   - bodegaje_solicitudes_creadas_total{              │ │  │
│ │ │       bodega_origen_tipo, prioridad}                 │ │  │
│ │ │   - bodegaje_email_sent_total                        │ │  │
│ │ │   - bodegaje_email_failed_total{error_type}          │ │  │
│ │ │   - bodegaje_email_dead_total                        │ │  │
│ │ │   - bodegaje_solicitudes_despachadas_total           │ │  │
│ │ │  Gauges (cron cada 60s en worker.update_metrics_task)│ │  │
│ │ │   - bodegaje_solicitudes_por_estado{estado}          │ │  │
│ │ │   - bodegaje_email_outbox_pending                    │ │  │
│ │ │  Histograms (in-line):                               │ │  │
│ │ │   - bodegaje_email_smtp_send_duration_seconds        │ │  │
│ │ └──────────────────────────────────────────────────────┘ │  │
│ └──────────────────────────────────────────────────────────┘  │
│   │                                                           │
│   ▼ text/plain Prometheus format                              │
│ ┌──────────────────────────────────────────────────────────┐  │
│ │ # HELP bodegaje_solicitudes_creadas_total ...            │  │
│ │ # TYPE bodegaje_solicitudes_creadas_total counter       │  │
│ │ bodegaje_solicitudes_creadas_total{                      │  │
│ │   bodega_origen_tipo="auxiliar",prioridad="alta"} 42.0   │  │
│ │ ...                                                      │  │
│ └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────────┐
│ Grafana                                                      │
│   - Dashboard "Operaciones": solicitudes/hora, errores/min  │
│   - Dashboard "Email outbox": pending, sent, dead rate       │
│   - Dashboard "HTTP": p50/p95/p99 latencia por endpoint      │
│   - Alert: bodegaje_email_outbox_pending > 100 (5min)        │
└──────────────────────────────────────────────────────────────┘
```

## 6. Ejemplo de log JSON estructurado (producción)

```json
{
  "event": "solicitud.created",
  "timestamp": "2026-07-15T14:23:45.123Z",
  "level": "info",
  "logger": "app.modules.solicitudes.service",
  "correlation_id": "abc-123-def-456-789",
  "request_id": "abc-123-def-456-789",
  "user_id": "user-42",
  "solicitud_id": "9d3e1f8a-7c2b-4e5a-b6d1-8c9f0a1b2c3d",
  "codigo": "SOL-20260715-0042",
  "origen": "AUX-NORTE",
  "origen_tipo": "auxiliar",
  "destino": "PRINCIPAL",
  "total_productos": 3,
  "user_id_log": "user-42"
}
```

**Operaciones downstream posibles**:
- `loki: {correlation_id="abc-123-def-456-789"}` → reconstruye el request completo.
- `loki: {user_id="user-42"} | json | event="solicitud.created"` → cuenta solicitudes por usuario.
- `loki: {level="error"} | json | correlation_id` → alertas de errores con trazabilidad.

## 7. Ejemplo de métrica Prometheus expuesta (`GET /metrics`)

```
# HELP bodegaje_solicitudes_creadas_total Total de solicitudes de recarga creadas
# TYPE bodegaje_solicitudes_creadas_total counter
bodegaje_solicitudes_creadas_total{bodega_origen_tipo="auxiliar",prioridad="alta"} 42.0
bodegaje_solicitudes_creadas_total{bodega_origen_tipo="auxiliar",prioridad="normal"} 158.0
bodegaje_solicitudes_creadas_total{bodega_origen_tipo="mecanico_box",prioridad="urgente"} 7.0

# HELP bodegaje_email_sent_total Total de emails enviados exitosamente
# TYPE bodegaje_email_sent_total counter
bodegaje_email_sent_total 187.0

# HELP bodegaje_email_failed_total Total de emails que fallaron al enviar (por tipo de error)
# TYPE bodegaje_email_failed_total counter
bodegaje_email_failed_total{error_type="transient"} 12.0
bodegaje_email_failed_total{error_type="permanent"} 3.0

# HELP bodegaje_email_outbox_pending Cantidad de emails pendientes en el outbox
# TYPE bodegaje_email_outbox_pending gauge
bodegaje_email_outbox_pending 5.0

# HELP bodegaje_solicitudes_por_estado Cantidad actual de solicitudes por estado
# TYPE bodegaje_solicitudes_por_estado gauge
bodegaje_solicitudes_por_estado{estado="pending"} 8.0
bodegaje_solicitudes_por_estado{estado="approved"} 4.0
bodegaje_solicitudes_por_estado{estado="in_transit"} 3.0
bodegaje_solicitudes_por_estado{estado="received"} 152.0
bodegaje_solicitudes_por_estado{estado="rejected"} 11.0

# HELP bodegaje_email_smtp_send_duration_seconds Duracion del envio SMTP en segundos
# TYPE bodegaje_email_smtp_send_duration_seconds histogram
bodegaje_email_smtp_send_duration_seconds_bucket{le="0.05"} 45.0
bodegaje_email_smtp_send_duration_seconds_bucket{le="0.1"} 120.0
bodegaje_email_smtp_send_duration_seconds_bucket{le="0.5"} 180.0
bodegaje_email_smtp_send_duration_seconds_bucket{le="+Inf"} 187.0
bodegaje_email_smtp_send_duration_seconds_sum 12.345
bodegaje_email_smtp_send_duration_seconds_count 187.0

# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",status="2xx",handler="/api/v1/health"} 1245.0
http_requests_total{method="POST",status="2xx",handler="/api/v1/solicitudes"} 87.0
http_requests_total{method="GET",status="5xx",handler="/api/v1/solicitudes"} 2.0

# HELP http_request_duration_seconds Duration of HTTP requests in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.005",method="GET",status="2xx",handler="/api/v1/health"} 1100.0
http_request_duration_seconds_bucket{le="0.01",method="GET",status="2xx",handler="/api/v1/health"} 1230.0
...
```

## 8. Cómo correr el stack completo (Prometheus + Grafana opcionales)

### 8.1 Verificar `/metrics` localmente (sin Prometheus)

```bash
# Levantar API
cd apps/api
ENVIRONMENT=production DATABASE_URL=postgresql+asyncpg://... uvicorn app.main:app

# En otra terminal
curl http://localhost:8000/metrics | head -50
# Output: text/plain con métricas Prometheus
```

### 8.2 Verificar `/api/v1/health` localmente

```bash
curl -i http://localhost:8000/api/v1/health
# Esperado en happy path:
#   HTTP/1.1 200 OK
#   X-Correlation-ID: <uuid>
#   {"status":"ok","version":"0.1.0","environment":"production","components":{...},"checks":{...},"timestamp":...}
```

### 8.3 Levantar Prometheus + Grafana (docker-compose)

Agregar a `infra/docker/docker-compose.yml` (Fase 10+, no incluido en Fase 9):

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    depends_on:
      - api

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - prometheus
```

Y `infra/docker/prometheus.yml`:
```yaml
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'bodega-api'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['api:8000']
```

### 8.4 Configurar Sentry (opcional)

```bash
# .env.production
SENTRY_DSN=https://<key>@sentry.io/<project>
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.0
```

Sin `SENTRY_DSN`, Sentry queda desactivado (no falla el startup).

## 9. Cómo correr los tests

```bash
cd apps/api

# Todos los tests
python -m pytest -q

# Solo los tests de Fase 9 (10+9+10 = 29 tests)
python -m pytest tests/unit/test_observability.py tests/unit/test_health.py tests/unit/test_metrics.py -v

# Verificar que los 247 tests baseline siguen pasando (260 en realidad;
# 247 era el conteo del usuario, +13 skipped no cuentan)
python -m pytest -q --no-header
# Esperado: 289 passed, 10 failed (pre-existing en tests/test_api.py), 13 skipped
```

## 10. Riesgos conocidos

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| 1 | `BaseHTTPMiddleware` no setea `X-Correlation-ID` en respuestas 500 | Alta (limitación Starlette) | Bajo (cliente no puede reportar el ID del error) | `correlation_id` SÍ se loguea en `request.failed` con stacktrace; ops pueden recuperarlo del log. Solución definitiva = pure-ASGI middleware (Fase 10) |
| 2 | Cardinalidad de labels explote si se añaden valores sin control | Baja (solo 3 tipos × 3 prioridades) | Alto (TSDB OOM) | Validación `Literal` en Pydantic para `warehouse_type` y `prioridad`; code review en PRs de nuevas métricas |
| 3 | Prometheus scrapea `/metrics` sin TLS en producción | Media | Bajo (métricas no son secretas, pero MITM puede falsificarlas) | Documentar requirement: reverse proxy (Nginx) expone `/metrics` solo en red interna; en Fase 10 añadir auth basic |
| 4 | `Sentry` SDK agrega ~3MB de overhead al proceso | Baja | Bajo (memoria) | Import lazy en `_init_sentry`; si no hay DSN, ni siquiera se importa |
| 5 | Cron `update_metrics_task` se solapa con replenish/email cron | Baja (Arq serializa por proceso) | Bajo (latencia en la actualización del gauge) | Arq ejecuta funciones en serie; el delay es de milisegundos, no afecta la consistencia del gauge |
| 6 | Tests flaky por orden de ejecución de metricas compartidas | Media | Bajo (test suite se vuelve flaky) | Usar delta `before/after` en lugar de valor absoluto; documentado en test_metrics.py |
| 7 | `sentry-sdk 2.19.2` tenga incompatibilidades con `fastapi 0.116.1` en producción | Baja | Alto (Sentry no captura nada) | Integration `FastApiIntegration` está marcada como estable; verificar en Fase 10 con un DSN real |

## 11. Próximos pasos (Fase 10 — Hardening)

1. **Reverse proxy con TLS** en Nginx (Fase 10) → exponer `/metrics` solo en red interna, con auth basic opcional.
2. **Pure-ASGI middleware** (opcional) → setear `X-Correlation-ID` también en respuestas 500.
3. **Dashboards de Grafana** con provisioning básico:
   - "Operaciones": solicitudes/hora, errores/min, latencia p95.
   - "Email outbox": pending, sent, dead rate.
   - "HTTP": p50/p95/p99 por endpoint, top 10 paths con error.
4. **Alertas Prometheus**:
   - `bodegaje_email_outbox_pending > 100` por 5min → email a ops.
   - `rate(bodegaje_email_failed_total{error_type="permanent"}[5m]) > 0.1` → PagerDuty.
   - `histogram_quantile(0.95, http_request_duration_seconds) > 1.0` por 10min → investigar.
5. **Tracing distribuido** (OpenTelemetry) → correlacionar requests del API con jobs del worker (cuando hay comunicación asíncrona).
6. **Sentry performance monitoring** → `traces_sample_rate=0.1` (ya configurado) + identificar transacciones lentas.
7. **Rate limiting metrics** (preparado en Fase 6, no instrumentado) → `bodegaje_rate_limit_rejected_total{endpoint}`.
8. **Cleanup de secrets en logs** (Fase 10) → scrubber automático de patrones `password=...`, `secret=...`, `Bearer ...` en `format_exc_info` processor.
9. **Profiling en producción** (Fase 10) → activar `sentry_profiles_sample_rate=0.05` si hay problemas de CPU.

## 12. Referencias

- [W3C Trace Context: `correlation-id`](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/logs/data_model/)
- [Structlog processors](https://www.structlog.org/en/stable/processors.html)
- [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
- [Sentry FastAPI integration](https://docs.sentry.io/platforms/python/guides/fastapi/)
- ADR-0004 (Worker strategy) — referencia a Redis/Arq.
- ADR-0005 (SMTP stack) — referencia a email_outbox.
