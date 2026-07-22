# Runbook de Staging (C4.8)

**Fecha:** 2026-07-22
**Audiencia:** operador que levanta el ambiente, dev que lo prueba

---

## TL;DR

```bash
# 1. Levantar el stack
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.staging.yml \
               up --build -d

# 2. Esperar a que este healthy (~30s)
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.staging.yml \
               ps

# 3. Sembrar datos
python infra/scripts/seed_staging.py \
    --base-url http://localhost:8080 \
    --admin-username admin --admin-password admin12345 \
    --size medium \
    --output-file staging-credentials.txt

# 4. Correr bateria E2E
python infra/scripts/run_e2e_staging.py \
    --base-url http://localhost:8080 \
    --admin-username admin --admin-password admin12345

# 5. Load test (opcional)
python infra/scripts/load_test_staging.py \
    --base-url http://localhost:8080 \
    --profile smoke

# 6. Invitar al cliente (ver staging-invitacion-cliente.md)
```

---

## 1. Pre-requisitos

### Herramientas
- Docker Desktop (>= 4.0)
- Python 3.11+
- PowerShell 7+ (o bash si estás en Linux)
- 4 GB RAM libres (Postgres + Redis + API + worker + observability)

### Variables de entorno
Debe existir `.env.staging` en la raíz del repo con:

```bash
ENVIRONMENT=staging
DATABASE_URL=postgresql+asyncpg://bodegaje:bodegaje@db:5432/bodegaje
REDIS_URL=redis://redis:6379/0
JWT_SECRET=<generar con: python -c "import secrets; print(secrets.token_urlsafe(32))">
SECRET_KEY=<distinto de JWT_SECRET>
PUBLIC_BASE_URL=http://localhost:8080
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_FROM=noreply@staging.bodega.cl
GRAFANA_ADMIN_PASSWORD=<elegir una>
```

### Secretos faltantes
```bash
# Si .env.staging no existe, copiarlo del example:
cp infra/.env.staging.example .env.staging

# Generar secretos
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(32))" \
  | Out-File -Append .env.staging
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))" \
  | Out-File -Append .env.staging
```

---

## 2. Levantar el stack

### 2.1 Stack principal (API + DB + Redis + worker + Nginx + Mailpit)

```bash
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.staging.yml \
               up --build -d
```

