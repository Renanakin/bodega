---
title: "Deployment Runbook — Bodegaje (Fase 10)"
date: 2026-07-15
status: "Vigente"
owner: "Equipo Backend / DevOps"
scope: "infra, apps/api, apps/web, db"
audience: "operadores de guardia, SRE, devs en on-call"
tags: ["runbook", "operaciones", "produccion", "incidentes", "rollback", "fase-10"]
---

# Deployment Runbook — Bodegaje

> Este runbook es la **guía operativa** para desplegar, monitorear, hacer rollback y resolver incidentes del sistema Bodegaje en producción. Está pensado para que un operador nuevo pueda ejecutarlo sin contexto previo, paso a paso.

---

## 1. Prerrequisitos

Antes de cualquier operación en producción, el operador debe tener:

| Herramienta | Versión mínima | Uso |
|---|---|---|
| Docker Desktop / Docker Engine | 24.0+ | Levantar/parar el stack |
| Docker Compose | v2.20+ | Orquestación de servicios |
| Git | 2.40+ | Rollback, ver diff, leer tags |
| Python | 3.12+ | Generar secretos, correr tests |
| psql (PostgreSQL client) | 15+ | Inspeccionar BD, restore manual |
| AWS CLI | 2.x | Acceder a S3 (backups off-site) |
| Acceso al repo | — | `git pull`, `git log` |
| Acceso al servidor de producción | SSH o Portainer | Ejecutar comandos |
| Vault o acceso a `.env.production` | — | Leer secretos |

> **Verificación rápida**: `docker --version && docker compose version && python --version && aws --version`

---

## 2. Pre-deployment checklist (10 items)

Ejecutar **todos** los items antes de cada deploy a producción. Si cualquiera falla, **NO hacer deploy**.

```bash
# 1. No hay secretos en el diff (el check #1 de pre-deploy-check.sh ya lo hace).
git diff --staged | grep -E "(SECRET_KEY|JWT_SECRET|POSTGRES_PASSWORD)" | grep -v "=__"

# 2. Migraciones Alembic creadas y commiteadas.
ls apps/api/alembic/versions/*.py | tail -5

# 3. Tests pasan localmente.
cd apps/api && python -m pytest tests/unit -q

# 4. Build OK.
cd apps/api && python -m ruff check app tests

# 5. Docker compose config valido.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml config -q

# 6. Nginx config valido.
docker run --rm -v $PWD:/cfg:ro nginx:alpine \
    sh -c "cp /cfg/infra/docker/nginx/conf.d/production.conf /etc/nginx/conf.d/default.conf && nginx -t"

# 7. .env.production existe y tiene JWT_SECRET, SECRET_KEY >= 32 chars.
[ -f .env.production ] && grep -E "^(JWT_SECRET|SECRET_KEY)=" .env.production | awk -F= '{print $1, length($2)}'

# 8. SMTP_USE_TLS=true en .env.production (ADR-0004: obligatorio).
grep SMTP_USE_TLS .env.production

# 9. Disco > 1GB libre en el host.
df -h / | awk 'NR==2 {print "Libre:", $4}'

# 10. Backup reciente existe (< 25h).
ls -t var/backups/bodegaje/bodegaje-*.sql.gz 2>/dev/null | head -1
```

**Comando único equivalente**: `bash infra/scripts/pre-deploy-check.sh production` corre los 10 checks (incluyendo el de tests, que es el más lento). Exit code 0 = OK.

---

## 3. Despliegue inicial (10 pasos, ~30 min)

Para el primer deploy desde cero en un servidor limpio.

### Paso 1: Conectarse al servidor
```bash
ssh deploy@bodega.example.com
```

### Paso 2: Clonar el repo
```bash
git clone https://github.com/<org>/bodega.git /opt/bodega
cd /opt/bodega
```

### Paso 3: Crear el archivo `.env.production`
```bash
# Copiar plantilla
cp infra/.env.production.example .env.production

# Generar secretos seguros
python infra/scripts/generate-secrets.py --print-only
# Copiar el output a .env.production, reemplazando los placeholders.

# Resto de variables (SMTP, SENTRY, etc) las rellena ops desde el vault.
chmod 600 .env.production
```

### Paso 4: Verificar aislamiento de secretos
```bash
bash infra/scripts/check-env-isolation.sh
```

### Paso 5: Crear directorios para datos persistentes
```bash
sudo mkdir -p /var/lib/bodegaje/{postgres,redis,backups}
sudo chown -R 999:999 /var/lib/bodegaje/postgres  # uid del usuario postgres en la imagen
sudo chown -R 999:999 /var/lib/bodegaje/redis
sudo chown -R $USER /var/lib/bodegaje/backups
```

