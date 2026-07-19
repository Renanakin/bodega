# Runbook de Operacion

> **Para SRE / DevOps**: este documento describe como operar el sistema en produccion.

## Indice

1. [Despliegue](#1-despliegue)
2. [Healthcheck y monitoreo](#2-healthcheck-y-monitoreo)
3. [Operaciones comunes](#3-operaciones-comunes)
4. [Troubleshooting](#4-troubleshooting)
5. [Backups y restore](#5-backups-y-restore)
6. [Rollback](#6-rollback)
7. [Oncall](#7-oncall)

---

## 1. Despliegue

### 1.1 Ambientes

| Ambiente | URL | Branch |
|---|---|---|
| Local | `http://localhost` | feature branches |
| Staging | `https://staging.bodega.example` | `main` |
| Production | `https://app.bodega.example` | tag `v*` |

### 1.2 Desplegar a staging

Automatico en push a `main`:

```bash
git push origin main
# CI: lint + test + build + deploy
```

Verificar:
- https://staging.bodega.example responde 200
- `/api/v1/health` retorna `{db: "ok", redis: "ok"}`

### 1.3 Desplegar a produccion

Manual (requiere aprobacion en GitHub Actions):

```bash
git tag v0.2.0
git push origin v0.2.0
# CI: lint + test + build + deploy (con approval manual)
```

## 2. Healthcheck y monitoreo

### 2.1 Healthcheck

```bash
curl https://app.bodega.example/api/v1/health
```

Respuesta esperada:
```json
{
  "status": "ok",
  "checks": {
    "database": {"status": "ok", "backend": "postgres"},
    "redis": {"status": "ok"}
  }
}
```

Si retorna 503: algun servicio critico esta caido.

### 2.2 Metricas Prometheus

```
GET /metrics
```

Metricas custom clave:
- `solicitudes_creadas_total`
- `solicitudes_despachadas_total`
- `ordenes_compra_enviadas_total`
- `email_outbox_pending`
- `replenishment_evaluator_last_run_timestamp`

### 2.3 Logs estructurados

Todos los logs en JSON con campos:
- `request_id`
- `user_id`
- `entity_id`
- `event` (e.g. `movement.applied`, `solicitud.created`)

Filtrar por nivel: `LOG_LEVEL=INFO` (staging) / `WARNING` (prod).

## 3. Operaciones comunes

### 3.1 Re-ejecutar migraciones Alembic

```bash
# En el contenedor de la API
alembic upgrade head

# Rollback una migracion
alembic downgrade -1

# Ver historial
alembic history
```

### 3.2 Resetear la BD de demo

```bash
python -m app.db.demo
```

### 3.3 Iniciar el worker de emails manualmente

```bash
python -m app.modules.notifications.worker
```

Logs en stdout; SIGINT para parar gracefully.

### 3.4 Disparar replenishment manualmente

```python
from app.db.session import get_session_factory
from app.modules.solicitudes.replenishment import ReplenishmentEvaluator
import asyncio

async def main():
    factory = get_session_factory()
    async with factory() as session:
        e = ReplenishmentEvaluator(session)
        report = await e.evaluate_all()
        print(report)

asyncio.run(main())
```

## 4. Troubleshooting

### Error: "connection refused" a Postgres
- Verificar que `docker compose ps db` muestra "running".
- Verificar `DATABASE_URL` en `.env.production`.
- Probar `psql $DATABASE_URL` para validar conectividad.

### Error: "ModuleNotFoundError: No module named 'app.X'"
- La estructura del proyecto cambio. Ver `docs/architecture/30-second-rule.md`.

### Error: "alembic.util.exc.CommandError: Can't locate revision"
- La BD esta en un estado inconsistente. Conectar a la BD y revisar tabla `alembic_version`.

### Emails no salen
1. Verificar `/api/v1/notificaciones/outbox?status=pending`.
2. Si hay `status=failed`, leer `last_error`.
3. Verificar credenciales SMTP en `.env.production`.
4. Verificar que el worker esta corriendo.

## 5. Backups y restore

### 5.1 Backup diario (Postgres)

Cron a las 03:00 AM:
```bash
pg_dump -Fc bodega_prod > /backups/bodega-$(date +\%Y\%m\%d).dump
```

Upload a S3:
```bash
aws s3 cp /backups/bodega-*.dump s3://bodega-backups/
```

### 5.2 Restore

```bash
# Parar la API
docker compose stop api worker

# Drop la BD actual (CUIDADO)
dropdb bodega_prod

# Crear BD vacia
createdb bodega_prod

# Restore
pg_restore -d bodega_prod /backups/bodega-20260714.dump

# Re-aplicar migraciones (por si acaso)
alembic upgrade head

# Reiniciar
docker compose start api worker
```

## 6. Rollback

### 6.1 Rollback de aplicacion (sin cambios de schema)

```bash
git revert HEAD
git push origin main
# CI redeploy automatico
```

### 6.2 Rollback de migracion Alembic

```bash
alembic downgrade -1
# O especificar revision
alembic downgrade 0009_users_supervisor_link
```

### 6.3 Rollback de emergencia (BD corrupta)

1. Restaurar desde backup (seccion 5.2).
2. NO usar la BD hasta verificar consistencia.
3. Contactar al equipo de desarrollo.

## 7. Oncall

### 7.1 Alertas configuradas (Prometheus)

| Alerta | Condicion | Severidad |
|---|---|---|
| `APIErrorRate5xx` | > 1% errores 5xx en 5 min | warning |
| `EmailOutboxPending` | > 50 emails pending 10 min | critical |
| `ReplenishmentEvaluatorLastRun` | sin ejecucion en 10 min | critical |
| `DatabaseConnectionFailing` | > 5 fallos consecutivos | critical |

### 7.2 Respuesta a alertas

**EmailOutboxPending CRITICAL:**
1. SSH al servidor de staging/prod.
2. `docker compose logs worker --tail 100`.
3. Verificar credenciales SMTP.
4. Si son correctas, reenviar manualmente con `python -c "..."`.

**APIErrorRate5xx WARNING:**
1. Verificar logs: `docker compose logs api --tail 200 | jq`.
2. Si es despues de un deploy, considerar rollback.
3. Si es DB lock contention, ver metricas de Postgres.

**ReplenishmentEvaluatorLastRun CRITICAL:**
1. Verificar que el cron esta configurado: `crontab -l | grep replenishment`.
2. Si no esta, agregar: `*/5 * * * * cd /app && python -m app.worker.jobs.replenishment`.
3. Si esta pero no corre, ver logs del cron: `journalctl -u cron`.

### 7.3 Escalamiento

| Severidad | Accion | SLA |
|---|---|---|
| Critical | Resolver + comunicar al equipo | < 1 hora |
| Warning | Investigar y resolver en sprint | < 1 semana |
| Info | Anotar para revision | Backlog |

### 7.4 Contactos

| Rol | Persona | Contacto |
|---|---|---|
| Backend Lead | – | backend@bodega.example |
| DevOps | – | devops@bodega.example |
| Product Owner | – | po@bodega.example |
| VP Engineering | – | vp@bodega.example |
