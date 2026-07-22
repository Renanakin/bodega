# Alerta: HighLatencyP95

**Severidad:** ⚠️ warning
**Origen:** Prometheus
**SLA respuesta:** 30 min
**Componente:** `bodegaje-api`

---

## ¿Qué significa?

El percentil 95 de latencia HTTP supera 1 segundo durante los últimos
5 minutos. La API responde, pero lenta. Esto suele pasar **antes** de
que la API caiga, así que es una alerta temprana.

## ¿Qué hacer?

### 1. Ver el dashboard de latencia (1 min)

Ir a Grafana → Dashboard "Bodegaje — API Overview" → panel "Latencia
p50 / p95 / p99". Identificar qué endpoint está causando el problema.

### 2. Buscar queries lentas (3 min)

```bash
# Top 10 queries lentas en Postgres
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT round(mean_exec_time::numeric, 2) as mean_ms,
         calls,
         query
  FROM pg_stat_statements
  ORDER BY mean_exec_time DESC
  LIMIT 10;
"
```

Si `pg_stat_statements` no está activo, activarlo en `postgresql.conf`:
```conf
shared_preload_libraries = 'pg_stat_statements'
pg_stat_statements.track = top
```

### 3. Verificar lock contention (2 min)

```bash
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT pid, usename, application_name, state, wait_event_type, wait_event,
         age(clock_timestamp(), query_start) as duration, query
  FROM pg_stat_activity
  WHERE datname = 'bodegaje' AND state != 'idle'
  ORDER BY query_start;
"
```

Si hay muchos procesos esperando el mismo `wait_event`, hay un lock.

### 4. Verificar el pool de conexiones (1 min)

```bash
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT count(*), state
  FROM pg_stat_activity
  WHERE datname = 'bodegaje'
  GROUP BY state;
"
```

Si `idle` es 0 y `active` está cerca del `max_connections`, el pool
está saturado.

### 5. Mitigación (5 min)

| Causa probable | Mitigación |
|---|---|
| Query N+1 nueva | Rollback al último commit |
| Falta de índice | `CREATE INDEX CONCURRENTLY` |
| Lock de una transacción larga | Identificar y matar el PID |
| Pool saturado | Aumentar `pool_size` en `app.db.session` |
| Redis lento | Reiniciar Redis |

## Mitigación de emergencia

Si la latencia no baja en 15 min, **rollback al deploy anterior** (ver
[high-error-rate.md](high-error-rate.md#4-mitigación-inmediata)).

## Referencias

- [disaster-recovery.md](../disaster-recovery.md)
- [PostgreSQL performance tips](https://wiki.postgresql.org/wiki/Performance_Optimization)