### Paso 6: Pre-deploy check
```bash
bash infra/scripts/pre-deploy-check.sh production
```

### Paso 7: Levantar el stack
```bash
docker compose \
    -f infra/docker/docker-compose.yml \
    -f infra/docker/compose.production.yml \
    up -d --build
```

### Paso 8: Verificar healthcheck
```bash
sleep 30  # dar tiempo a que arranque
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml ps
curl -i http://localhost/api/v1/health
```

Esperado: HTTP 200 con `components.db.status="ok"`, `components.redis.status="ok"`, `components.worker.status="ok"`.

### Paso 9: Verificar logs y métricas
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs -f --tail=50
curl -s http://localhost/metrics | head -20
```

### Paso 10: Cargar datos demo (opcional, solo staging)
```bash
# Solo en staging o demo, NUNCA en produccion real.
docker compose exec api python scripts/load_demo_data.py
```

**Resultado esperado**: stack production arriba, healthcheck 200, métricas fluyendo.

---

## 4. Despliegue continuo (5 pasos, ~5 min)

Para actualizar la app sin downtime (rolling update manual).

### Paso 1: Pull del código nuevo
```bash
cd /opt/bodega
git pull origin main
```

### Paso 2: Pre-deploy check
```bash
bash infra/scripts/pre-deploy-check.sh production
```

### Paso 3: Rebuild de la imagen
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml build api worker
```

### Paso 4: Restart con rolling update
```bash
# Levantar la nueva version (sin --build porque ya construimos).
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up -d api worker

# Nginx sigue sirviendo el frontend con la version vieja de la API por unos
# segundos mientras arranca la nueva. Con 2 workers (uvicorn --workers 2),
# el rolling restart deja al menos 1 vivo en todo momento.
```

### Paso 5: Verificar post-deploy
```bash
sleep 10
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml ps
curl -i http://localhost/api/v1/health
curl -i http://localhost/api/v1/health/ready  # readiness probe
```

Si alguno de los checks falla, ir a **sección 5 (Rollback)**.

---

## 5. Rollback (3 estrategias)

Cuando el deploy nuevo rompe algo. Orden de preferencia: **git revert > docker rollback > DB migration down**.

### 5.1 Estrategia A: `git revert` (preferida, más limpia)

```bash
# 1. Identificar el commit problematico.
git log --oneline -20

# 2. Revertir el commit (crea un nuevo commit que deshace los cambios).
git revert <commit-hash>

# 3. Push y redeploy normal.
git push origin main
# (dispara el CI, que hace el deploy automatico)

# Si NO hay CI automatico, hacer manual:
git pull origin main
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml build api worker
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up -d api worker
```

**Cuándo usar**: el bug es en código Python/JS, no en schema de BD.

### 5.2 Estrategia B: Docker rollback (rápido, sin git)

```bash
# 1. Ver la imagen actual y la anterior.
docker images | grep bodegaje-api

# Ejemplo:
# bodegaje-api    v1.2.3    abc123    2 hours ago
# bodegaje-api    v1.2.2    def456    1 day ago

# 2. Taggear la imagen anterior como la actual.
docker tag bodegaje-api:def456 bodegaje-api:latest

# 3. Restart con la imagen anterior.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up -d api worker

# 4. Verificar.
curl -i http://localhost/api/v1/health
```

**Cuándo usar**: necesitas rollback en <1 min y el tag de la imagen anterior sigue accesible.

### 5.3 Estrategia C: DB migration down (último recurso, destructivo)

```bash
# 1. Ver las migraciones aplicadas.
docker compose exec api alembic current

# 2. Bajar 1 version.
docker compose exec api alembic downgrade -1

# 3. Verificar que la app sigue arrancando.
docker compose restart api
curl -i http://localhost/api/v1/health

# 4. Si la app no arranca con el schema viejo, es porque los modelos
#    cambiaron incompatiblmente. En ese caso, hacer rollback a la imagen
#    vieja (estrategia B) Y mantener la migracion bajada hasta investigar.
```

**Cuándo usar**: la nueva migración de BD es incompatible con el código viejo y necesitas volver al schema anterior.

**Advertencia CRÍTICA**: `alembic downgrade` puede **perder datos** si la migración anterior eliminaba columnas. Hacer backup antes:

