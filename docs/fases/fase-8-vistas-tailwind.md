# Fase 8: Vistas Tailwind restantes + Backend operativo

**Status:** ✅ Completada
**Fecha:** 2026-07-15
**Equipo:** 1 BE + 1 FE
**Esfuerzo:** L (3-5 días, ejecutado en 1 sesion)

## 1. Resumen ejecutivo

La Fase 8 cierra las **vistas de gestion operativa** que el bodeguero central
y los supervisores necesitaban para configurar el sistema sin tocar la BD:
`CategoriasPage` (arbol colapsable), `ReplenishmentRuleForm` (parametros por
producto-bodega), `NotificationsCenter` (campanita in-app), `ReportsPage`
refactor con tabs + export PDF ejecutivo, y `SettingsPage` refactor con
tabs (Reglas / Proveedores / Stock).

En el backend se anadieron 3 modulos nuevos (`proveedores`, `reports`,
`notificaciones` in-app) y 2 endpoints faltantes (categorias/arbol,
inventory/parametros), todo dentro del patron **router / service /
repository / schemas** y la separacion **async SQLAlchemy 2.0** (modulos
nuevos) vs **sync legacy** (modulos existentes que la fase 1+ migra
gradualmente). La coexistencia con CSS plano del MVP se mantiene
segun ADR-0006.

**Resultado de tests:** 247 passing (238 baseline + 9 nuevos), 12 skipped
(Mailpit / Postgres-only). 0 regresiones.

## 2. Cambios realizados

### 2.1 Backend (modulos nuevos)

| Archivo | Tipo | Lineas | Proposito |
|---|---|---|---|
| `apps/api/app/modules/proveedores/router.py` | Nuevo | 80 | CRUD + filtro ?activo= |
| `apps/api/app/modules/proveedores/service.py` | Nuevo | 178 | Logica de unicidad (nombre, RUT) + soft delete |
| `apps/api/app/modules/proveedores/schemas.py` | Nuevo | 75 | Pydantic: Create/Update/Response |
| `apps/api/app/modules/proveedores/__init__.py` | Modificado | 16 | Docstring del modulo |
| `apps/api/app/modules/reports/router.py` | Nuevo | 88 | /ejecutivo + placeholders /inventario\|/transferencias\|/historial |
| `apps/api/app/modules/reports/service.py` | Nuevo | 244 | Calculo de KPIs en SQL (sin N+1) |
| `apps/api/app/modules/reports/schemas.py` | Nuevo | 95 | EjecutivoSnapshot + TopProducto + ValorPorBodega |
| `apps/api/app/modules/reports/__init__.py` | Modificado | 16 | Docstring del modulo |
| `apps/api/app/modules/notificaciones/router.py` | Nuevo | 95 | /notificaciones (in-app) + marcar leidas |
| `apps/api/app/modules/notificaciones/service.py` | Nuevo | 138 | CRUD con scope por user + idempotencia |
| `apps/api/app/modules/notificaciones/schemas.py` | Nuevo | 33 | NotificacionResponse + NotificacionCount |
| `apps/api/app/modules/notificaciones/__init__.py` | Nuevo | 12 | Docstring del modulo |
| `apps/api/app/db/models/notificaciones.py` | Nuevo | 78 | SQLAlchemy: Notificacion + NotificationType enum |

### 2.2 Backend (modulos extendidos)