Esto levanta:
- `bodegaje-db` (Postgres 17, sin puerto expuesto al host)
- `bodegaje-redis` (Redis 8, sin puerto)
- `bodegaje-mailpit` (puerto 8025 → http://localhost:8025)
- `bodegaje-api` (puerto interno 8000, expuesto vía Nginx)
- `bodegaje-worker` (Arq, sin puerto)
- `bodegaje-web` (Nginx 80, expuesto vía Nginx)
- `bodegaje-nginx` (puerto 8080 → http://localhost:8080)

### 2.2 (Opcional) Stack de observabilidad

```bash
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.staging.yml \
               -f infra/docker/compose.observability.yml \
               up -d prometheus grafana alertmanager
```

Esto agrega:
- `bodegaje-prometheus` (puerto 9090 → http://localhost:9090)
- `bodegaje-grafana` (puerto 3000 → http://localhost:3000, admin/admin)
- `bodegaje-alertmanager` (puerto 9093 → http://localhost:9093)

### 2.3 Verificar que todo está healthy

```bash
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.staging.yml \
               ps
```

Esperar a que `db` diga `(healthy)`. Si la API sigue reiniciándose, ver
los logs:

```bash
docker logs bodegaje-api --tail 50
```

### 2.4 Verificar que la API responde

```bash
# Health check basico
curl -s http://localhost:8080/api/v1/health/live | jq .
# Esperado: {"status": "alive"}

# Health check completo (incluye Postgres + Redis)
curl -s http://localhost:8080/api/v1/health/ready | jq .
# Esperado: {"status": "ready", "checks": {"postgres": "ok", "redis": "ok"}}
```

---

## 3. Sembrar datos

### 3.1 Seed completo (usuarios + datos)

```bash
python infra/scripts/seed_staging.py \
    --base-url http://localhost:8080 \
    --admin-username admin \
    --admin-password admin12345 \
    --size medium \
    --output-file staging-credentials.txt
```

Esto crea:
- 1 supervisor
- 3 usuarios por rol (admin, supervisor, operador origen, operador destino)
- 1 bodega principal + (N-1) auxiliares (medium = 15 bodegas)
- 25 categorías
- 300 productos
- 20 proveedores
- Stock inicial en cada bodega
- Solicitudes en distintos estados (pending, approved, dispatched, received)

El archivo `staging-credentials.txt` contiene las passwords random.
**Guardalo seguro** — es la única vez que verás las credenciales.

### 3.2 (Opcional) Seed manual

Si querés más control, podés correr los seeds por separado:

```bash
# Solo usuarios (sin datos)
python apps/api/auditoria-fase5/seed_users_local.py

# Solo datos (necesita admin preexistente)
python apps/api/auditoria-fase5/seed_load_test_data.py \
    --base-url http://localhost:8080 \
    --username admin --password admin12345 \
    --size large
```

---

## 4. Validación pre-cliente

### 4.1 Batería E2E completa (9 módulos, 51 pasos)

```bash
python infra/scripts/run_e2e_staging.py \
    --base-url http://localhost:8080 \
    --admin-username admin --admin-password admin12345
```

Si pasan 51/51, el sistema está OK. Si falla alguno:

```bash
# Ver logs de la API
docker logs bodegaje-api --tail 100

# Ver logs del worker
docker logs bodegaje-worker --tail 50
```

### 4.2 Load test smoke

```bash
python infra/scripts/load_test_staging.py \
    --base-url http://localhost:8080 \
    --profile smoke
```

Para staging con 1 cliente, `smoke` (5 concurrentes, 30s) es suficiente.
Si querés validar más, probá `normal` (20 concurrentes, 60s).

### 4.3 Verificar observabilidad

- **Grafana:** http://localhost:3000 (admin/admin)
  - Dashboard "Bodegaje — API Overview": debería mostrar tráfico del load test.
  - Dashboard "Bodegaje — Negocio": debería mostrar las solicitudes creadas por el seed.
- **Prometheus:** http://localhost:9090
  - Targets: http://localhost:9090/targets (todos UP)
  - Alertas: http://localhost:9090/alerts

---

## 5. Invitar al cliente

### 5.1 Antes de invitar

- [ ] Batería E2E pasa 51/51
- [ ] Load test pasa con error rate < 1%
- [ ] No hay alertas activas en Prometheus
- [ ] Las credenciales están guardadas en lugar seguro
- [ ] El cliente firmó NDA (si aplica)
- [ ] Tienes el manual de usuario listo para enviar

### 5.2 Enviar invitación

Usar la plantilla: [staging-invitacion-cliente.md](staging-invitacion-cliente.md)

Personalizar:
- `[NOMBRE]`, `[USUARIO]`, `[PASSWORD]`
- `[FECHA_INICIO]`, `[FECHA_FIN]`
- `[EMAIL]`, `[CONTACTO]`

### 5.3 Monitorear durante la prueba

- Revisar Grafana cada 6h (p95, error rate, alertas)
- Responder al cliente en <2h en horario hábil
- Documentar cada feedback en
  `staging-informe-template.md` (llenar al final)

### 5.4 Al final del período

1. Llenar `staging-informe-template.md` con los datos
2. Decidir go / no-go con base en los resultados
3. Si no-go: archivar el informe, no destruir los datos hasta confirmar
4. Si go: pasar a C5 (go-live con refresh tokens + HTTPS + pen-test)

---

## 6. Limpieza

### 6.1 Reset completo (para nueva prueba)

```bash
# Detener y borrar volumenes
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.staging.yml \
               down -v

# Levantar de nuevo
docker compose -f infra/docker/docker-compose.yml \
               -f infra/docker/compose.staging.yml \
               up --build -d
```

### 6.2 Backup pre-reset

Si querés conservar los datos antes del reset:

```bash
# Backup de la BD
docker exec bodegaje-db pg_dump -U bodegaje -d bodegaje \
    --format=custom --file=/tmp/staging-backup.dump
docker cp bodegaje-db:/tmp/staging-backup.dump ./staging-backup.dump
```

---

## 7. Troubleshooting

### La API no arranca (loop infinito)

```bash
docker logs bodegaje-api --tail 50
```

Causas comunes:
- `.env.staging` falta o tiene secrets placeholder
- `alembic upgrade head` falla (schema desincronizado)
- `db` no está healthy aún (esperar)

### El seed falla con "duplicate key"

```bash
# El RUN_ID random deberia evitarlo, pero si pasa:
python infra/scripts/seed_staging.py --size small  # menos datos, menos colisiones
```

### El cliente no puede acceder desde su red

Verificar que la URL está expuesta correctamente:

```bash
curl -s http://localhost:8080/api/v1/health/live
```

Si estás exponiendo a internet, asegurate de que:
- Nginx tiene TLS (certbot o cloud LB)
- El firewall del VPS abre el 80/443
- CORS permite el dominio del cliente (en `CORS_ALLOWED_ORIGINS`)

### Mailpit no muestra emails

```bash
# Verificar que la API envia al mailpit
docker exec bodegaje-api env | grep SMTP
# Esperado: SMTP_HOST=mailpit

# Inspeccionar via UI
open http://localhost:8025  # UI web de Mailpit
```

---

## Referencias

- [staging-invitacion-cliente.md](staging-invitacion-cliente.md) — plantilla email
- [staging-informe-template.md](staging-informe-template.md) — template informe
- [observability-runbook.md](observability-runbook.md) — Prometheus/Grafana
- [disaster-recovery.md](disaster-recovery.md) — qué hacer si algo cae
