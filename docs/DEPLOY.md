# Manual de Despliegue y Setup para Testing

> **Para:** un dev nuevo, un agente, o vos en otro IDE que necesita clonar
> el repo, levantar el sistema, conectarse a la misma BD y correr tests.
>
> **Lee esto de arriba a abajo la primera vez.** Despues usa el indice para
> saltar al modulo que necesites.

---

## Indice rapido

1. [TL;DR (30 segundos)](#1-tldr-30-segundos)
2. [Requisitos](#2-requisitos)
3. [Setup paso a paso](#3-setup-paso-a-paso)
4. [Conexion a la BD](#4-conexion-a-la-bd)
5. [Como correr el sistema en otro IDE](#5-como-correr-el-sistema-en-otro-ide)
6. [Como correr TODOS los tests](#6-como-correr-todos-los-tests)
7. [Credenciales del sistema](#7-credenciales-del-sistema)
8. [Como interactuar con el sistema](#8-como-interactuar-con-el-sistema)
9. [Troubleshooting](#9-troubleshooting)
10. [Anexo: estructura del repo](#10-anexo-estructura-del-repo)

---

## 1. TL;DR (30 segundos)

Si ya tenes el repo y Docker corriendo, **3 comandos** y el sistema esta up:

```bash
# 1. Clonar e ir al repo
git clone https://github.com/Renanakin/bodega.git
cd bodega

# 2. Levantar todo (13 containers: api, web, db, redis, mailpit, nginx, etc.)
docker compose -f infra/docker/docker-compose.yml up -d

# 3. Esperar 30s y probar
curl -sk https://localhost:8443/api/v1/health
```

Si te responde `{"status":"ok",...}` → **el sistema esta funcionando.**

Despues de eso, segui leyendo desde la seccion 4 para conectarte a la BD y correr tests.

---

## 2. Requisitos

| Software | Version minima | Verificar | Como instalar |
|---|---|---|---|
| **Docker Desktop** | 4.x | `docker --version` | https://www.docker.com/products/docker-desktop/ |
| **Docker Compose** | v2.x | `docker compose version` | Viene con Docker Desktop |
| **Git** | 2.40+ | `git --version` | https://git-scm.com/download/win |
| **Python** | 3.12+ | `python --version` | https://www.python.org/downloads/ |
| **Node.js** | 20+ | `node --version` | https://nodejs.org/ |
| **PowerShell** | 5+ | `$PSVersionTable.PSVersion` | Preinstalado en Windows 10/11 |

**Espacio en disco:** ~5 GB para la imagen Docker + volumenes.

**Puertos que usa el sistema (todos en `localhost`):**

| Puerto | Servicio | URL |
|---|---|---|
| 8080 | Nginx (HTTP) | http://localhost:8080 |
| 8443 | Nginx (HTTPS, cert self-signed) | https://localhost:8443 |
| 5432 | Postgres 17 | `localhost:5432` |
| 6379 | Redis 8 | `localhost:6379` |
| 1025 | Mailpit SMTP | (interno) |
| 8025 | Mailpit Web UI | http://localhost:8025 |
| 3000 | Grafana | http://localhost:3000 (admin/admin) |
| 9090 | Prometheus | http://localhost:9090 |
| 9093 | Alertmanager | http://localhost:9093 |
| 9100 | Node Exporter | (interno) |

---

## 3. Setup paso a paso

### 3.1 Clonar el repo

```bash
git clone https://github.com/Renanakin/bodega.git
cd bodega
```

### 3.2 Verificar que Docker esta corriendo

```bash
docker --version
docker compose version
docker ps
```

Si `docker ps` falla con "Cannot connect to the Docker daemon", abrí Docker Desktop.

### 3.3 Levantar el sistema

```bash
# Levanta los 13 containers: api, web, db, redis, mailpit, nginx, etc.
docker compose -f infra/docker/docker-compose.yml up -d

# Ver el estado
docker compose -f infra/docker/docker-compose.yml ps
```

Salida esperada (13 containers en `Up`):

```
NAME                         STATUS              PORTS
bodegaje-alertmanager        Up 30 minutes       0.0.0.0:9093->9093/tcp
bodegaje-api                 Up 30 minutes
bodegaje-backup              Up 30 minutes
bodegaje-db                  Up 30 minutes (healthy)   0.0.0.0:5432->5432/tcp
bodegaje-grafana             Up 30 minutes       0.0.0.0:3000->3000/tcp
bodegaje-mailpit             Up 30 minutes (healthy)   0.0.0.0:8025->8025/tcp
bodegaje-nginx               Up 30 minutes       0.0.0.0:8080->80/tcp, 8443->443/tcp
bodegaje-node-exporter       Up 30 minutes       0.0.0.0:9100->9100/tcp
bodegaje-postgres-exporter   Up 30 minutes       0.0.0.0:9187->9187/tcp
bodegaje-prometheus          Up 30 minutes       0.0.0.0:9090->9090/tcp
bodegaje-redis               Up 30 minutes
bodegaje-web                 Up 30 minutes
bodegaje-worker              Up 30 minutes
```

### 3.4 Esperar que el API este lista

La primera vez tarda ~30-60 segundos en arrancar (aplica migraciones + carga datos seed).

```bash
# En PowerShell
for ($i=1; $i -le 30; $i++) {
  $r = curl.exe -sk https://localhost:8443/api/v1/health 2>&1
  if ($r -like '*ok*') { Write-Host "API lista"; break }
  Start-Sleep 2
}
```

Salida esperada cuando este lista:

```json
{"status":"ok","version":"0.1.0","environment":"staging",
 "components":{
   "db":{"status":"ok","backend":"postgres","latency_ms":35.76},
   "redis":{"status":"ok","latency_ms":"2.88"},
   "worker":{"status":"ok","active_workers":"11","latency_ms":"2.55"}
 }}
```

### 3.5 (Opcional) Aplicar migraciones manualmente

Solo necesario si modificas la BD localmente. En condiciones normales el
container `bodegaje-api` corre las migraciones al arrancar.

```bash
docker exec bodegaje-api alembic current
docker exec bodegaje-api alembic upgrade head
```

---

## 4. Conexion a la BD

### 4.1 Credenciales de la BD

La BD **Postgres 17** se levanta con Docker Compose. Las credenciales
estan en `infra/docker/.env.development` (NO las commitees si las cambiaste).

| Parametro | Valor dev | Valor staging | Valor production |
|---|---|---|---|
| Host | `localhost` | `db` (en docker network) | `db` (en docker network) |
| Port | `5432` | `5432` | `5432` |
| Database | `bodegaje` | `bodegaje` | `bodegaje` |
| User | `bodegaje` | `bodegaje` | `bodegaje` |
| Password | `bodegaje` | `bodegaje` | (de .env.production) |

### 4.2 Conexion con `psql` (CLI)

```bash
# Desde el host (PowerShell o bash)
docker exec -it bodegaje-db psql -U bodegaje -d bodegaje
```

> **Nota en Windows:** `psql` no existe nativamente. Usa siempre
> `docker exec` o conectate desde un IDE (DataGrip, DBeaver, pgAdmin).

### 4.3 Conexion desde un IDE (DataGrip, DBeaver, VSCode, PyCharm)

**Parametros de conexion JDBC/ODBC para Postgres:**

```
Host:     localhost
Port:     5432
Database: bodegaje
User:     bodegaje
Password: bodegaje
```

**URL completa (para `.env`, scripts, etc.):**

```
postgresql+asyncpg://bodegaje:bodegaje@localhost:5432/bodegaje
```

**Desde VSCode** con la extension "PostgreSQL" (por `ckolkman`):

1. Abrir panel "Database" (Ctrl+Shift+D)
2. Click `+` → "Create Connection"
3. Llenar: `localhost:5432`, user `bodegaje`, password `bodegaje`, database `bodegaje`
4. SSL: Disable (es dev local)
5. Test → OK

**Desde PyCharm DataGrip / DBeaver:**

1. File → New → Data Source → PostgreSQL
2. Host: `localhost`, port: `5432`
3. User: `bodegaje`, password: `bodegaje`, database: `bodegaje`
4. Test Connection → OK

### 4.4 Tablas principales

Una vez conectado, las tablas que vas a ver:

```
audit_logs                       auditoria de acciones
categorias                      jerarquia de categorias
detalle_orden_compra             lineas de OC
detalle_solicitud_recarga        lineas de solicitudes
email_outbox                     cola de emails pendientes
inventory_movements              todos los movimientos
ordenes_compra                   OCs a proveedores
productos                        catalogo de productos
productos_detalle_neumatico      extension para neumaticos
proveedores                      proveedores externos
receipts                         recepciones de mercaderia (FIX POST-E2E)
receipt_lines                    lineas de recepciones
solicitudes_recarga              solicitudes entre bodegas
stock_levels                     stock por (bodega, producto)
ubicaciones_estanteria           ubicaciones fisicas
users                            usuarios del sistema
user_sessions                    sesiones + refresh tokens
warehouses                       bodegas
```

### 4.5 Ver datos seed importantes

```sql
-- Bodegas
SELECT id, code, name, warehouse_type, is_active
FROM warehouses
ORDER BY warehouse_type, code;

-- Productos
SELECT id, sku, name, is_active FROM productos LIMIT 20;

-- Usuarios (login)
SELECT id, username, full_name, role, is_active FROM users;

-- Supervisores (tabla separada de users)
SELECT id, nombre, email, cargo, activo FROM supervisores;
```

### 4.6 Inspeccionar el ultimo estado del sistema

```sql
-- Stock total por bodega
SELECT w.code, w.warehouse_type, COUNT(sl.*) AS n_skus, SUM(sl.quantity) AS total
FROM warehouses w
LEFT JOIN stock_levels sl ON sl.warehouse_id = w.id
WHERE w.is_active = true
GROUP BY w.id, w.code, w.warehouse_type
ORDER BY w.warehouse_type, w.code;

-- Ultimos movimientos
SELECT m.id, m.movement_type, m.quantity, m.reference_type, m.created_at
FROM inventory_movements m
ORDER BY m.created_at DESC
LIMIT 20;

-- Ultimas solicitudes
SELECT codigo, estado, prioridad, created_at
FROM solicitudes_recarga
ORDER BY created_at DESC
LIMIT 10;

-- Ultimas OCs
SELECT codigo, estado, proveedor_nombre, total_estimado, created_at
FROM ordenes_compra
ORDER BY created_at DESC
LIMIT 10;
```

---

## 5. Como correr el sistema en otro IDE

### 5.1 Abrir el repo en otro IDE

**VSCode:**

```bash
code .
```

Recomendado instalar las extensiones:
- `ms-python.python` (Python)
- `ms-python.vscode-pylance` (Pylance)
- `ckolkman.vscode-postgres` (PostgreSQL client)
- `dbaeumer.vscode-eslint` (ESLint, para `apps/web`)
- `bradlc.vscode-tailwindcss` (Tailwind, para `apps/web`)
- `ms-python.debugpy` (Debug Python)

**PyCharm / IntelliJ:**

1. File → Open → seleccionar la carpeta `bodega`
2. PyCharm detecta el monorepo. Click "Open as Project"
3. Configurar el SDK Python: Settings → Project → Python Interpreter → `apps/api/.venv/bin/python` (si existe)
4. Marcar `apps/api/` como Sources Root (click derecho → "Mark Directory as" → "Sources Root")

**DataGrip (solo para BD):** ver seccion 4.3.

### 5.2 Setup del entorno Python local (opcional, para correr tests sin Docker)

Si queres correr los **tests unitarios y de integracion** directamente desde
tu IDE (sin pasar por Docker):

```bash
# Ir a la carpeta del API
cd apps/api

# Crear venv
python -m venv .venv

# Activar (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activar (Linux/Mac)
# source .venv/bin/activate

# Instalar dependencias
pip install -e ".[dev]"

# Verificar
python -c "import app.main; print('OK')"
```

**Dependencias clave** (de `apps/api/pyproject.toml`):

- `fastapi` (>=0.116)
- `sqlalchemy[asyncio]` (>=2.0)
- `asyncpg` (driver Postgres async)
- `aiosqlite` (driver SQLite para tests)
- `pydantic` (>=2.0)
- `structlog` (logging)
- `arq` (worker async)
- `pytest`, `pytest-asyncio`, `pytest-cov` (testing)

### 5.3 Setup del frontend (opcional, si vas a tocar `apps/web`)

```bash
cd apps/web
npm install
npm run dev     # arranca Vite en :5173
npm run build   # build de produccion
npm run test    # vitest
```

Pero el frontend **ya esta servido por el container `bodegaje-web` en
`localhost:8080`**, no necesitás `npm run dev` para usarlo.

### 5.4 Donde correr los tests (recomendado)

**Tests unitarios e integracion:**
- DENTRO del container (recomendado, mismo Python que produccion)
- O local con el venv (mas rapido el feedback)

**Tests E2E (`tests/e2e/`):**
- **SIEMPRE fuera del container** (golpean `https://localhost:8443`)
- Usan `requests` o `urllib` (Python stdlib)
- No necesitan instalacion extra: solo `python tests/e2e/run_all.py`

---

## 6. Como correr TODOS los tests

El sistema tiene **3 capas de tests** (ver `docs/plan_ejecucion_testing.md`):

### 6.1 Tests unitarios (70% de la piramide, ~400 tests)

```bash
# Opcion A: DENTRO del container (recomendado, consistencia con produccion)
docker exec bodegaje-api pytest tests/unit/ -v -p no:postgresql

# Opcion B: Local con venv (mas rapido)
cd apps/api
pytest tests/unit/ -v -p no:postgresql
```

> **Por que `-p no:postgresql`:** el container `bodegaje-api` no incluye el
> driver `psycopg` (necesario para el plugin `pytest-postgresql`). Como
> los tests unitarios usan SQLite in-memory, el plugin de Postgres no es
> necesario. Desactivarlo evita el ImportError y mantiene la suite verde.

**Output esperado:** ~400 verde, ~57 pre-existentes flaky cuando corren en
suite completa (ver seccion 6.6 — bug arreglado en commit `ddb248d`).

**Marcar un test especifico:**
```bash
docker exec bodegaje-api pytest tests/unit/test_security_injection.py -v -p no:postgresql
docker exec bodegaje-api pytest tests/unit/test_idempotency.py::TestInMemoryIdempotencyCache -v -p no:postgresql
```

### 6.2 Tests de integracion (~63 tests)

```bash
docker exec bodegaje-api pytest tests/integration/ -v -p no:postgresql
```

> **Nota:** algunos tests de integracion usan SQLite in-memory (no Postgres)
> por velocidad. Esto esta documentado en `tests/integration/README.md`.

### 6.3 Tests E2E completos (auditoria-fase5)

```bash
# Desde el host (golpea https://localhost:8443)
cd "C:\Users\Tranquilidad\auditoria-fase5"

# Bateria completa (5 tests, ~70s, incluye Playwright)
python run_all.py

# Sin Playwright (3 tests, ~25s, mas rapido)
python run_all.py --skip bug11_layout manual_screens

# Solo el modulo OC por correo
python run_all.py --only oc_correo_flujo

# Solo backup + restore
python run_all.py --only backup_restore

# O via Makefile
make e2e
make e2e-quick
make e2e-oc
```

**Output esperado:** `[EXIT 0] Todos los 5 tests pasaron`.

### 6.4 E2E del Manual de Usuario (43/43 verde, RECOMENDADO)

Este es **el test mas importante** porque valida el sistema contra el manual
de usuario. Ver `auditoria-fase5/REPORTE_E2E_MANUAL.md`.

```bash
cd "C:\Users\Tranquilidad\auditoria-fase5"
python e2e_manual_usuario.py
```

**Output esperado:**
```
RESUMEN FINAL
  Pasados: 43 / 43
  Fallados: 0
Por flujo:
  SETUP  ->   6/  6 (fail: 0)
  19.1   ->   7/  7 (fail: 0)
  19.2   ->  11/ 11 (fail: 0)
  19.3   ->   4/  4 (fail: 0)
  19.4   ->   7/  7 (fail: 0)
```

**Argumentos opcionales:**
```bash
python e2e_manual_usuario.py --base https://localhost:8443/api/v1
```

### 6.5 Tests de performance (Big-O P0-P3)

```bash
cd "C:\PROYECTOS\bodega"
python tests/perf/explain_critical_queries.py    # EXPLAIN ANALYZE
python tests/perf/drp_drill.py                  # DRP drill 3 escenarios
```

### 6.6 Sobre los tests pre-existentes flaky

**El sistema tiene ~57 tests pre-existentes que fallan en la suite completa
de tests unitarios legacy** (`test_solicitudes.py`, `test_supervisores.py`,
`test_transfers.py`, etc.) — pero **pasan individualmente**.

**Causa raiz documentada:** bug pre-existente en `app/db/sqlite_legacy.py`
donde las migraciones SQL corren ANTES de que `Base.metadata.create_all`
cree las tablas. Esto fue **arreglado en commit `ddb248d`** (FIX FASE B).

**Si los tests fallan al correr juntos:** correlos individualmente:
```bash
docker exec bodegaje-api pytest tests/unit/test_solicitudes.py -v -p no:postgresql
```

### 6.7 Tabla resumen de los tests

| Suite | Comando | Tests | Tiempo |
|---|---|---|---|
| Unit ofensivos (security) | `pytest tests/unit/test_security_*.py -v -p no:postgresql` | 36 | 25s |
| Unit idempotency | `pytest tests/unit/test_idempotency.py -v -p no:postgresql` | 16 | 9s |
| Unit cursor | `pytest tests/unit/test_cursor.py -v -p no:postgresql` | 11 | <5s |
| Unit hardening | `pytest tests/unit/test_hardening.py -v -p no:postgresql` | 11 | <5s |
| Unit auth | `pytest tests/unit/test_auth.py -v -p no:postgresql` | 17 | <5s |
| Unit logging | `pytest tests/unit/test_logging.py -v -p no:postgresql` | 8 | <5s |
| **E2E manual usuario** | `python e2e_manual_usuario.py` | **43** | **1.4s** |
| E2E audit-fase5 | `python run_all.py` | 5 | 70s |
| E2E sin Playwright | `python run_all.py --skip bug11_layout manual_screens` | 3 | 25s |
| Perf Big-O | `python tests/perf/explain_critical_queries.py` | 5 EXPLAINs | 5s |
| DRP drill | `python tests/perf/drp_drill.py` | 3 escenarios | 30s |

> Todos los comandos `pytest` en el container requieren `-p no:postgresql`
> para evitar el ImportError del driver psycopg (no necesario en unit tests).

---

## 7. Credenciales del sistema

### 7.1 Usuarios de la aplicacion (4 precargados)

| Username | Password | Rol | Que puede hacer |
|---|---|---|---|
| `admin` | `admin12345` | `admin` | Todo: gestion de usuarios, configuracion, todas las bodegas |
| `supervisor` | `admin12345` | `supervisor` | Aprobar/rechazar solicitudes y OCs, supervisar operaciones |
| `origen` | `admin12345` | `origin_operator` | Operador de bodega origen: despachar solicitudes |
| `destino` | `admin12345` | `destination_operator` | Operador de bodega destino: recibir solicitudes |

> **IMPORTANTE:** estos passwords son del `.env.development` (DB seed).
> En staging/production **deben cambiarse** (ver `docs/operations/GO_LIVE_CHECKLIST.md`).

### 7.2 Base de datos

| Parametro | Valor |
|---|---|
| Host | `localhost:5432` (desde host) o `db:5432` (desde dentro de Docker) |
| User | `bodegaje` |
| Password | `bodegaje` |
| Database | `bodegaje` |
| **Usuario admin alternativo** | Postgres `postgres` con password `postgres` (solo dev) |

### 7.3 Grafana

| Parametro | Valor |
|---|---|
| URL | http://localhost:3000 |
| User | `admin` |
| Password | `admin` |

### 7.4 Mailpit (SMTP dev)

| Parametro | Valor |
|---|---|
| URL | http://localhost:8025 |
| SMTP host (interno) | `mailpit:1025` |
| Funcion | Captura los emails que envia el sistema en dev/staging |

### 7.5 JWT y refresh tokens

| Parametro | Valor dev |
|---|---|
| Algoritmo | `HS256` |
| Access token TTL | 1 hora |
| Refresh token TTL | 7 dias |
| Secret | `dev-secret-not-for-production-32chars-XXXXXX` (cambiar en prod) |

### 7.6 Resumen visual

| Servicio | URL | User | Password |
|---|---|---|---|
| Web UI | http://localhost:8080 | `admin` | `admin12345` |
| Web UI (HTTPS) | https://localhost:8443 | `admin` | `admin12345` |
| API REST | https://localhost:8443/api/v1 | (Bearer token) | - |
| Postgres | localhost:5432 | `bodegaje` | `bodegaje` |
| Grafana | http://localhost:3000 | `admin` | `admin` |
| Mailpit | http://localhost:8025 | (sin auth) | - |
| Prometheus | http://localhost:9090 | (sin auth) | - |

---

## 8. Como interactuar con el sistema

### 8.1 Via la UI web (recomendado para empezar)

Abrí http://localhost:8080 en tu navegador.

1. **Login:** usuario `admin`, password `admin12345`
2. **Dashboard:** vista ejecutiva con KPIs (alertas, solicitudes, transferencias)
3. **Modulos accesibles desde el menu lateral:**
   - Bodegas, Productos, Categorias
   - Inventario y movimientos
   - Recepciones (modulo nuevo, FIX POST-E2E)
   - Solicitudes, Reposicion automatica
   - Multibodega, Consolidador
   - Ordenes de compra
   - Reportes, Notificaciones
   - Supervisores, Auditoria, Configuracion

### 8.2 Via la API REST (curl / Postman / HTTPie)

**Todos los endpoints en `https://localhost:8443/api/v1`.**

Ejemplo: hacer login y crear una solicitud:

```bash
# 1. Login (obtiene token)
TOKEN=$(curl -sk -X POST https://localhost:8443/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin12345"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 2. Listar bodegas
curl -sk https://localhost:8443/api/v1/warehouses \
  -H "Authorization: Bearer $TOKEN"

# 3. Crear una recepcion (manual seccion 8, FIX POST-E2E)
curl -sk -X POST https://localhost:8443/api/v1/receipts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id_bodega_destino": "a96d195d-58c2-4a5c-97d8-df333f44dab1",
    "id_proveedor": "afe472c9-5d2b-4122-9bff-378b8f45c8d9",
    "numero_documento": "FAC-TEST-001",
    "lineas": [
      {
        "id_producto": "83e9bbc4-5325-447d-923b-09132e6d8e15",
        "cantidad": 50,
        "precio_unitario": 1500
      }
    ]
  }'

# 4. Confirmar la recepcion (genera movimiento in)
RECEIPT_ID="<id que devolvio el paso 3>"
curl -sk -X POST "https://localhost:8443/api/v1/receipts/$RECEIPT_ID/confirm" \
  -H "Authorization: Bearer $TOKEN"
```

### 8.3 Via la BD (SQL directo)

```bash
# Conectarse
docker exec -it bodegaje-db psql -U bodegaje -d bodegaje

# Ver el stock actual
SELECT w.code, p.sku, sl.quantity
FROM stock_levels sl
JOIN warehouses w ON w.id = sl.warehouse_id
JOIN productos p ON p.id = sl.product_id
ORDER BY w.code, p.sku
LIMIT 20;

# Ver las ultimas 10 solicitudes con su detalle
SELECT s.codigo, s.estado, s.prioridad, s.created_at,
       d.id_producto, d.cantidad_solicitada, d.cantidad_despachada, d.cantidad_recibida
FROM solicitudes_recarga s
JOIN detalle_solicitud_recarga d ON d.id_solicitud = s.id
ORDER BY s.created_at DESC
LIMIT 10;

# Salir
\q
```

### 8.4 Via Mailpit (ver emails enviados)

Abrí http://localhost:8025. Vas a ver los emails que el sistema envia
(recepciones, OCs, etc.). Click en un email para ver su contenido HTML
y los links de aprobacion publica.

### 8.5 Via Grafana (metricas)

Abrí http://localhost:3000, login `admin`/`admin`.

Dashboards disponibles:
- **Bodegaje - Overview**: KPIs generales (stock, alertas, transferencias)
- **Bodegaje - Big-O Health**: queries lentas, indices, locks (ver
  `infra/docker/grafana/dashboards/big-o-health.json`)

### 8.6 Flujos completos del manual

El manual de usuario (`docs/manual_usuario.md`, 762 lineas) describe
15 modulos. Para una guia paso a paso, ver:

- **Seccion 19.1:** Recibir mercaderia de un proveedor
  (ahora via `/receipts`, FIX POST-E2E)
- **Seccion 19.2:** Mover stock entre bodegas (solicitud)
  (descuenta origen, suma destino, FIX POST-E2E)
- **Seccion 19.3:** Reposicion automatica
- **Seccion 19.4:** Orden de compra con aprobacion publica
  (token recuperable via `?include_token=true`, FIX POST-E2E)

Para validar end-to-end todos estos flujos, correr
`python e2e_manual_usuario.py` (43/43 verde).

---

## 9. Troubleshooting

### 9.1 El API no arranca (502 Bad Gateway)

```bash
# Ver el log del API
docker logs bodegaje-api --tail 50

# Buscar errores de importacion o migracion
docker logs bodegaje-api 2>&1 | grep -i "error\|traceback"
```

**Causa comun:** migracion pendiente. Aplicar manualmente:
```bash
docker exec bodegaje-api alembic upgrade head
docker compose -f infra/docker/docker-compose.yml restart api
```

### 9.2 Tests unitarios fallan en suite completa pero pasan individuales

Esto era un bug pre-existente de `app/db/sqlite_legacy.py` que fue
**arreglado en commit `ddb248d`**. Si tu copia del repo no tiene ese
commit, actualiza:

```bash
git pull origin main
docker compose -f infra/docker/docker-compose.yml restart api
```

Si sigue fallando, corré los tests individualmente y reporta.

### 9.3 Rate limit 429 al hacer login

El sistema limita a 5 logins fallidos por minuto (Regla C5.2).
**Esperar 30 segundos** o reiniciar el container:

```bash
docker compose -f infra/docker/docker-compose.yml restart api
```

### 9.4 Mailpit no muestra los emails

El worker Arq procesa el `email_outbox` cada 5 minutos (configurable).
Para forzar el envio inmediato:

```bash
docker logs bodegaje-worker --tail 20
```

Si ves errores, reinicia:
```bash
docker compose -f infra/docker/docker-compose.yml restart worker
```

### 9.5 Postgres no acepta conexiones

```bash
# Verificar que el container esta healthy
docker ps --filter "name=bodegaje-db"

# Si no, ver el log
docker logs bodegaje-db --tail 30
```

### 9.6 No puedo conectarme a localhost:5432 desde mi IDE

**Causa comun:** Docker Desktop a veces bindea el puerto solo a `127.0.0.1`.
Proba:
- `127.0.0.1:5432` en vez de `localhost:5432`
- Verificar firewall de Windows
- Verificar que el puerto este publicado:
  ```bash
  docker port bodegaje-db
  # Debe decir: 5432/tcp -> 0.0.0.0:5432
  ```

### 9.7 Quiero resetear todo y empezar de cero

```bash
# Bajar todo y borrar volumenes
docker compose -f infra/docker/docker-compose.yml down -v

# Levantar de nuevo (aplica migraciones + seed automaticamente)
docker compose -f infra/docker/docker-compose.yml up -d

# Esperar 60s y validar
curl -sk https://localhost:8443/api/v1/health
```

> **CUIDADO:** `-v` borra TODOS los volumenes (BD, backups, configs). Solo
> usar en dev. En staging/production, ver `docs/operations/DRP_DRILL_REPORT_2026-07-24.md`.

### 9.8 El container de Mailpit no captura emails

Verificar que el SMTP este configurado para apuntar a Mailpit en dev:

```bash
docker exec bodegaje-api env | grep SMTP
# Debe decir: SMTP_HOST=mailpit
#            SMTP_PORT=1025
```

Si dice `SMTP_HOST=localhost`, el container no resuelve `mailpit`. Ver
`infra/docker/.env.development` y reiniciar el API.

---

## 10. Anexo: estructura del repo

```
bodega/
├── apps/
│   ├── api/                      # Backend FastAPI
│   │   ├── app/
│   │   │   ├── main.py           # create_app() entrypoint
│   │   │   ├── api/              # Router principal de v1
│   │   │   ├── core/             # Config, logging, security, rate limit, etc.
│   │   │   ├── db/               # Modelos SQLAlchemy + sesion async
│   │   │   ├── modules/          # Logica de negocio (warehouses, products, etc.)
│   │   │   │   ├── auth/         # Login, refresh, RBAC
│   │   │   │   ├── inventory/    # Stock + movimientos
│   │   │   │   ├── solicitudes/  # Solicitudes entre bodegas
│   │   │   │   ├── ordenes_compra/  # OCs a proveedores
│   │   │   │   ├── receipts/     # Recepciones (FIX POST-E2E)
│   │   │   │   └── ...           # +14 modulos mas
│   │   │   └── shared/           # MovementEngine, barcode, etc.
│   │   ├── alembic/              # Migraciones de BD
│   │   ├── tests/
│   │   │   ├── unit/             # 400+ tests unitarios
│   │   │   ├── integration/      # 63 tests de integracion
│   │   │   └── conftest.py
│   │   ├── pyproject.toml        # Dependencias + config pytest
│   │   └── Dockerfile
│   └── web/                      # Frontend React + Vite
│       ├── src/                  # Componentes
│       ├── package.json
│       └── Dockerfile
├── db/
│   └── migrations/               # SQL mirror de las migraciones Alembic
├── infra/
│   └── docker/
│       ├── docker-compose.yml    # 13 containers
│       ├── nginx/                # Config nginx + certs + TLS
│       ├── prometheus/           # Config Prometheus
│       ├── grafana/              # Dashboards preconfigurados
│       └── .env.development      # Variables de entorno (dev only)
├── docs/
│   ├── manual_usuario.md         # 762 lineas, manual completo
│   ├── DEPLOY.md                 # ESTE ARCHIVO
│   ├── plan_ejecucion_testing.md # Plan de testing
│   ├── RESULTS_plan_testing.md   # Reporte de testing
│   ├── REPORTE_FLUJO_E2E.md     # Reporte E2E flujo completo
│   ├── operations/               # GO_LIVE, DRP, PRE_PENTEST
│   ├── architecture/             # ADRs, diagramas
│   └── roadmap_*.md              # Roadmaps de fases
├── tests/
│   ├── e2e/                      # Bateria E2E orquestada (run_all.py)
│   ├── perf/                     # Big-O + DRP drill
│   └── README.md
├── auditoria-fase5/             # E2E + reporte fuera del repo principal
│   ├── e2e_manual_usuario.py     # 43/43 verde
│   ├── run_all.py                # Orquestador E2E
│   ├── REPORTE_E2E_MANUAL.md     # Reporte del manual
│   └── ...                       # +10 scripts E2E historicos
├── Makefile                      # make e2e, make e2e-quick, etc.
├── README.md
└── .gitignore
```

### Variables de entorno clave

| Variable | Dev | Staging | Production |
|---|---|---|---|
| `ENVIRONMENT` | `development` | `staging` | `production` |
| `DEBUG` | `true` | `false` (rechazado) | `false` (rechazado) |
| `DATABASE_URL` | `postgresql+asyncpg://...` | `postgresql+asyncpg://...` | `postgresql+asyncpg://...` |
| `JWT_SECRET` | dev-secret (32+ chars) | secret real (32+ chars) | secret real (32+ chars) |
| `SECRET_KEY` | dev-secret | secret real | secret real (HMAC) |
| `REDIS_URL` | `redis://...` | `redis://...` | `redis://...` |
| `SMTP_HOST` | `mailpit` | SES/SendGrid | SES/SendGrid |
| `CORS_ALLOWED_ORIGINS` | `localhost:5173,...` | staging.example.com | app.example.com |

> **En produccion**, `DEBUG=true` es **rechazado** por `Settings._validate_production_secrets()`
> (ver `apps/api/app/core/config.py`). Esto fue agregado por la FASE A del
> plan de testing ofensivo (FIX bug pre-existente).

---

## Resumen ejecutivo

| Tarea | Comando | Tiempo |
|---|---|---|
| **Levantar el sistema desde cero** | `docker compose -f infra/docker/docker-compose.yml up -d` | 1-2 min |
| **Validar que funciona** | `curl -sk https://localhost:8443/api/v1/health` | <1s |
| **Conectarse a la BD** | `localhost:5432` user `bodegaje` pass `bodegaje` | <1s |
| **Correr TODOS los tests E2E** | `python e2e_manual_usuario.py` | 1.4s |
| **Correr tests unitarios ofensivos** | `docker exec bodegaje-api pytest tests/unit/test_security_*.py -v` | 30s |
| **Resetear todo** | `docker compose -f infra/docker/docker-compose.yml down -v && up -d` | 2-3 min |
| **Login UI** | http://localhost:8080 → `admin` / `admin12345` | - |
| **Login API** | `POST /auth/login` con `{"username":"admin","password":"admin12345"}` | - |

**TL;DR final:** Clone → `docker compose up -d` → esperá 30s → `curl /health` → `python e2e_manual_usuario.py` → 43/43 verde → **sistema funcionando**.

**Contacto / dudas:** ver `docs/operations/GO_LIVE_CHECKLIST.md` o
contactar al equipo via Slack #bodega-dev.