| Archivo | Tipo | Cambio |
|---|---|---|
| `apps/api/app/modules/categories/router.py` | +13 | Endpoint `GET /categories/arbol` |
| `apps/api/app/modules/categories/service.py` | +67 | `get_arbol()` con conteos + filtrado activo |
| `apps/api/app/modules/categories/repository.py` | +27 | `list_all()`, `count_subcategorias()`, `count_productos()` |
| `apps/api/app/modules/categories/schemas.py` | +30 | `CategoryNode` recursivo |
| `apps/api/app/modules/inventory/router.py` | +57 | `PUT /inventory/parametros/{producto_id}/{bodega_id}` |
| `apps/api/app/modules/inventory/service.py` | +55 | `upsert_stock_parameters()` + `StockParametersView` |
| `apps/api/app/modules/inventory/repository.py` | +30 | `upsert_stock_parameters()` |
| `apps/api/app/modules/inventory/schemas.py` | +36 | `StockParametersUpsert` + `StockParametersResponse` |
| `apps/api/app/core/errors.py` | +50 | `ProveedorNotFoundError`, `DuplicateProveedorNombreError`, `DuplicateProveedorRutError`, `NotificationNotFoundError`, `InvalidStockParameterError` |
| `apps/api/app/db/models/__init__.py` | +5 | Registra `Notificacion` + `NotificationType` |
| `apps/api/app/api/router.py` | +15 | Registra `proveedores_router`, `reports_router`, `notificaciones_router` |
| `db/migrations/sqlite/0008_proveedores_notificaciones.sql` | Nuevo | Crea tablas `proveedores` y `notificaciones` + indices |

### 2.3 Frontend (vistas y componentes nuevos)

| Archivo | Tipo | Lineas | Proposito |
|---|---|---|---|
| `apps/web/src/views/CategoriasPage.jsx` | Nuevo | 480 | Arbol colapsable, drawer form, busqueda |
| `apps/web/src/components/ReplenishmentRuleForm.jsx` | Nuevo | 280 | Drawer con SearchSku + bodega + min/max/lead |
| `apps/web/src/components/NotificationsCenter.jsx` | Nuevo | 290 | Campanita + dropdown con polling 30s |
| `apps/web/src/views/ReportsPage.jsx` | Refactor | 700 | Tabs Operacional/Ejecutivo/Auditoria, export PDF |
| `apps/web/src/views/SettingsPage.jsx` | Refactor | 800 | Tabs Reglas/Proveedores/Stock con CRUD completo |
| `apps/web/src/router.jsx` | +3 | Registra `/categorias` |
| `apps/web/src/shell/AppShell.jsx` | +5 | Agrega `NotificationsCenter` al topbar + `/categorias` a nav |
| `apps/web/src/lib/api.js` | +7 | Exporta `putJson()` |

### 2.4 Tests (9 nuevos)

| Archivo | Tests | Cubre |
|---|---|---|
| `apps/api/tests/unit/test_proveedores.py` | 3 | Crear OK, duplicado, listar activos |
| `apps/api/tests/unit/test_reports.py` | 3 | Snapshot completo, alertas criticas, top_n |
| `apps/api/tests/unit/test_categorias_arbol.py` | 3 | Arbol basico, 3 niveles, ocultar inactivos |

## 3. Decisiones de implementacion

### 3.1 Async vs sync en modulos nuevos

Los modulos `proveedores` y `notificaciones` usan **SQLAlchemy 2.0 async**
(igual que `supervisores` y `ordenes_compra`) porque son entidades creadas
en Fase 6+ que no tienen historial legacy. Esto evita:
- doble codepath (sync legacy + async);
- doble set de tests;
- lockups con sqlite3 (sincronico) en Python 3.14.

El modulo `reports` (read-only) tambien usa async para consistencia. La
migracion del legacy de `categories`, `inventory`, etc. es trabajo de
Fase 3+ (ver `aterrizaje-requerimiento-multi-bodega-2026-07-14.md` §9).

### 3.2 PDF ejecutivo: HTML-to-print, no jsPDF

El spec permitia `jsPDF` (~50KB) o HTML imprimible. Implementamos la
segunda: `downloadEjecutivoPDF()` en `ReportsPage.jsx` abre un `window.open`
con HTML estilado y dispara `window.print()`. Cero KB adicionales al bundle,
el browser del usuario hace el layout final. Tradeoff: requiere popup
habilitado, pero es la opcion comun en dashboards ejecutivos.

