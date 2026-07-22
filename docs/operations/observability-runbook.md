# Runbook de Observabilidad (C3.10)

**Fecha:** 2026-07-22
**Stack:** Prometheus + Grafana + Alertmanager + node-exporter + postgres-exporter

---

## TL;DR

| Componente | URL | Credenciales |
|---|---|---|
| Prometheus | http://localhost:9090 | sin auth (dev) |
| Grafana | http://localhost:3000 | admin / admin (cambiar en prod) |
| Alertmanager | http://localhost:9093 | sin auth (dev) |
| API metrics | http://localhost:8000/metrics | sin auth |
| Mailpit (SMTP dev) | http://localhost:8025 | sin auth |

Levantar todo el stack:
```bash
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.observability.yml \
               up -d
```

---

## Dashboards (C3.2-3.4)

Hay 3 dashboards pre-instalados en Grafana (carpeta "Bodegaje"):

### 1. Bodegaje — API Overview

**Para:** SRE / backend devs
**Muestra:**
- Request rate (req/s) por endpoint
- Latencia p50 / p95 / p99
- Errores 4xx / 5xx por segundo
- Tasa de error (%)

**Cuándo mirarlo:** cualquier alerta de `HighErrorRate` o `HighLatencyP95`.

### 2. Bodegaje — Negocio

**Para:** Product Owner / operaciones
**Muestra:**
- Solicitudes creadas (últimas 24h)
- OC aprobadas (últimas 24h)
- Emails en outbox (pendientes)
- Stock bajo-mínimo por bodega

**Cuándo mirarlo:** daily standup, fin de semana para ver tendencias.

### 3. Bodegaje — Infra

**Para:** SRE / DevOps
**Muestra:**
- CPU por contenedor
- Memoria por contenedor
- Conexiones a Postgres (active vs idle)
- Disco usado (%)

**Cuándo mirarlo:** cuando llega una alerta de `MemoryHigh` o
`PostgresConnectionsHigh`.

---

## Alertas (C3.5)

Hay 6 alertas activas (ver [`alerts.yml`](../../infra/docker/prometheus/alerts.yml)):

| Alerta | Severidad | SLA | Runbook |
|---|---|---|---|
| `HighErrorRate` | 🔴 critical | 5 min | [high-error-rate.md](alerts/high-error-rate.md) |
| `OutboxBacklog` | 🔴 critical | 15 min | [outbox-backlog.md](alerts/outbox-backlog.md) |
| `HighLatencyP95` | ⚠️ warning | 30 min | [high-latency.md](alerts/high-latency.md) |
| `NoTraffic` | ⚠️ warning | 30 min | [no-traffic.md](alerts/no-traffic.md) |
| `PostgresConnectionsHigh` | ⚠️ warning | 30 min | [postgres-connections-high.md](alerts/postgres-connections-high.md) |
| `DiskSpaceLow` | ⚠️ warning | 1 h | [disk-space-low.md](alerts/disk-space-low.md) |
| `MemoryHigh` | ⚠️ warning | 1 h | [memory-high.md](alerts/memory-high.md) |

Cada runbook tiene: síntomas, pasos de diagnóstico, mitigación
inmediata, causas probables, mitigación duradera.

---

## Métricas custom de la API (C3.3)

La API expone las siguientes métricas de negocio bajo `/metrics`
(configuradas en `app/modules/observability/metrics.py`):

| Métrica | Tipo | Descripción |
|---|---|---|
| `bodegaje_solicitudes_creadas_total` | counter | Solicitudes creadas, label `prioridad` |
| `bodegaje_ordenes_compra_aprobadas_total` | counter | OC aprobadas |
| `bodegaje_email_outbox_pending` | gauge | Emails pendientes de envío (actualizado cada 60s) |
| `bodegaje_stock_bajo_minimo` | gauge | Items bajo mínimo por bodega |

Para ver las métricas raw: `curl -s http://localhost:8000/metrics | grep bodegaje_`

---

## Operaciones comunes

### Ver todas las alertas activas

```bash
# Desde CLI
curl -s http://localhost:9090/api/v1/alerts | jq .

# Desde UI
# http://localhost:9090/alerts
```

