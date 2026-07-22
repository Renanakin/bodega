# Alerta: OutboxBacklog

**Severidad:** 🔴 critical
**Origen:** Prometheus
**SLA respuesta:** 15 min
**Componente:** `worker`

---

## ¿Qué significa?

Más de 100 emails en `email_outbox` llevan más de 10 minutos sin
procesarse. Esto indica que el **worker Arq** no está cumpliendo su
trabajo. Consecuencia: los usuarios no reciben notificaciones por
email (aprobaciones de OC, alertas de stock bajo mínimo, etc.).

## ¿Qué hacer?

### 1. Verificar el estado del worker (1 min)

```bash
docker ps | grep worker
docker logs bodegaje-worker --tail 50
```

El worker debería estar logueando algo como:
```
worker.starting
worker.ready
```

### 2. Verificar Redis (la cola vive ahí) (1 min)

```bash
docker exec bodegaje-redis redis-cli PING
docker exec bodegaje-redis redis-cli LLEN arq:queue
```

Si `LLEN` muestra muchos items pero el worker no procesa, hay un bug.

### 3. Verificar SMTP (Mailpit o proveedor real) (2 min)

```bash
# Si es dev/staging
docker ps | grep mailpit
docker logs bodegaje-mailpit --tail 10
curl -s http://localhost:8025/api/v1/messages | jq ' | length'

# Si es prod con SMTP real
echo "Test" | mail -s "test" admin@bodega.cl
```

### 4. Reiniciar el worker (1 min)

```bash
docker compose -f infra/docker/docker-compose.yml restart worker
```

Esperar 30 segundos y revisar:
```bash
docker logs bodegaje-worker --tail 30
```

### 5. Verificar que el backlog baja

```bash
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT status, count(*)
  FROM email_outbox
  GROUP BY status;
"
```

Debería verse: `pending` bajando, `sent` subiendo.

## Causas probables

| Síntoma | Causa | Mitigación |
|---|---|---|
| Worker no está corriendo | crash / OOM | Reiniciar, ver logs |
| Worker corre pero no procesa | Bug en código | Rollback al último commit bueno |
| Redis lleno / caído | Disco / restart | Reiniciar Redis, ver disco |
| SMTP rechaza todos | Auth / config | Verificar credenciales, sandbox |
| `attempts` > 5 en todos | Email destino rebota | Verificar dominio, SPF, DKIM |

## Mitigación de emergencia

Si el worker no se recupera en 5 min, **matar y recrear**:

```bash
docker compose -f infra/docker/docker-compose.yml down worker
docker compose -f infra/docker/docker-compose.yml up -d worker
```

Si hay muchos emails con `status='dead'` (más de 5 intentos fallidos),
revisar manualmente:

```bash
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "
  SELECT id, to_email, subject, last_error, attempts
  FROM email_outbox
  WHERE status = 'dead'
  ORDER BY created_at DESC
  LIMIT 20;
"
```

Decidir si re-enviar o descartar manualmente.

## Referencias

- ADR-0004 (smtp-async-architecture)
- ADR-0005 (smtp-stack)
- [disaster-recovery.md §"Escenario 2"](../disaster-recovery.md#escenario-2--redis-caído)