### 3.3 Notificaciones in-app vs SMTP outbox

Hay 2 sistemas paralelos:
- `email_outbox` (Fase 7): cola async de emails enviada por el worker Arq.
- `notificaciones` (Fase 8): inbox in-app del usuario, polleado cada 30s
  por `NotificationsCenter`.

Ambos se exponen bajo `/api/v1/notificaciones/...` pero los paths son
distintos (`/outbox` para el primero, `/`, `/{id}/marcar-leida` para el
segundo). FastAPI matchea por path, no por prefix. Esto evita proliferar
URLs y mantiene el contrato del spec literal.

### 3.4 Tree de categorias: 1 query + armado en memoria

`GET /categories/arbol` carga TODAS las categorias en una sola query
(`list_all()`) y arma el arbol en el service. Las alternativas eran:
- CTE recursivo: 1 query pero mas complejo y DB-specific.
- N queries (padre por nodo): N+1 clasico.

Para volumenes esperados (decenas a cientos de categorias) la opcion
elegida es la mas simple. Si en algun momento hay >10k categorias, revisar.

### 3.5 Edicion inline de stock minimo

`TabStock` permite editar `min_quantity` inline con `<input type=number>`.
El `onBlur` dispara el PUT al backend. La validacion de la regla
(max >= min) NO se valida inline (seria bloqueante para UX); el backend
retorna 422 `invalid_stock_parameter` si viola, y el toast lo muestra.

### 3.6 Coexistencia con CSS plano legacy

ADR-0006: vistas nuevas en Tailwind v3, vistas legacy sin tocar. Esta fase
refactoriza `ReportsPage` y `SettingsPage` (que estaban en CSS plano) a
Tailwind v3 porque son entry points de la nueva funcionalidad de Fase 8.
El resto de vistas legacy (`DashboardPage`, `LoginPage`, `ChatPage`,
`SlottingPage`, `WarehousesPage`, etc.) **siguen con CSS plano intacto**.

## 4. Diagrama de las nuevas vistas

```
                                  +---------------------+
                                  |    AppShell (topbar)|
                                  |  + Notifications    |
                                  +----------+----------+
                                             |
            +-----------------+   +----------+----------+   +------------------+
            | /categorias     |   | /settings           |   | /reports         |
            | CategoriasPage  |   | SettingsPage        |   | ReportsPage      |
            | (arbol)         |   | (tabs)              |   | (tabs + PDF)     |
            +--------+--------+   +----+----+----+-----+   +-----+-----+------+
                     |                |    |    |                   |     |
                     v                v    v    v                   v     v
            GET /categories/   PUT  /inventory/   /proveedores  GET /reports/  /audit
                arbol           parametros/...     CRUD         ejecutivo
                                PATCH              POST/PATCH
                                DELETE             DELETE
                     |                |    |    |                   |
                     v                v    v    v                   v
        +-----------+----------+----+----+----+--+-------------------+
        | app/modules/categories|  |  inventory  |   proveedores    reports
        |   service.get_arbol   |  | .upsert_..  |   service CRUD    service
        +-----------------------+  +-------------+   (async)         (async SQL)
                                   +-------------+

        +--------------------+
        |  /notificaciones   |  (in-app, polling 30s)
        |  NotificationsCenter
        +---------+----------+
                  |
                  v
        GET/POST /notificaciones/...
        (modulo notificaciones, async SQL, tabla `notificaciones`)
```

## 5. Como correr los tests

### 5.1 Backend

```bash
cd apps/api
# Tests unit + integration (excluye E2E manual):
export DATABASE_URL="sqlite+aiosqlite:///:memory:"
export ENVIRONMENT=development
export JWT_SECRET="__TEST_JWT_SECRET_PLACEHOLDER_32_CHARS__"
export REDIS_URL="redis://localhost:6379/0"
python -m pytest tests/unit/ tests/integration/

# Solo los tests nuevos de Fase 8:
python -m pytest tests/unit/test_proveedores.py tests/unit/test_reports.py tests/unit/test_categorias_arbol.py -v
```