```bash
# Backup antes de downgrade.
bash infra/scripts/backup-postgres.sh --upload-s3
# Luego downgrade.
docker compose exec api alembic downgrade -1
```

---

## 6. Incidentes comunes (8 escenarios)

### 6.1 BD caída

**Síntomas**: `/api/v1/health` retorna 503, `components.db.status="error"`, logs con `asyncpg.exceptions.CannotConnectNowError`.

**Diagnóstico**:
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml ps db
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs db --tail=50
```

**Causas comunes**:
1. Disco lleno → `df -h /var/lib/bodegaje/postgres`
2. OOM kill → `dmesg | grep -i "killed process"`
3. Migración corrupta → `docker compose exec db psql -U bodegaje -c '\dt'`

**Resolución**:
```bash
# Reiniciar el servicio (auto-recovery con restart: always).
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml restart db

# Si sigue caido, levantar con logs en vivo.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up db
```

### 6.2 Redis caído

**Síntomas**: `/api/v1/health` retorna 503, `components.redis.status="error"`, requests lentos (cache misses).

**Diagnóstico**:
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml ps redis
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs redis --tail=30
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" ping
```

**Resolución**:
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml restart redis
```

**Mitigación**: la app funciona con Redis caido (degraded mode: sin cache, sin rate limit distribuido). El rate limit pasa a ser in-memory por proceso.

### 6.3 Worker muerto (Arq)

**Síntomas**: emails no se envian, replenishment no corre, `/api/v1/health` retorna `components.worker.status="error"`.

**Diagnóstico**:
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml ps worker
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs worker --tail=50
```

**Resolución**:
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml restart worker
# Verificar que arranca y se conecta a Redis.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs worker --tail=20 | grep "redis"
```

### 6.4 SMTP caído (SES o Mailgun)

**Síntomas**: emails no salen, `bodegaje_email_failed_total` crece, logs con `SMTPError`.

**Diagnóstico**:
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs api --tail=30 | grep -i smtp
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml exec api \
    python -c "import asyncio; from app.modules.notifications.smtp import SmtpClient; print(asyncio.run(SmtpClient(get_settings()).verify()))"
```

**Resolución**:
- **SES throttled**: revisar cuotas en AWS Console, esperar.
- **Credenciales expiradas**: rotar en AWS Secrets Manager, actualizar `.env.production`, restart.
- **TLS handshake fail**: verificar `SMTP_USE_TLS=true` y que el puerto sea 587 (STARTTLS) o 465 (implicit TLS).

Los emails fallidos quedan en el outbox (`email_outbox` table) y se reintentan automáticamente con backoff exponencial (30s, 5min, 30min). Tras 3 intentos van a `status='dead'` y requieren acción manual.

### 6.5 Nginx 502 Bad Gateway

**Síntomas**: todas las requests retornan 502.

**Diagnóstico**:
```bash
# Ver si los containers de api/web estan healthy.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml ps
# Logs de nginx.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs nginx --tail=20
```

**Causas comunes**:
1. API crasheada → ver logs de api: `docker compose ... logs api --tail=50`
2. DNS interno roto → el container nginx no resuelve `api:8000`.
3. API arrancando (cold start) → esperar 10-20s.

**Resolución**:
```bash
# Forzar restart del upstream.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml restart api
# Nginx deberia detectar el upstream vivo en < 5s.
```

### 6.6 Disco lleno

**Síntomas**: deploy falla, BD no arranca, logs con `No space left on device`.

**Diagnóstico**:
```bash
df -h /
du -sh /var/lib/bodegaje/*  # encontrar que ocupa mas
du -sh /var/log/*  # logs viejos?
```

**Resolución**:
```bash
# 1. Limpiar logs viejos de Docker.
docker system prune -a --volumes  # CUIDADO: borra TODO. Solo si sabes lo que haces.

# 2. Rotar logs de la app.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs --tail=0  # vacia buffers

# 3. Si la BD es lo que ocupa, limpiar archivos WAL viejos.
docker compose exec db vacuumdb -U bodegaje --analyze

# 4. Si los backups ocupan mucho, subir el S3 retention mas corta.
ls -la /var/lib/bodegaje/backups/ | head -20
```

### 6.7 SSL expirado

**Síntomas**: navegador muestra "Your connection is not private", healthcheck externo falla.

**Diagnóstico**:
```bash
openssl s_client -connect bodega.example.com:443 -servername bodega.example.com < /dev/null 2>&1 | openssl x509 -noout -dates
```

