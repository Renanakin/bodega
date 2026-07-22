# Runbook de Disaster Recovery (C2.5)

**Fecha:** 2026-07-22
**Audiencia:** operador de turno, on-call SRE
**SLA objetivo:** RTO 30 min, RPO 24h (con backup diario)

---

## TL;DR

| Escenario | RTO | RPO | Comando principal |
|---|---|---|---|
| **1. BD caída / corrupta** | 15-30 min | <24h (último backup) | `restore-postgres.sh` + smoke E2E |
| **2. Redis caído** | 1 min | 0 (cache, se reconstruye) | `docker compose restart redis` |
| **3. Servicio caído** | 2-5 min | 0 (stateless) | `docker compose restart api` |

---

## Escenario 1 — Postgres caído o corrupto

### Síntomas
- `GET /health/ready` retorna 503 con `postgres: connection refused`.
- La UI no carga bodegas ni productos.
- Logs muestran `asyncpg.exceptions.PostgresConnectionError` o `FATAL: database files are incompatible`.

### Pasos

#### 1.1 — Verificar el estado del contenedor

```bash
docker ps | grep postgres
docker logs bodegaje-db --tail 50
```

**Si el contenedor está vivo pero la BD corrupta** (raro):
```bash
docker exec bodegaje-db pg_isready -U bodegaje
# Si retorna "no response" o "FATAL": la BD está corrupta
```

**Si el contenedor está muerto**:
```bash
docker inspect bodegaje-db --format '{{.State.Status}}'
# Si está en "restarting" o "exited": ver docker logs arriba
```

#### 1.2 — Listar backups disponibles

```bash
./infra/scripts/restore-postgres.sh --list
# Muestra los ultimos 30 backups con tamano y edad
```

#### 1.3 — Tomar el último backup bueno

Elegir el más reciente que tenga tamaño coherente (>100 KB, no 0).

```bash
# Ejemplo: backup de las 03:00 de hoy
BACKUP=/var/backups/bodegaje/bodegaje-20260722-030000.sql.gz
ls -la $BACKUP
# Verificar que el archivo existe y no es vacio
```

#### 1.4 — Restaurar (¡CUIDADO! Sobreescribe la BD)

```bash
./infra/scripts/restore-postgres.sh $BACKUP
# PIDE CONFIRMACION: escribir 'SI' en mayusculas
```

El script:
1. Termina conexiones activas
2. DROP DATABASE bodegaje
3. CREATE DATABASE bodegaje
4. pg_restore desde el backup
5. Reporta el conteo de tablas

#### 1.5 — Verificar que la API responde

```bash
curl -s http://localhost:8000/api/v1/health/ready | jq .
# Debe retornar: {"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}}
```

#### 1.6 — Smoke E2E post-restore

```bash
cd apps/api
python -m pytest tests/integration/test_solicitudes.py -v --no-header
# 9 tests, deben pasar todos

# Bateria E2E completa
python auditoria-fase5/bateria_e2e_demo.py
# 50/51 (un test requiere usuario con rol especial)
```

#### 1.7 — Comunicación a stakeholders

Si la BD se cayó en horario de operación, enviar aviso:
- "El sistema tuvo una caída de BD a las HH:MM. Se restauró desde el backup de las HH:MM. La pérdida de datos es <24h."

---

## Escenario 2 — Redis caído

### Síntomas
- `GET /health/ready` retorna 503 con `redis: connection refused`.
- La UI carga pero la campanita de notificaciones no se actualiza.
- `Idempotency-Key` middleware falla con 500.

### Pasos

#### 2.1 — Verificar

```bash
docker ps | grep redis
docker logs bodegaje-redis --tail 20
redis-cli -h 127.0.0.1 -p 6379 PING
# Si retorna error: confirmar caida
```

#### 2.2 — Reiniciar (1 minuto)

```bash
docker compose -f infra/docker/docker-compose.yml restart redis
# o
docker restart bodegaje-redis
```

#### 2.3 — Verificar

```bash
redis-cli -h 127.0.0.1 -p 6379 PING
# Debe retornar: PONG
curl -s http://localhost:8000/api/v1/health/ready | jq .checks.redis
# Debe retornar: "ok"
```

**Impacto de la caída:**
- Idempotency-Key cache se pierde → requests duplicados podrían crear entidades duplicadas (mitigado por `UNIQUE` constraints en BD).
- Outbox de emails sigue funcionando (es código defensivo).
- Notificaciones in-app siguen funcionando (van a BD).

**RPO = 0** (Redis es cache, no fuente de verdad).

---

## Escenario 3 — Servicio (API) caído

### Síntomas
- `GET /health/ready` retorna 503 con `app: not initialized`.
- Nginx retorna 502 Bad Gateway.
- Los logs del servicio muestran un crash.

