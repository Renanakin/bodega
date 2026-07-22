# Alerta: HighErrorRate

**Severidad:** 🔴 critical
**Origen:** Prometheus
**SLA respuesta:** 5 min
**Componente:** `bodegaje-api`

---

## ¿Qué significa?

La API está retornando errores 5xx (errores internos del servidor) a más
del 1% de los requests durante los últimos 5 minutos. Esto es **crítico**
porque afecta directamente a los usuarios.

## ¿Qué hacer?

### 1. Verificar el estado general (1 min)

```bash
# Estado de los contenedores
docker ps | grep bodegaje

# Healthcheck de la API
curl -s http://localhost:8000/api/v1/health/ready | jq .

# Logs de la API (ultimas 100 lineas)
docker logs bodegaje-api --tail 100
```

### 2. Identificar el tipo de error (2 min)

```bash
# Buscar stacktraces en logs
docker logs bodegaje-api --tail 500 2>&1 | grep -E "(Error|Exception|Traceback)" | head -10
```

Errores comunes:
- `asyncpg.exceptions.PostgresConnectionError` → BD caída.
- `redis.exceptions.ConnectionError` → Redis caído.
- `RuntimeError: ...` → bug en código (revisar última migración).
- `KeyError: 'X-Correlation-ID'` → bug en middleware.

### 3. Verificar componentes dependientes

```bash
# Postgres
docker exec bodegaje-db pg_isready -U bodegaje
docker logs bodegaje-db --tail 20

# Redis
docker exec bodegaje-redis redis-cli PING

# Mailpit (afecta el outbox, no requests HTTP directamente)
docker logs bodegaje-mailpit --tail 10
```

### 4. Mitigación inmediata

Si el problema es **BD caída**: ver [disaster-recovery.md §"Escenario 1"](../disaster-recovery.md#escenario-1--postgres-caído-o-corrupto).

Si el problema es **Redis caído**: ver [disaster-recovery.md §"Escenario 2"](../disaster-recovery.md#escenario-2--redis-caído).

Si el problema es **bug en código**: hacer rollback al deploy anterior:

```bash
docker tag bodega-api:v1.0.0-rc1 bodega-api:previous
docker compose -f infra/docker/docker-compose.yml up -d --force-recreate api
```

### 5. Verificar recuperación

Esperar 2-3 minutos y revisar:

```bash
# Grafana: dashboard "API Overview" → "Tasa de error (%)" debe bajar a 0
# Slack: el bot publica "RESOLVED" cuando la alerta se cierra
```

---

## Prevención

- **Healthcheck proactivo:** el job de CI debería hacer un test de carga
  sintético cada 6h y alertar si la tasa de error > 0.5%.
- **Alertas tempranas:** la métrica `http_requests_5xx_total` debería
  estar en un dashboard visible, no solo en alertas.
- **Runbook por excepción:** mapear los `Exception` más comunes a
  acciones específicas (no siempre es "rollback").

## Referencias

- [disaster-recovery.md](../disaster-recovery.md)
- [api-overview dashboard](../../infra/docker/grafana/dashboards/api-overview.json)
