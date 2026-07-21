# Go-Live Testing Runbook (Fase 6: Carga y Datos)

**Fecha:** 2026-07-21
**Estado:** Listo para go-live + pruebas de carga + pruebas de datos

---

## TL;DR

```bash
# 1. Backend arriba (SQLite local o Postgres)
cd apps/api && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Seed usuarios (solo primera vez)
python auditoria-fase5/seed_users_local.py

# 3. Generar datos de prueba
python auditoria-fase5/seed_load_test_data.py --size medium

# 4. Smoke load test
python auditoria-fase5/load_test.py --profile smoke

# 5. Load test real
python auditoria-fase5/load_test.py --profile normal
```

---

## Estado del sistema al cierre de Fase 5

### Tests automatizados
- **378 pasando / 2 fallando / 18 skipped / 0 errores**
- Coverage 77% (gap en `transfers/` legacy y `worker.py`)
- Ver: `docs/informe_revision_pruebas_unitarias.md`

### Bugs arreglados durante live testing
1. ✅ `sqlite3.InterfaceError` race condition → RLock en `execute()`
2. ✅ `IntegrityError` devolvía 500 → exception handler devuelve 422
3. ✅ Orden de rutas en FastAPI → `/solicitudes/bajo-minimo` matcheaba como UUID
4. ✅ Login UI mostraba credenciales incorrectas (`demo123` vs `admin12345`)
5. ✅ `seedDemoData` usaba `/api/v1/transfers` deprecated
6. ✅ `[object Object]` en toasts → normalización en `api.js`