**Resolución con Let's Encrypt + certbot** (recomendado):
```bash
# 1. Renovar manualmente.
sudo certbot renew --force-renewal

# 2. Recargar Nginx (si certbot no lo hace automaticamente).
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml exec nginx nginx -s reload

# 3. Verificar.
curl -I https://bodega.example.com
```

**Resolución con Caddy** (auto-renew): Caddy renueva automáticamente. Solo verificar logs:
```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs caddy | grep -i "renewal"
```

### 6.8 Token de aprobación OC comprometido

**Síntomas**: supervisor reporta haber aprobado/rechazado OC que no reconece, o `bodegaje_email_outbox_pending` se vacia sospechosamente rápido.

**Diagnóstico**:
```bash
# Ver ultimas aprobaciones.
docker compose exec db psql -U bodegaje -c "
SELECT id, codigo, id_supervisor, estado, updated_at
FROM ordenes_compra
ORDER BY updated_at DESC
LIMIT 20;
"

# Ver logs del endpoint publico (sin auth, rate-limited).
docker compose logs nginx --tail=200 | grep "/api/v1/public/ordenes-compra"
```

**Resolución**:
```bash
# 1. ROTAR SECRET_KEY inmediatamente (firma de tokens OC).
#    Editar .env.production, generar nuevo SECRET_KEY:
python infra/scripts/generate-secrets.py --print-only
#    Actualizar .env.production, restart api/worker.

# 2. Marcar OC afectadas como 'rechazado' manualmente.
docker compose exec db psql -U bodegaje -c "
UPDATE ordenes_compra SET estado='rechazado', updated_at=now()
WHERE id IN (...);
"

# 3. Notificar a los supervisors legitimos.

# 4. Auditar logs: buscar la IP origen del atacante y bloquear en WAF/firewall.
docker compose logs nginx --tail=1000 | grep "<ip-sospechosa>" | head -20
```

---

## 7. Backups y restore

### 7.1 Backups automáticos

- **Backups locales**: el sidecar `backup` corre `pg_dump` diariamente a las 02:30 UTC.
- **Backups off-site**: si `BACKUP_S3_BUCKET` esta configurado, se sube a S3 con storage class STANDARD_IA.
- **Rotación**: diaria 7 días, semanal 4, mensual 12 (configurable via `BACKUP_RETENTION_*`).
- **Verificación**: cada backup es validado con `pg_restore --list` antes de declarar OK.

### 7.2 Backup manual

```bash
# Backup local.
bash infra/scripts/backup-postgres.sh

# Backup local + upload a S3.
bash infra/scripts/backup-postgres.sh --upload-s3

# En Windows.
.\infra\scripts\backup-postgres.ps1 -UploadS3
```

### 7.3 Restore

**ADVERTENCIA**: el restore SOBREESCRIBE la BD destino. Hacer backup antes de restaurar.

```bash
# 1. Listar backups disponibles.
bash infra/scripts/restore-postgres.sh --list

# 2. Restore a la BD principal (pide confirmacion).
bash infra/scripts/restore-postgres.sh /var/backups/bodegaje/bodegaje-20260715-023000.sql.gz

# 3. Restore a una BD paralela (para verificar).
bash infra/scripts/restore-postgres.sh /var/backups/bodegaje/bodegaje-20260715-023000.sql.gz --target-db bodegaje_restore_test
docker compose exec db psql -U bodegaje -d bodegaje_restore_test -c "SELECT count(*) FROM productos;"
docker compose exec db dropdb -U bodegaje bodegaje_restore_test
```

---

## 8. Monitoreo

### 8.1 Healthcheck

```bash
# Liveness: ¿el proceso responde?
curl -i http://localhost/api/v1/health/live
# Esperado: 200 con {"status":"ok"}.

# Readiness: ¿BD, Redis, worker OK?
curl -i http://localhost/api/v1/health/ready
# Esperado: 200 con components.{db,redis,worker}.status="ok".
# Si 503, ver sección 6 (Incidentes).
```

### 8.2 Métricas Prometheus

```bash
# Ver métricas raw.
curl -s http://localhost/metrics | head -50

# Métricas custom del negocio (prefijo bodegaje_).
curl -s http://localhost/metrics | grep "^bodegaje_"
```

**Métricas clave a alertar**:
| Métrica | Umbral | Significado |
|---|---|---|
| `bodegaje_email_outbox_pending > 100` | 5 min | Emails no se envian |
| `rate(bodegaje_email_failed_total{error_type="permanent"}[5m]) > 0.1` | - | SMTP tiene problemas |
| `histogram_quantile(0.95, http_request_duration_seconds) > 1.0` | 10 min | API lenta |
| `rate(http_requests_total{status="5xx"}[5m]) / rate(http_requests_total[5m]) > 0.01` | 5 min | Error rate > 1% |