Resultado esperado:
```
247 passed, 12 skipped in ~60s
```

Los 12 skipped son:
- 1 demo warehouse types (skipped intencionalmente).
- 1 Postgres-only (test_concurrent_postgres).
- 3 schema constraints (SQLite async limita FKs).
- 7 Mailpit (SMTP tests requieren `docker compose up mailpit`).

### 5.2 Frontend

```bash
cd apps/web
npm run build
```

Resultado esperado: bundle 459KB (gzip 122KB). El build incluye:
- 7 vistas legacy (CSS plano).
- 11 vistas nuevas (Tailwind v3, incluye las 5 de Fase 8).
- 2 componentes nuevos (`ReplenishmentRuleForm`, `NotificationsCenter`).
- 1 componente legacy (`ReplenishmentRuleForm` en `forms/` con CSS plano)
  que YA NO se usa porque `SettingsPage` consume el de `components/`.

## 6. Riesgos conocidos

1. **HTML-to-print requiere popup habilitado**: `downloadEjecutivoPDF()`
   usa `window.open()`. Si el usuario tiene popups bloqueados, vera un
   mensaje. Mitigacion: futuro fallback server-side con `reportlab`
   (Fase 9+).

2. **Polling de notificaciones cada 30s**: si el usuario tiene la UI
   abierta por horas, hara ~2880 requests/dia al endpoint. Es aceptable
   para el volumen actual; en Fase 9 (Observabilidad) se puede cambiar
   a SSE o WebSocket.

3. **Edicion inline del stock minimo**: el `onBlur` puede generar
   requests en cascada si el usuario tabula rapido. El backend
   valida atomicidad con el constraint CHECK; no hay race condition
   entre usuarios distintos porque es un UPDATE de una fila.

4. **Tree de categorias en memoria**: si crece a >10k nodos, el armado
   del arbol en `service.get_arbol` puede ser lento. Por ahora OK.

5. **NotificationsCenter + polling**: si el usuario navega entre tabs
   rapidamente, puede haber N requests en vuelo. La implementacion
   actual no aborta (es GET, no hace falta), pero en Fase 9+ se
   puede agregar `AbortController`.

## 7. Proximos pasos (Fase 9: Observabilidad)

Segun `aterrizaje-requerimiento-multi-bodega-2026-07-14.md` §9:

- **Logs JSON estructurados** via structlog en todos los modulos.
  Los modulos nuevos ya usan `get_logger()` (Fase 7); los legacy
  pendientes.
- **Metricas Prometheus** via `prometheus-fastapi-instrumentator`
  (ya instalado en `pyproject.toml`). Falta custom metricas:
  - `notifications_pending_count` (por usuario).
  - `report_ejecutivo_duration_seconds` (histograma).
  - `categories_tree_size` (gauge).
- **Healthcheck enriquecido** con checks de DB, Redis, Arq worker,
  email_outbox. (El test `test_healthcheck_returns_ok` ya falla
  porque el shape cambio en algun momento; es un bug pre-existente
  que la Fase 9 cierra.)
- **SSE / WebSocket** para reemplazar el polling de notificaciones.
- **PDF server-side** como fallback del HTML-to-print cuando los
  popups esten bloqueados.

Ademas:
- El CRUD de `notificaciones` todavia NO se dispara automaticamente
  desde `SolicitudService` / `OrdenCompraService`. La UI las crea
  via tests o manualmente. Pendiente: hookear la creacion en
  los services existentes (Fase 8+ si se requiere).
- Las 10 fallas pre-existentes en `tests/test_api.py` (no relacionadas
  con Fase 8) requieren correccion de la shape del healthcheck.