### Issues pendientes (no críticos)
1. ✅ **RESUELTO**: `SECRET_KEY` validation en producción (Issue #1)
2. ✅ **RESUELTO**: `GET /audit` no exponía filtros (Issue #2)
3. ✅ **RESUELTO**: `/transfers/{id}/derived` siempre 503 (Issue #5)
4. ⚠️ **Documentado**: `/api/v1/transfers` POST/PATCH/DELETE → 410 Gone (compat 6 meses)
5. ⚠️ **Documentado**: `notifications/` (inglés) coexiste con `notificaciones/` (español)

---

## 1. Setup de pre-producción

### 1.1 Levantar el backend

#### Opción A: SQLite (dev/QA rápido)
```bash
cd apps/api

# Variables de entorno
export ENVIRONMENT=development
export DATABASE_URL=sqlite+aiosqlite:///./data/dev.db
export REDIS_URL=
export JWT_SECRET=dev-secret-32-chars-aaaaaaaaaaaaaaaaa
export SECRET_KEY=dev-secret-32-chars-bbbbbbbbbbbbbb
export PUBLIC_BASE_URL=http://localhost:8000
export SMTP_HOST=localhost
export SMTP_PORT=1025
export SMTP_FROM=noreply@bodega.cl
export LOG_LEVEL=INFO

# Iniciar
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

#### Opción B: Docker Compose (más cercano a prod)
```bash
cd infra
docker compose -f docker/docker-compose.yml up -d
```

Verificar: `curl http://127.0.0.1:8000/api/v1/health/live` debe retornar `{"status":"alive"}`.

### 1.2 Levantar el frontend
```bash
cd apps/web
npm run dev
```

Verificar: http://127.0.0.1:5173 responde 200.

Si vite no se mantiene arriba (caso observado en Windows con sandbox), lanzar con:
```powershell
Start-Process powershell -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","auditoria-fase5\start_vite.ps1" -WindowStyle Hidden
```

### 1.3 Seed de usuarios
```bash
cd apps/api
python auditoria-fase5/seed_users_local.py
```

Crea: `admin` / `supervisor` / `origen` / `destino` (todos con password `admin12345`).

---

## 2. Generación de datos de prueba

### 2.1 Script: `seed_load_test_data.py`

**Ubicación:** `auditoria-fase5/seed_load_test_data.py`

**Perfiles predefinidos:**

| Perfil  | Warehouses | Productos | Categorías | Proveedores | Solicitudes |
|---------|-----------|-----------|------------|-------------|-------------|
| small   | 5         | 50        | 8          | 5           | 10          |
| medium  | 15        | 300       | 25         | 20          | 30          |
| large   | 50        | 2000      | 80         | 50          | 100         |

**Uso:**
```bash
# Por defecto usa --size=small si no se especifica
python auditoria-fase5/seed_load_test_data.py --size medium

# Override de cantidades individuales
python auditoria-fase5/seed_load_test_data.py \
    --warehouses 20 \
    --products 500 \
    --solicitudes 50

# Cambiar URL/credenciales
python auditoria-fase5/seed_load_test_data.py \
    --base-url http://prod.example.com \
    --username admin \
    --password $ADMIN_PASSWORD
```

**Idempotencia:** cada corrida usa un `RUN_ID` (timestamp+random) en códigos/nombres,
así se puede correr múltiples veces sin chocar con UNIQUE constraints.

**Lo que crea (en orden):**
1. Warehouses: 1 principal + N-1 auxiliares
2. Categorías: 12 L1 base + subcategorías L2
3. Proveedores: N con RUTs aleatorios válidos
4. Productos: N con SKUs/nombres/categorías/precios randomizados
5. Stock inicial: en bodega principal + muestreo en otras
6. Solicitudes: N con estados mezclados (pending/approved/dispatched)

### 2.2 Verificación post-seed
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin12345"}' | jq -r .token
```

```bash
TOKEN=...
curl -s http://127.0.0.1:8000/api/v1/warehouses -H "Authorization: Bearer $TOKEN" | jq length
curl -s http://127.0.0.1:8000/api/v1/products -H "Authorization: Bearer $TOKEN" | jq length
curl -s http://127.0.0.1:8000/api/v1/solicitudes -H "Authorization: Bearer $TOKEN" | jq length
```

---

## 3. Pruebas de carga

### 3.1 Script: `load_test.py`

**Ubicación:** `auditoria-fase5/load_test.py`

**Perfiles predefinidos:**

| Perfil  | Workers | Duración | Ramp-up | Caso de uso              |
|---------|---------|----------|---------|--------------------------|
| smoke   | 5       | 30s      | 5s      | Sanity check post-deploy |
| normal  | 20      | 60s      | 10s     | Carga esperada           |
| peak    | 50      | 60s      | 15s     | Pico de uso              |
| stress  | 100     | 60s      | 20s     | Test de estrés           |

**Uso:**
```bash
# Smoke test (5 workers, 30s, ~750 requests)
python auditoria-fase5/load_test.py --profile smoke

# Carga normal (20 workers, 60s, ~1500 requests)
python auditoria-fase5/load_test.py --profile normal

# Custom
python auditoria-fase5/load_test.py \
    --concurrent 30 \
    --duration 120 \
    --ramp-up 15
```

**Output esperado (ejemplo normal):**
```
======================================================================
 REPORTE FINAL  (profile=normal, concurrent=20, elapsed=60.0s)
======================================================================
 Total requests : 1500
 Exitosos       : 1450 (96.7%)
 Errores        : 50 (3.3%)
 Throughput     : 25.0 req/s

 Latencia (ms) sobre 1450 requests exitosos:
   p50  =   180.0
   p90  =   400.0
   p95  =   600.0
   p99  =   800.0
   max  =  1200.0

 Distribucion por codigo HTTP:
   200 OK             :  1200  ( 80.0%)
   201 Created        :   250  ( 16.7%)
   409 Conflict       :    45  (  3.0%)  <- stock insuficiente en escritura concurrente
```

### 3.2 Endpoints cubiertos
- **Reads (80%):** `/auth/me`, `/inventory/summary`, `/inventory/stock`, `/warehouses`,
  `/products`, `/solicitudes`, `/solicitudes/bajo-minimo`, `/audit`, `/categories`,
  `/proveedores`, `/health/live`
- **Writes (20%):** `POST /inventory/movements`, `POST /warehouses`, `POST /products`

### 3.3 SLOs objetivo
- **Throughput:** >= 20 req/s con 20 workers (SQLite)
- **Latencia p95:** < 500ms
- **Error rate:** < 5% (los 409 por stock insuficiente son esperados)

### 3.4 Errores esperados y cómo interpretarlos
- **409 Conflict** en POST movements: stock insuficiente o duplicado de referencia.
  No es bug, es comportamiento correcto bajo concurrencia.
- **401 Unauthorized** en algunos requests: si el token expira durante el test.
  Aumentar `session_duration_hours` si pasa mucho.
- **500 Server Error**: bug, requiere investigación.

---

## 4. Smoke tests manuales (UI)

### 4.1 Login y dashboard
1. Abrir http://127.0.0.1:5173/login
2. Login con `admin` / `admin12345`
3. Verificar redirección a `/dashboard`
4. Verificar cards de resumen (total stock, alertas)

### 4.2 Cargar demo
1. Click en "Cargar demo" del dashboard
2. Esperar toast verde "Demo cargada"
3. Verificar que `CENTRAL` y `NORTE` aparecen en la lista de bodegas
4. Verificar que `/inventory/stock` muestra stock

### 4.3 Flujo de solicitudes (e2e)
1. Ir a "Solicitudes" en el menú
2. Crear una solicitud:
   - Origen: NORTE
   - Destino: CENTRAL
   - Producto: cualquier ACE-001
   - Cantidad: 10
3. Aprobar desde el detalle
4. Despachar con barcode
5. Recibir
6. Verificar que el stock se movió

### 4.4 Reposición automática
1. Ir a "Reposición"
2. Click "Previsualizar (dry run)" — debería mostrar SKUs bajo mínimo
3. Click "Generar solicitudes" — crea solicitudes para esos SKUs

---

## 5. Checklist pre go-live real

### 5.1 Configuración
- [ ] `ENVIRONMENT=production` en .env de prod
- [ ] `SECRET_KEY` seteado (32+ chars, distinto a JWT_SECRET)
- [ ] `JWT_SECRET` >= 32 chars
- [ ] `SMTP_USE_TLS=true`
- [ ] `DATABASE_URL` apunta a Postgres (no SQLite)
- [ ] `REDIS_URL` apunta a Redis real
- [ ] `CORS_ALLOWED_ORIGINS` configurado para el dominio de prod
- [ ] `SENTRY_DSN` configurado
- [ ] Secrets NO commiteados (verificado con gitleaks)

### 5.2 Datos
- [ ] Seed usuarios producción (no usar `admin12345`!)
- [ ] Generar dataset de prueba con `seed_load_test_data.py`
- [ ] Verificar que las migraciones se aplicaron (`alembic upgrade head`)

### 5.3 Performance
- [ ] Smoke test pasa (`profile=smoke` con > 95% success)
- [ ] Load test pasa (`profile=normal` con throughput >= 20 req/s)
- [ ] No hay 500 errors en los logs de uvicorn

### 5.4 Monitoreo post go-live
- [ ] Métricas Prometheus expuestas en `/metrics`
- [ ] Alertas configuradas (Sentry, Grafana)
- [ ] Logs estructurados con correlation_id
- [ ] Health check `/api/v1/health` retorna 200 (no degraded)

---

## 6. Comandos rápidos

```bash
# Suite de tests
cd apps/api && pytest -v

# Solo los tests del fix de hardening
pytest tests/unit/test_hardening.py -v

# Generar datos medium
python auditoria-fase5/seed_load_test_data.py --size medium

# Load test 60s con 20 workers
python auditoria-fase5/load_test.py --profile normal

# Verificar unicidad (debe fallar al crear duplicado)
curl -X POST http://127.0.0.1:8000/api/v1/warehouses \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"code":"DUPLICADO","name":"Ya Existe","warehouse_type":"principal"}'
# Repetir para ver el 422 unique_constraint_violated

# Audit con filtros (Issue #2 resuelto)
curl "http://127.0.0.1:8000/api/v1/audit?entity_type=warehouse&limit=10" \
  -H "Authorization: Bearer $TOKEN"

# Solicitud /transfers sigue dando 410 Gone (compat 6 meses)
curl -X POST http://127.0.0.1:8000/api/v1/transfers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
# 410 Gone con mensaje de deprecation
```

---

## 7. Troubleshooting

| Síntoma                                       | Causa probable                    | Solución                                   |
|-----------------------------------------------|-----------------------------------|--------------------------------------------|
| `uvicorn` no arranca                          | Falta SECRET_KEY / JWT_SECRET    | Verificar `.env` o env vars                |
| `IntegrityError: CHECK constraint failed`     | Valor de `warehouse_type` invalido| Usar `principal`/`auxiliar`/`mecanico_box`|
| `409 unique_constraint_violated`              | `name` duplicado                  | Usar nombre único                          |
| `[object Object]` en toast                   | Frontend viejo                    | HMR actualiza `api.js` automáticamente      |
| `interface error: bad parameter`              | Concurrencia SQLite               | **Resuelto**: RLock en `sqlite_legacy.py`  |
| Login con `demo123` falla                    | UI desactualizada                 | **Resuelto**: UI muestra `admin12345`      |
| "Cargar demo" falla con 410                  | UI usa `/transfers` deprecated    | **Resuelto**: seed actualizado             |
| 5xx en /audit                                 | audit_log no existe               | Verificar migración 0003                   |

---

## 8. Contacto y escalación

- **Issues del proyecto:** `https://github.com/Renanakin/bodega/issues`
- **Documentación:** `docs/`
- **Runbook original:** `docs/go_live_runbook.md`
- **Informe de revisión:** `docs/informe_revision_pruebas_unitarias.md`

---

**Última actualización:** 2026-07-21
**Versión:** 1.0
**Estado:** ✅ Listo para go-live
