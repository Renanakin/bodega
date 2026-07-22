# Alerta: MemoryHigh

**Severidad:** ⚠️ warning
**Origen:** Prometheus
**SLA respuesta:** 1 hora
**Componente:** `host`

---

## ¿Qué significa?

El sistema está usando > 90% de RAM por 15+ minutos. Riesgo de
OOM kills (Linux mata el proceso que más memoria usa, que puede ser
Postgres o la API).

## ¿Qué hacer?

### 1. Ver uso de memoria por proceso (2 min)

```bash
# Top 10 procesos por memoria
ps aux --sort=-%mem | head -11

# Memoria por contenedor Docker
docker stats --no-stream
```

### 2. Identificar al culpable (5 min)

Si es la **API**:
```bash
docker logs bodegaje-api --tail 100 2>&1 | grep -E "(MemoryError|out of memory|ResourceWarning)"
```

Posibles causas:
- Memory leak en una request específica (raro).
- Query que retorna millones de filas (más común).
- Cache sin límite (ej: `aiocache` sin `ttl`).

Si es **Postgres**:
```bash
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT pid, application_name, state,
         pg_size_pretty(pg_memory_usage_bytes) as mem
  FROM pg_stat_activity
  WHERE datname = 'bodegaje'
  ORDER BY pg_memory_usage_bytes DESC NULLS LAST
  LIMIT 5;
"
```

Posibles causas:
- `work_mem` muy alto.
- Query con sort/hash enorme.
- Conexiones zombie.

Si es el **host** (no Docker):
- Algún proceso del sistema (cron, journal, etc.) se disparó.
- Revisar `dmesg | tail -20` para OOM kills recientes.

### 3. Liberar memoria (rápido)

#### Si es un contenedor
```bash
docker restart bodegaje-api
docker restart bodegaje-worker
```

#### Si es el host
```bash
# Liberar pagecache
sync && echo 3 > /proc/sys/vm/drop_caches

# Verificar
free -h
```

### 4. Prevenir recurrencia

- **Limitar memoria de contenedores:**
  ```yaml
  # docker-compose.yml
  services:
    api:
      deploy:
        resources:
          limits:
            memory: 1G
  ```

- **Bajar `work_mem` de Postgres** si está muy alto:
  ```sql
  ALTER SYSTEM SET work_mem = '32MB';
  SELECT pg_reload_conf();
  ```

- **Ajustar `pool_size`** de la app para no acumular sesiones.

## Mitigación de emergencia

Si la memoria llega al 95% y sigue subiendo, **reiniciar el proceso
más grande** antes de que Linux lo mate por OOM:

```bash
# Identificar al mas grande
ps aux --sort=-%mem | head -2

# Reiniciar (ejemplo: api)
docker restart bodegaje-api
```

## Referencias

- [disaster-recovery.md](../disaster-recovery.md)
- [PostgreSQL memory configuration](https://www.postgresql.org/docs/current/runtime-config-resource.html)