### Silenciar una alerta durante X tiempo

```bash
# Via API de Alertmanager
amtool silence add \
    --alertmanager.url=http://localhost:9093 \
    --duration=2h \
    --comment="Mantenimiento programado" \
    HighErrorRate

# Listar silencios activos
amtool silence list --alertmanager.url=http://localhost:9093
```

### Probar que una alerta se dispara

```bash
# Generar 5xx errors
./infra/scripts/test-alert.sh high-error-rate

# Generar backlog de outbox
./infra/scripts/test-alert.sh outbox-backlog

# Matar Redis
./infra/scripts/test-alert.sh redis-down
```

### Ver logs de Prometheus / Alertmanager

```bash
docker logs bodegaje-prometheus --tail 50
docker logs bodegaje-alertmanager --tail 50
```

---

## Configuración por entorno

### Dev (default)

```bash
# Stack de observabilidad: contenedor local
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.observability.yml up -d

# Sin Slack (las alertas van a logs, no a chat)
SLACK_WEBHOOK_URL="" docker compose ...
```

### Staging

```bash
# Mismo stack + Slack en canal #staging-alerts
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../XXX" \
  docker compose -f infra/docker/docker-compose.yml \
                 -f infra/docker/compose.observability.yml \
                 -f infra/docker/compose.staging.yml \
                 up -d
```

### Producción

```bash
# Stack completo + Slack en #oncall + Sentry team plan
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../XXX" \
ONCALL_EMAIL="oncall@bodega.cl" \
GRAFANA_ADMIN_PASSWORD="$(openssl rand -hex 32)" \
SENTRY_DSN="https://...@sentry.io/..." \
  docker compose -f infra/docker/docker-compose.yml \
                 -f infra/docker/compose.observability.yml \
                 -f infra/docker/compose.production.yml \
                 up -d
```

---

## Mantenimiento

### Retención de métricas

Prometheus retiene métricas por **15 días** por default. Para más
retención, editar el flag `--storage.tsdb.retention.time` en
`compose.observability.yml`.

### Rotación de logs de Prometheus

Si el volumen `prometheus_data` crece mucho (>10 GB), ejecutar:

```bash
docker exec bodegaje-prometheus promtool tsdb analyze /prometheus
```

Y luego, si es necesario, purgar datos antiguos:

```bash
# Stop, purge, restart (durante una ventana de mantenimiento)
docker compose stop prometheus
docker run --rm -v bodega_prometheus_data:/prometheus prom/prometheus \
    promtool tsdb delete --retention=15d
docker compose start prometheus
```

### Backup de Grafana (dashboards)

Los dashboards están en `infra/docker/grafana/dashboards/*.json`
(versionados en git). No es necesario backup adicional; el código es
la fuente de verdad.

---

## Troubleshooting

### Prometheus no puede scrapear la API

```bash
# Verificar que la API expone /metrics
curl -s http://localhost:8000/metrics | head -5

# Verificar la config de Prometheus
docker exec bodegaje-prometheus promtool check config /etc/prometheus/prometheus.yml

# Ver los targets
curl -s http://localhost:9090/api/v1/targets | jq .
```

### Las alertas no se disparan

```bash
# 1. Verificar que Prometheus esta scrapeando
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {scrapePool, health, lastError}'

# 2. Evaluar la regla manualmente
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.name=="HighErrorRate")'

# 3. Verificar Alertmanager
curl -s http://localhost:9093/api/v1/status | jq .
```

### Grafana no muestra datos

```bash
# 1. Verificar datasource
curl -s -u admin:admin http://localhost:3000/api/datasources

# 2. Test query desde la UI
# Explore > Prometheus > ejecutar: http_requests_total

# 3. Ver logs de Grafana
docker logs bodegaje-grafana --tail 50
```

---

## Referencias

- [disaster-recovery.md](disaster-recovery.md)
- [Runbooks de alertas](alerts/)
- [ADR-0001 postgres-strategy](../adr/adr-0001-postgres-strategy.md)
- [infra/scripts/pre-deploy-check.sh](../../infra/scripts/pre-deploy-check.sh)
- [infra/scripts/test-alert.sh](../../infra/scripts/test-alert.sh)
