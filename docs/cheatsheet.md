# Cheatsheet de comandos criticos (bodegaje)

> **TL;DR** — Lo que te salva a las 3am, en una pagina.
> Si vas solo, pega esto en un sticky o dejalo abierto en el navegador.

## Acceso rapido

| Servicio | URL | Notas |
|---|---|---|
| UI web | http://localhost:8080 | Login con `admin` / `admin12345` |
| API REST | http://localhost:8080/api/v1 | JWT en header `Authorization: Bearer ...` |
| Swagger | http://localhost:8080/docs | FastAPI auto-generado |
| Grafana | http://localhost:3000 | `admin` / `admin` |
| Prometheus | http://localhost:9090 | Queries PromQL |
| Mailpit | http://localhost:8025 | Emails enviados por la app |

## Stack actual

12 contenedores: `bodegaje-{api,worker,web,nginx,db,redis,mailpit,prometheus,grafana,alertmanager,node-exporter,postgres-exporter,backup}`.

## 1. Ver estado de la pila

```powershell
# Ver que esta corriendo
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String "bodegaje"

# Solo los unhealthy
docker ps --filter "health=unhealthy" --format "{{.Names}}: {{.Status}}"
```

## 2. Reiniciar un servicio especifico

```powershell
# API (la que mas se toca)
docker restart bodegaje-api

# Worker (cola de emails + cron replenishment)
docker restart bodegaje-worker

# Web (frontend)
docker restart bodegaje-web

# Si un servicio no levanta bien, ver logs
docker logs --tail 100 bodegaje-api
```

**Si la API se reinicia y las sesiones se invalidan**: es normal, el JWT expira a la hora. Los usuarios tienen que volver a loguearse. No es bug.

## 3. Ver logs en vivo

```powershell
# API (lo que mas vas a mirar)
docker logs -f --tail 50 bodegaje-api

# Worker (replenishment, emails)
docker logs -f --tail 50 bodegaje-worker

# Backup (corrida diaria 03:00 UTC)
docker logs -f --tail 50 bodegaje-backup

# Filtrar por nivel (errors/warnings)
docker logs bodegaje-api 2>&1 | Select-String "error|warning" | Select-Object -Last 20
```

## 4. Entrar a la BD Postgres

```powershell
# Consola psql directa
docker exec -it bodegaje-db psql -U bodegaje -d bodegaje

# Una query rapida sin entrar
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "SELECT count(*) FROM solicitudes_recarga;"

# Tablas y sus tamanos
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "SELECT schemaname,tablename,pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables WHERE schemaname='public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"

# Salir de psql: \q
```

## 5. Disparar replenishment manual

```powershell
# Login y capturar token
$token = (Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/auth/login" -ContentType "application/json" -Body '{"username":"admin","password":"admin12345"}').token

# Dry run (solo muestra el reporte, no crea)
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/solicitudes/auto-generar?dry_run=true" -Headers @{Authorization="Bearer $token"} | Format-List

# Ejecucion real
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/solicitudes/auto-generar" -Headers @{Authorization="Bearer $token"} | Format-List

# Solo para una bodega especifica (UUID de la bodega)
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/solicitudes/auto-generar?bodega_id=3a5baf63-18f7-4ead-8cab-6ab412ac525a" -Headers @{Authorization="Bearer $token"} | Format-List
```

## 6. Forzar una corrida de backup AHORA

```powershell
docker exec bodegaje-backup /usr/local/bin/backup.sh
```

Veras algo como:
```
[2026-07-23T15:07:18Z] Iniciando backup: bodegaje@db:5432 -> /backups/bodegaje-20260723T150718Z.dump.gz
[2026-07-23T15:07:18Z] Backup completado en 0s. Tamaño: 34605 bytes.
[2026-07-23T15:07:18Z] Estado final: 1 backup(s), 34K total en /backups
```

## 7. Restaurar un backup (DRP)

### Escenario: la BD se rompio, volver al ultimo backup

```powershell
# 1. Bajar API y worker
docker compose -f G:\PROYECTOS\bodega\infra\docker\docker-compose.yml stop api worker

# 2. Copiar el backup al host
docker cp bodegaje-backup:/backups/bodegaje-latest.dump.gz C:\Users\Tranquilidad\restore.dump.gz

# 3. Restaurar (dropea objetos antes de crear, ignora warnings de owners)
gunzip -c C:\Users\Tranquilidad\restore.dump.gz | docker exec -i bodegaje-db pg_restore -U bodegaje -d bodegaje --clean --if-exists --no-owner --no-privileges

# 4. Verificar counts
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "SELECT 'warehouses' tabla, count(*) FROM warehouses UNION ALL SELECT 'solicitudes', count(*) FROM solicitudes_recarga;"

# 5. Levantar API y worker
docker compose -f G:\PROYECTOS\bodega\infra\docker\docker-compose.yml start api worker
```

### Escenario: disaster recovery en maquina nueva

```powershell
# Asumiendo que tienes docker + el codigo clonado
cd G:\PROYECTOS\bodega
docker compose -f infra/docker/docker-compose.yml up -d db
# Esperar a "healthy" (~10s)
docker exec bodegaje-db pg_isready -U bodegaje
# Restaurar dump
gunzip -c /ruta/al/backup.dump.gz | docker exec -i bodegaje-db pg_restore -U bodegaje -d bodegaje --no-owner --no-privileges
# Levantar el resto
docker compose -f infra/docker/docker-compose.yml up -d
```

