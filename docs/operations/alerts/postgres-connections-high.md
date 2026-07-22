# Alerta: PostgresConnectionsHigh

**Severidad:** ⚠️ warning
**Origen:** Prometheus
**SLA respuesta:** 30 min
**Componente:** `postgres`

---

## ¿Qué significa?

El pool de conexiones a Postgres está al >80% del máximo configurado.
Riesgo de timeouts en requests nuevos. Si llega al 100%, la app empieza
a fallar con `pool_timeout`.

## ¿Qué hacer?

### 1. Ver conexiones activas (1 min)

```bash
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT count(*), state, application_name
  FROM pg_stat_activity
  WHERE datname = 'bodegaje'
  GROUP BY state, application_name
  ORDER BY count(*) DESC;
"
```

### 2. Buscar conexiones zombi (2 min)

```bash
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT pid, application_name, client_addr, state,
         age(clock_timestamp(), state_change) as idle_for,
         query
  FROM pg_stat_activity
  WHERE datname = 'bodegaje' AND state = 'idle'
    AND state_change < now() - interval '5 minutes'
  ORDER BY state_change;
"
```

Si hay conexiones `idle` por más de 5 min, son leaks.

### 3. Matar conexiones zombi (si las hay)

```bash
# Cuidado: esto cierra TODAS las conexiones idle >5 min
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = 'bodegaje' AND state = 'idle'
    AND state_change < now() - interval '5 minutes';
"
```

### 4. Verificar el pool_size de la app

`apps/api/app/db/session.py`:

```python
pool_size: int = 20  # conexiones maximas por proceso
max_overflow: int = 10  # conexiones extra permitidas
```

Si hay N workers de uvicorn, el total es N * (pool_size + max_overflow).
Con 4 workers y los defaults: 4 * 30 = 120 conexiones, que está cerca
del default de Postgres (100).

### 5. Ajustar max_connections de Postgres (si es necesario)

```bash
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SHOW max_connections;
"
# Si es muy bajo, editar postgresql.conf:
# max_connections = 200
```

## Mitigación duradera

1. **PgBouncer** entre la app y Postgres (connection pooling real).
2. **Reducir pool_size** en la app y subir `max_overflow`.
3. **Cerrar conexiones explícitamente** en código (session.close()).
4. **Timeouts** en `app.db.session` para que conexiones colgadas se
   cierren solas.

## Referencias

- [disaster-recovery.md §"Escenario 1"](../disaster-recovery.md#escenario-1--postgres-caído-o-corrupto)
- [PostgreSQL connection pooling](https://www.postgresql.org/docs/current/runtime-config-connection.html)
