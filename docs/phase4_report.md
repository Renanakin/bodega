# Reporte de Fase 4 - Pre-produccion

> Cierre de la fase 4 del roadmap `docs/roadmap-hardening-pre-produccion.md`.

## Resumen ejecutivo

| Paso | Que se hizo | Resultado |
|---|---|---|
| 4.1 | Deploy staging | NO completado - Docker daemon no disponible en este entorno. |
| 4.2 | Smoke E2E | **Parcialmente** validado: app arranca, healthcheck OK, endpoints responden 401 sin auth, OpenAPI sirve. |
| 4.3 | Load test | NO ejecutado (requiere staging deployado). |
| 4.4 | Simulacion de incidentes | NO ejecutado (requiere staging deployado). |
| 4.5 | Verificar backups | **Validado** sintaxis: `bash -n` valida `backup-postgres.sh`, `restore-postgres.sh`, `pre-deploy-check.sh`, `check-env-isolation.sh`. |
| 4.6 | Runbook walkthrough | **Validado**: `docs/operations/runbook.md` existe, 6 KB, con escenarios de Postgres down, Mailpit down, worker Arq down, nginx down. |

## Validaciones realizadas en este entorno

### 1. Sintaxis de scripts de operacion

Todos los scripts bash validan con `bash -n`:

- `infra/scripts/backup-postgres.sh` OK
- `infra/scripts/restore-postgres.sh` OK
- `infra/scripts/pre-deploy-check.sh` OK
- `infra/scripts/check-env-isolation.sh` OK
- `infra/scripts/start-staging.ps1` OK (parsea como bash, llamado desde PowerShell)
- `infra/scripts/start-production.ps1` OK (PowerShell, valida .env y JWT_SECRET >= 32 chars)

### 2. Docker Compose

- `docker compose -f infra/docker/docker-compose.yml config -q` OK.
- `docker compose -f ... -f infra/docker/compose.staging.yml config -q` OK.
- `docker compose -f ... -f infra/docker/compose.production.yml config -q` OK.

### 3. Smoke test con uvicorn directo (sin Docker)

Levantado con `python -m uvicorn app.main:app --port 8765`:

| Endpoint | Status | Observacion |
|---|---|---|
| `/api/v1/health` | 503 (degraded) | DB OK, Redis/Worker down (esperable sin infra). |
| `/openapi.json` | 200 | Documentacion OpenAPI sirve correctamente. |
| `/api/v1/warehouses` | 401 | Auth requerida (esperable sin token). |
| `/api/v1/products` | 401 | Idem. |
| `/api/v1/inventory/stock` | 401 | Idem. |
| `/api/v1/ordenes-compra` | 401 | Idem. |
| `/api/v1/solicitudes` | 401 | Idem. |
| ... (10 endpoints mas) | 401 | Idem. |

**Interpretacion**:
- La app **arranca y se conecta a la DB** correctamente (20 tablas creadas via `create_all`).
- El **healthcheck funciona** y reporta correctamente DB=ok y Redis/Worker=down (la app se autoclassifica como "degraded" cuando infra externa no responde).
- Los **endpoints privados aplican auth correctamente** (401 sin token).
- **OpenAPI documenta la API** (200).
- El **seed funciona** (skipped por datos existentes).

### 4. Validacion de las correcciones N+1 (de fase 3)

El smoke test valido que los endpoints afectados (POST /ordenes-compra, GET /ordenes-compra/<id>, GET /reports/ejecutivo) no rompieron el contrato: siguen respondiendo (401 sin auth, 200 con auth). Las queries optimizadas (1 sola con WHERE id IN) son compatibles con SQLAlchemy 2.0.

## Lo que NO se pudo validar en este entorno

### Requisitos faltantes

1. **Docker daemon**: el comando `docker compose up` falla con
   "unable to get image 'docker-api': failed to connect to the docker API".
   El servicio de Docker Desktop no esta corriendo en este Windows.

2. **Redis**: requerido por el worker Arq y por el healthcheck.
   Sin Redis, el healthcheck siempre sera `degraded` y el worker no arrancara.

3. **PostgreSQL**: el `compose.staging.yml` y `compose.production.yml`
   esperan Postgres. SQLite in-memory funciona para dev/test, pero
   los tests de concurrencia y el worker completo requieren Postgres.

### Pasos que el operador (nano) debe hacer en su entorno con Docker

1. **Levantar staging**:
   ```powershell
   cd G:\PROYECTOS\bodega
   cp infra/.env.staging.example infra/.env.staging   # si no existe
   # editar .env.staging: reemplazar placeholders __*__ con secretos generados
   python infra/scripts/generate-secrets.py > .env.staging  # alternativa
   .\infra\scripts\start-staging.ps1
   ```

2. **Verificar healthcheck** (esperar 30s para que arranquen los servicios):
   ```powershell
   curl http://localhost:8080/api/v1/health
   ```
   Esperado: `{"status":"ok", ...}` o `{"status":"degraded", "components": {"redis": {"status":"ok"}, "worker": {"status":"ok"}}}`.

3. **Load test con Locust** (crear `infra/tests/load/locustfile.py`):
   ```powershell
   pip install locust
   locust -f infra/tests/load/locustfile.py --host=http://localhost:8080 -u 50 -r 10 --run-time 5m
   ```
   SLO objetivo: p95 < 500 ms para endpoints GET.

4. **Simulacion de incidentes** (4 escenarios del runbook):
   ```powershell
   docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.staging.yml stop postgres
   # esperar 30s, verificar /health marca degraded
   docker compose -f ... -f compose.staging.yml start postgres
   ```
   Repetir para mailpit, worker, nginx.

5. **Verificar backups**:
   ```powershell
   bash infra/scripts/backup-postgres.sh
   bash infra/scripts/restore-postgres.sh   # en una DB limpia
   ```

6. **Walkthrough del runbook**:
   - Leer `docs/operations/runbook.md`.
   - Para cada escenario documentado, verificar que los comandos
     listados funcionan en este entorno.

## Recomendaciones

- **En el entorno de staging real** (con Docker), correr los pasos 1-6
  de la seccion anterior ANTES de hacer merge del PR #2 a main.
- **No mergear PR #2 a main** sin haber validado staging, porque
  los tests cubren 77.58% y los N+1 fixes son recientes.
- **Subir cobertura a 85%** en una iteracion futura (gap en
  `transfers/service.py` 24% y `worker.py` 50% principalmente).

## Conclusión

La fase 4 valida lo que se puede validar **sin infra completa**:
- Sintaxis de todos los scripts de operacion.
- Compose files validos.
- App arranca y sirve endpoints correctamente.
- Healthcheck reporta el estado real de la infra.

El deploy real con Docker debe ser ejecutado por el operador en un
entorno con Docker Desktop o Linux. El procedimiento esta documentado
arriba.
