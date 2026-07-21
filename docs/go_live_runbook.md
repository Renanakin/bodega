# Go-Live Runbook - Bodegaje

> Procedimiento operativo para el go-live a produccion de Bodegaje.
>
> Este runbook esta basado en el roadmap `docs/roadmap-hardening-pre-produccion.md`
> (fases 0-4 cerradas) y la suite de tests 271/272 verde.

## Indice

1. [Pre-condiciones](#1-pre-condiciones)
2. [Pre-deploy check](#2-pre-deploy-check)
3. [Backup pre-deploy](#3-backup-pre-deploy)
4. [Deploy a produccion](#4-deploy-a-produccion)
5. [Smoke post-deploy](#5-smoke-post-deploy)
6. [Monitoreo 24h](#6-monitoreo-24h)
7. [Rollback](#7-rollback)
8. [Post-mortem a 72h](#8-post-mortem-a-72h)
9. [Checklist final](#9-checklist-final)

---

## 1. Pre-condiciones

Antes de empezar, el operador debe tener:

- [ ] Docker Desktop o Linux con Docker Engine >= 24.
- [ ] Acceso SSH al servidor de produccion (si aplica).
- [ ] `git`, `python3` (con venv), `bash`, `curl` en PATH.
- [ ] Branch con los cambios mergeado a `main`.
- [ ] `.env.production` generado (ver seccion 3.1).
- [ ] Bucket S3 configurado (si se usa `--upload-s3`).

Variables de entorno requeridas (en `.env.production`):

```bash
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
JWT_SECRET=<32+ chars random>
SECRET_KEY=<32+ chars random, DISTINTO de JWT_SECRET>
POSTGRES_PASSWORD=<32+ chars random>
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USERNAME=<SES user>
SMTP_PASSWORD=<SES password>
SENTRY_DSN=https://<key>@sentry.io/<project>
```

Generar secretos con: `python infra/scripts/generate-secrets.py`.

---

## 2. Pre-deploy check

Ejecutar **antes de cualquier deploy**:

```bash
cd /path/to/bodega
bash infra/scripts/pre-deploy-check.sh production
```

El script corre 10 checks. **Todos deben pasar (OK)** antes de continuar:

| # | Check | Que valida |
|---|---|---|
| 1 | Sin secretos en diff staged | `git diff --staged` no tiene secretos reales |
| 2 | Migraciones numeradas | Existen archivos `db/migrations/0*.sql` |
| 3 | Tests unitarios | `pytest tests/unit` pasa |
| 4 | docker compose config | `docker compose ... config -q` sin errores |
| 5 | nginx config | `nginx -t` valido via docker |
| 6 | `.env.production` existe | Archivo presente |
| 7 | JWT_SECRET >= 32 chars | No es placeholder |
| 8 | SECRET_KEY >= 32 chars | No es placeholder (solo prod) |
| 9 | Puerto 80 libre | Sin conflictos (solo prod) |
| 10 | Disco > 1GB libre | Espacio suficiente |

Si **cualquier check falla, NO hacer deploy**. Resolver y volver a correr.

El script tambien es invocado automaticamente por `start-production.ps1`
antes de levantar el stack (a menos que se pase `-SkipCheck`).

---

## 3. Backup pre-deploy

### 3.1 Generar `.env.production` (si no existe)

```bash
# Generar placeholders con secretos
python infra/scripts/generate-secrets.py --print-only > /tmp/secrets.txt
# Editar .env.production y reemplazar placeholders __*__
# (o inyectar desde Vault / AWS Secrets Manager en runtime)
```

### 3.2 Backup de la base de datos actual

```bash
# Backup automatico con rotacion
bash infra/scripts/backup-postgres.sh
# Con upload a S3 (opcional)
bash infra/scripts/backup-postgres.sh --upload-s3
```

El backup se guarda en `$BACKUP_DIR` (default `/var/backups/bodegaje`)
con nombre `bodegaje-YYYYMMDD-HHMMSS.sql.gz`. Rotacion automatica
(configurable via `BACKUP_RETENTION_DAILY`, default 7 dias).

### 3.3 Verificar que el backup es valido

```bash
# Listar backups disponibles
bash infra/scripts/restore-postgres.sh --list

# Verificar integridad del gzip
gunzip -t /var/backups/bodegaje/bodegaje-LATEST.sql.gz
```

### 3.4 Guardar el backup off-site

Aunque el script soporta `--upload-s3`, se recomienda tambien copiar
el archivo a un volumen externo:

```bash
cp /var/backups/bodegaje/bodegaje-LATEST.sql.gz /mnt/backup-pre-deploy/
```

---

## 4. Deploy a produccion

### 4.1 Levantar el stack

```bash
# Con pre-deploy check incluido (RECOMENDADO)
.\infra\scripts\start-production.ps1

# O saltar el check (NO recomendado en CI/CD)
.\infra\scripts\start-production.ps1 -SkipCheck

# Con rebuild de imagenes (si hay cambios en Dockerfile)
.\infra\scripts\start-production.ps1 -Build
```

El script valida:
- `JWT_SECRET` >= 32 chars
- `SECRET_KEY` >= 32 chars (en produccion)
- `JWT_SECRET != SECRET_KEY` (defense in depth)
- `.env.production` existe

Si pasa, ejecuta `docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up -d`.

### 4.2 Verificar que los servicios arrancaron

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml ps
```

Todos los servicios deben estar en estado `healthy` despues de 30-60 segundos:

- `nginx` (puerto 80)
- `web` (build estatico servido por nginx)
- `api` (FastAPI, interno)
- `worker` (Arq, interno)
- `db` (PostgreSQL)
- `redis` (cache + cola Arq)
- `mailpit` (solo staging)

---

## 5. Smoke post-deploy

Inmediatamente despues del deploy, validar:

### 5.1 Healthcheck

```bash
curl -i http://localhost/api/v1/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "production",
  "components": {
    "db": {"status": "ok", "backend": "postgres", "latency_ms": 5.2},
    "redis": {"status": "ok"},
    "worker": {"status": "ok"}
  },
  "timestamp": "..."
}
```

`status` puede ser `ok` o `degraded`. Si es `down` o `unhealthy`,
**abortar y rollback** (seccion 7).

### 5.2 OpenAPI

```bash
curl -i http://localhost/openapi.json | head -20
```

Debe devolver 200 con JSON valido que documente todos los endpoints.

### 5.3 Login con un usuario admin existente

```bash
curl -i -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<password>"}'
```

Debe devolver 200 con un `access_token`.

### 5.4 Endpoint autenticado

```bash
TOKEN="<token from login>"
curl -i http://localhost/api/v1/warehouses -H "Authorization: Bearer $TOKEN"
```

Debe devolver 200 con la lista de bodegas.

### 5.5 Flujo end-to-end de solicitud

Si los checks anteriores pasan, ejecutar el flujo completo desde la UI:

1. Login en la webapp.
2. Crear una bodega + producto de prueba (si no existen).
3. Crear una solicitud de Aux -> Principal.
4. Aprobar.
5. Despachar.
6. Recibir.
7. Verificar que el stock se movio correctamente.

Si **cualquier paso falla**, abrir incidente antes de continuar.

---

## 6. Monitoreo 24h

Las primeras 24 horas son criticas. Mantener `LOG_LEVEL=INFO` (o `DEBUG`
si hay problemas).

### 6.1 Herramientas

- **Prometheus metrics**: `http://localhost/metrics` (scrape por Prometheus).
- **Sentry**: revisar el dashboard cada 2-4 horas.
- **Logs estructurados**: `docker compose logs -f api worker`.

### 6.2 Metricas a monitorear

| Metrica | Alerta | Comando |
|---|---|---|
| Request rate | caida > 50% en 5 min | `curl -s localhost/metrics \| grep http_requests_total` |
| Latencia p95 | > 1s sostenido | Grafana dashboard |
| Error rate 5xx | > 1% | Sentry / logs |
| Health degraded | continuo > 5 min | `curl localhost/api/v1/health` |
| Disco | > 90% uso | `df -h /` |

### 6.3 Comandos utiles

```bash
# Ver logs en vivo
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml logs -f --tail=100 api worker

# Buscar errores 5xx
docker compose logs api | grep -E '" 5[0-9]{2} '

# Verificar cola de emails pendientes
docker compose exec api python -c "
import asyncio
from app.db.session import get_session_factory
from sqlalchemy import select, text
from app.db.models.ordenes_compra import EmailOutbox
async def run():
    factory = get_session_factory()
    async with factory() as s:
        result = await s.execute(text('SELECT status, count(*) FROM email_outbox GROUP BY status'))
        for row in result:
            print(row)
asyncio.run(run())
"

# Estadisticas de DB
docker compose exec db psql -U bodegaje bodegaje -c "
  SELECT schemaname, tablename, n_live_tup
  FROM pg_stat_user_tables
  ORDER BY n_live_tup DESC
  LIMIT 10;
"
```

---

## 7. Rollback

Si algo sale mal, rollback inmediato (no parchar en caliente).

### 7.1 Rollback del codigo

```bash
# Opcion A: revertir al commit anterior
cd /path/to/bodega
git checkout HEAD~1
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up -d --build

# Opcion B: cherry-pickear un fix rapido
# (solo si el fix es obvio y se valida en menos de 10 min)
git revert HEAD
docker compose ... up -d --build
```

### 7.2 Rollback de la base de datos

```bash
# Listar backups disponibles
bash infra/scripts/restore-postgres.sh --list

# Restaurar el backup pre-deploy
bash infra/scripts/restore-postgres.sh /var/backups/bodegaje/bodegaje-PRE-DEPLOY.sql.gz
```

El restore pide confirmacion interactiva y SOBREESCRIBE la BD destino.
Si la BD destino tiene conexiones activas, el restore falla con
"DROP DATABASE failed". Cerrar conexiones primero:

```bash
docker compose -f ... -f compose.production.yml stop api worker
bash infra/scripts/restore-postgres.sh /var/backups/bodegaje/bodegaje-PRE-DEPLOY.sql.gz
docker compose -f ... -f compose.production.yml start api worker
```

### 7.3 Validar rollback

```bash
curl http://localhost/api/v1/health
# Verificar que el estado es consistente con el backup restaurado
```

---

## 8. Post-mortem a 72h

A las 72 horas del go-live, hacer un post-mortem aunque todo haya ido bien.

### 8.1 Template

```markdown
## Post-mortem - Bodegaje Go-Live [FECHA]

### Resumen
- **Deploy ejecutado**: [FECHA HORA]
- **Operador**: [NOMBRE]
- **Duracion del deploy**: [minutos]
- **Estado a 72h**: [OK / issues menores / incidentes]

### Metricas observadas
- Request rate promedio: [req/s]
- Latencia p95: [ms]
- Error rate 5xx: [%]
- Healthcheck status: [ok / degraded]
- Usuarios activos: [count]

### Incidentes
1. [HORA] - [descripcion corta] - [resolucion]
2. ...

### Lecciones aprendidas
1. ...

### Acciones de seguimiento
1. [ ] ...
```

### 8.2 Quien asiste

- Operador que hizo el deploy
- Tech lead
- Cualquier dev que haya resuelto incidentes en las 24h

---

## 9. Checklist final

### Pre-deploy (T-24h)

- [ ] Branch mergeado a `main`.
- [ ] PRs revisados y CI verde.
- [ ] `.env.production` generado con secretos validos.
- [ ] Bucket S3 configurado (si se usa).
- [ ] DNS apunta al servidor de produccion.
- [ ] Equipo disponible para las 24h post-deploy.

### Deploy (T-0)

- [ ] Pre-deploy check pasa (10/10 OK).
- [ ] Backup pre-deploy completo y validado.
- [ ] `start-production.ps1` ejecutado sin errores.
- [ ] Servicios `healthy` en `docker compose ps`.
- [ ] Healthcheck responde 200.
- [ ] OpenAPI responde 200.
- [ ] Login funciona.
- [ ] Flujo end-to-end de solicitud validado.

### Post-deploy (T+0 a T+24h)

- [ ] `LOG_LEVEL=INFO` (no DEBUG).
- [ ] Sentry dashboard abierto.
- [ ] Prometheus scrape configurado.
- [ ] `docker compose logs -f` activo en una terminal.
- [ ] Equipo de guardia comunicado.

### Post-deploy (T+24h a T+72h)

- [ ] Volver `LOG_LEVEL=WARNING` (configurado en `.env.production.example`).
- [ ] Post-mortem escrito y revisado.
- [ ] Acciones de seguimiento asignadas.

### Rollback (si necesario)

- [ ] Backup pre-deploy disponible y verificado.
- [ ] Procedimiento de restore documentado.
- [ ] Comando de revert del codigo probado.