### 8.3 Logs

```bash
# Logs en vivo de un servicio.
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs -f api

# Filtrar por correlation_id (trazabilidad end-to-end).
docker compose logs api | grep "abc-123-def-456"

# Filtrar por nivel de error.
docker compose logs api | grep '"level":"error"'

# Filtrar por evento.
docker compose logs api | grep '"event":"solicitud.created"'
```

Los logs son JSON (en production), una línea por evento, parseable por `jq`:
```bash
docker compose logs api | grep '"event":"solicitud.created"' | jq .
```

### 8.4 Sentry

Si `SENTRY_DSN` esta configurado, los errores no manejados se envian automaticamente a Sentry. En Sentry:
- **Issues** → filtrar por `environment:production` para ver solo errores de prod.
- **Performance** → traces con latencia p50/p95/p99 por endpoint.
- **Alerts** → configurar alerta para "issue seen > 100 times in 1 hour".

---

## 9. Secretos

### 9.1 Dónde se guardan

| Entorno | Ubicación | Quién accede |
|---|---|---|
| dev | `.env.development` en repo local | Devs |
| staging | `.env.staging` en servidor de staging | Devs + QA |
| production | Vault (AWS Secrets Manager / Vault) + `.env.production` en servidor (chmod 600) | DevOps |

### 9.2 Cómo rotar

```bash
# 1. Generar nuevos secretos.
python infra/scripts/generate-secrets.py --print-only

# 2. Actualizar vault (ejemplo AWS Secrets Manager).
aws secretsmanager update-secret --secret-id bodega/production --secret-string "$(cat .env.production.new)"

# 3. En el servidor, recargar el .env y restart.
scp .env.production.new deploy@bodega.example.com:/opt/bodega/.env.production
ssh deploy@bodega.example.com "cd /opt/bodega && docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml restart api worker"

# 4. Verificar que la app arranca con los secretos nuevos.
curl -i http://localhost/api/v1/health

# 5. Invalidar el secreto anterior (rotacion completa).
#    - JWT_SECRET rotado: invalida todas las sesiones existentes (usuarios re-login).
#    - SECRET_KEY rotado: invalida todos los approval tokens OC pendientes.
#    - POSTGRES_PASSWORD rotado: requiere actualizar el comando del `db` service
#      y recrear el container (datos no afectados si la BD ya esta inicializada).
```

### 9.3 Frecuencia recomendada

| Secreto | Frecuencia de rotacion | Justificacion |
|---|---|---|
| JWT_SECRET | Cada 90 días | Limita ventana si se filtra |
| SECRET_KEY | Cada 180 días | Menos expuesto (solo HMAC OC) |
| POSTGRES_PASSWORD | Cada 365 días | Rotación disruptiva |
| SMTP_PASSWORD | Cada 365 días o al离开 empleado | Política corporativa |
| SENTRY_DSN | Cuando se quiera | No es secreto real, solo el project key |

---

## 10. Runbook de migración de Fase 11+ (placeholder)

> Esta sección se actualizará cuando arranque Fase 11. Reservada para futuros procedimientos (ej. migrar a Kubernetes, multi-region, blue-green deploys).

**Próximos runbooks a crear**:
- [ ] Blue-green deploy con Nginx upstream switch.
- [ ] Migración a Kubernetes (EKS/GKE).
- [ ] Multi-region con read replicas.
- [ ] Disaster recovery con failover automático.

---

## 11. Referencias

- [Fase 10 — Hardening de Producción](../fases/fase-10-hardening-produccion.md)
- [Fase 9 — Observabilidad](../fases/fase-9-observabilidad.md)
- [ADR-0005 — Token de aprobación OC](../adr/adr-0005-token-approval-oc.md)
- [ADR-0004 — SMTP async](../adr/adr-0004-smtp-async-architecture.md)
- [Informe final 10 fases](../INFORME_FINAL_10_FASES.md)
- [Nginx production config](../../infra/docker/nginx/conf.d/production.conf)
- [Docker compose production](../../infra/docker/compose.production.yml)
- [Pre-deploy check script](../../infra/scripts/pre-deploy-check.sh)
- [Backup script](../../infra/scripts/backup-postgres.sh)
- [Restore script](../../infra/scripts/restore-postgres.sh)
- [Generate secrets](../../infra/scripts/generate-secrets.py)