### Pasos

#### 3.1 — Ver logs del servicio

```bash
docker logs bodegaje-api --tail 100
# Buscar stacktrace, "RuntimeError", "ImportError", etc.
```

#### 3.2 — Si es un crash simple, reiniciar

```bash
docker compose -f infra/docker/docker-compose.yml restart api
```

#### 3.3 — Si no se recupera, rollback al deploy anterior

```bash
# Listar imagenes disponibles
docker images | grep bodega

# Marcar la imagen buena anterior como "previous"
docker tag bodega-api:v1.0.0-rc1 bodega-api:previous

# Re-deployar la imagen anterior
docker compose -f infra/docker/docker-compose.yml up -d --force-recreate api
```

#### 3.4 — Si persiste, escalar horizontalmente (si hay replicas)

```bash
docker compose -f infra/docker/docker-compose.yml up -d --scale api=3
# 3 replicas detras del Nginx, distribucion round-robin
```

---

## Escenario 4 — Nginx caído (producción)

### Síntomas
- El puerto 80/443 no responde.
- Los usuarios no pueden acceder a la UI.

### Pasos

```bash
docker ps | grep nginx
docker logs bodegaje-nginx --tail 50

docker compose -f infra/docker/docker-compose.yml restart nginx
```

Si la config está corrupta, restaurar desde git:
```bash
cd /opt/bodega
git checkout HEAD -- infra/docker/nginx/conf.d/production.conf
docker compose -f infra/docker/docker-compose.yml restart nginx
```

---

## Backups: política y verificación

### Política (C2.4)
- **Frecuencia:** diario, 03:00 UTC.
- **Retención:** 7 diarios + 4 semanales + 3 mensuales.
- **Storage:** local en `/var/backups/bodegaje` + S3 (off-site) si `BACKUP_S3_BUCKET` está configurado.
- **Verificación:** `pg_restore --list` valida integridad tras cada backup.

### Verificación manual

```bash
# 1. Listar backups
./infra/scripts/restore-postgres.sh --list

# 2. Tomar un backup fresco
./infra/scripts/backup-postgres.sh

# 3. Validar que se puede restaurar
./infra/scripts/test-backup-restore.ps1
# Exit 0 = OK
```

### Test E2E mensual (sugerido)

Agregar al runbook operacional:
- **Día 1 de cada mes:** ejecutar `test-backup-restore.ps1` y guardar el log.
- **Si falla:** abrir incidente y revisar logs de Postgres + script de backup.

---

## Rotación de secretos (C2.8)

### Cuándo rotar
- Cada 90 días (recomendación OWASP).
- Inmediatamente si se sospecha compromiso.
- Cuando un empleado con acceso se va de la empresa.

### Procedimiento

```bash
# 1. Generar nuevos secretos
python infra/scripts/generate-secrets.py
# Imprime: JWT_SECRET=..., SECRET_KEY=..., POSTGRES_PASSWORD=...

# 2. Aplicar a producción
# - En Render: Environment > Update secret
# - En VPS: editar .env.production y reiniciar

# 3. Reiniciar servicio (sin downtime: rolling restart)
docker compose -f infra/docker/docker-compose.yml up -d --force-recreate api
docker compose -f infra/docker/docker-compose.yml up -d --force-recreate worker

# 4. Verificar que los tokens antiguos son rechazados
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"test"}'
# Si retorna 401 con token viejo: rotacion exitosa
```

### Impacto
- **JWT_SECRET rotado:** todos los usuarios deben re-loguearse. No invalida la BD.
- **SECRET_KEY rotado:** tokens de aprobación de OC (ADR-0005) emitidos antes son inválidos. Si había OCs pendientes, hay que reemitir tokens.
- **POSTGRES_PASSWORD rotado:** requiere actualizar `DATABASE_URL` y reiniciar. Sin downtime si se hace en rolling restart.

---

## Contactos de escalación

| Rol | Persona | Canal | Tiempo de respuesta |
|---|---|---|---|
| On-call primario | nano | Slack #oncall | 15 min |
| On-call secundario | (por definir) | Slack #oncall | 30 min |
| DBA | (por definir) | Email | 1h |
| Proveedor cloud | (Render / DO / etc) | Support ticket | 4h |

---

## Referencias

- **Scripts:** `infra/scripts/backup-postgres.sh`, `infra/scripts/restore-postgres.sh`, `infra/scripts/test-backup-restore.ps1`
- **Fase 10:** `docs/fases/fase-10-hardening-produccion.md`
- **Plan de backup:** este documento §"Backups: política y verificación"
- **ADR-0001:** PostgreSQL como target de producción
- **ADR-0007:** Hashing de contraseñas (PBKDF2 600k)