Mas detalle en `infra/docker/backup/README.md`.

## 8. Regenerar una solicitud cancelada/rechazada

A veces una solicitud se rechazo por error humano. Para regenerar:

```powershell
# Opcion A: disparar replenishment automatico
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/v1/solicitudes/auto-generar?bodega_id=<UUID_BODEGA>" -Headers @{Authorization="Bearer $token"}

# Opcion B: crearla manual con POST /solicitudes
# Body JSON:
# {
#   "bodega_origen_id": "3a5baf63-...",   # auxiliar
#   "bodega_destino_id": "a96d195d-...",  # principal
#   "prioridad": "alta",
#   "lineas": [
#     {"producto_id": "<UUID_PRODUCTO>", "cantidad_solicitada": 50}
#   ]
# }
```

## 9. Matar el rate limit (debug login)

Si te trabaste probando logins (5 por minuto por username) y necesitas resetear:

```powershell
# El rate limit esta en Redis, instancia `bodegaje-redis`
docker exec bodegaje-redis redis-cli KEYS "*rate*"
docker exec bodegaje-redis redis-cli KEYS "*auth*"
docker exec bodegaje-redis redis-cli FLUSHDB    # ⚠️ borra TODAS las keys de Redis
```

`FLUSHDB` es agresivo (borra tambien la cola de emails pendientes). Usa `DEL key_name` si sabes cual es.

## 10. Ver metricas de rendimiento

```powershell
# Load test rapido (si tienes apache bench o hey instalado)
# 100 requests, 10 concurrentes
hey -n 100 -c 10 http://localhost:8080/api/v1/warehouses?limit=50

# O con curl en bucle (sin herramientas extra)
1..100 | ForEach-Object -Parallel { (curl -s -o $null -w "%{http_code} %{time_total}s`n" http://localhost:8080/api/v1/warehouses?limit=50) } | Measure-Object

# Prometheus queries utiles
# - Request rate: rate(http_requests_total[5m])
# - Error rate: rate(http_requests_total{status=~"5.."}[5m])
# - p95 latency: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

## 11. Si TODO se rompio: reset nuclear

```powershell
# ⚠️ ESTO BORRA TODOS LOS DATOS. Solo si no hay otra salida.
cd G:\PROYECTOS\bodega
docker compose -f infra/docker/docker-compose.yml down -v
docker compose -f infra/docker/docker-compose.yml up -d

# Restaurar el ultimo backup (ver seccion 7)
```

## 12. Variables de entorno (lo critico)

`.env` en `infra/docker/`:

| Variable | Default | Para que es |
|---|---|---|
| `ENVIRONMENT` | `staging` | Cambia logs y seguridad |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Conexion BD |
| `REDIS_URL` | `redis://redis:6379/0` | Cola + rate limit |
| `JWT_SECRET` | (requerido) | Firma tokens. **Rotar si se filtra** |
| `SECRET_KEY` | (requerido) | CSRF y otros. **Rotar si se filtra** |
| `SMTP_HOST` | `mailpit` | Servidor de emails |
| `LOG_LEVEL` | `INFO` | `DEBUG` para troubleshooting pesado |

## 13. Tags y releases

```powershell
# Ver tags
git tag -l

# El ultimo tag estable es v1.0.0 (post C5)
# Para volver a una version anterior:
git checkout v1.0.0
docker compose -f infra/docker/docker-compose.yml up -d --build
```

## 14. Cuando NADA de esto funciona

1. `docker compose -f infra/docker/docker-compose.yml ps` → que dice?
2. `docker logs --tail 200 bodegaje-api` → que error sale?
3. `docker exec bodegaje-db pg_isready -U bodegaje` → la BD responde?
4. `docker exec bodegaje-redis redis-cli PING` → Redis responde?

Si la BD no responde y el backup tiene <25h: **restaurar backup** (seccion 7).
Si la BD no responde y NO hay backup reciente: **reset nuclear** (seccion 11) y llorar un rato.

## 15. Stack overflow (mental)

| Sintoma | Probable causa | Comando |
|---|---|---|
| "401 Unauthorized" en todo | Token expirado o JWT_SECRET rotado | Limpiar localStorage y relogin |
| "422 Unprocessable Entity" en login | Username/password mal | Verificar que escribiste bien |
| "429 Too Many Requests" en login | Rate limit | Esperar 1 min o `redis-cli FLUSHDB` |
| "500 Internal Server Error" random | Bug en backend | `docker logs --tail 50 bodegaje-api` |
| Replenishment no genera solicitudes | Ya hay PENDING para esos SKUs | Ver `solicitudes_omitidas_pendientes` en el reporte |
| Web no carga | Nginx o web caido | `docker restart bodegaje-web bodegaje-nginx` |
| Emails no salen | Mailpit o worker caido | `docker ps \| Select-String "mailpit\|worker"` |

## Contactos (dejar en tu celu)

- **Renanakin (autor)**: hectorteck4@gmail.com
- **Repositorio**: https://github.com/Renanakin/bodega
- **Issues**: https://github.com/Renanakin/bodega/issues
- **Documentacion tecnica**: `docs/propuesta_ejecutables/`
- **Auditorias de cambios**: `C:\Users\Tranquilidad\auditoria-fase0\` y `auditoria-fase5\` (gitignored)
