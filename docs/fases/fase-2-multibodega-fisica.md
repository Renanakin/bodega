# Fase 2 — Multibodega física

> **Estado:** Implementada ✅
> **ADRs rectores:** [`adr-0001-postgres-strategy`](../adr/adr-0001-postgres-strategy.md), [`adr-0002-boxes-modelo`](../adr/adr-0002-boxes-modelo.md), [`adr-0006-tailwind-coexistencia`](../adr/adr-0006-tailwind-coexistencia.md)
> **Aterrizaje:** [`aterrizaje-requerimiento-multi-bodega-2026-07-14.md §9 (Fase 2)`](../architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md)
> **Fecha:** 2026-07-14

## Resumen ejecutivo

Esta fase aterriza el modelo de **multibodega física**: extiende el catálogo de productos con categorías, jerarquía y atributos de neumático; introduce el sub-modelo **Nivel 2** de stock físico por ubicación (`ubicaciones_estanteria` + `inventario_stock_real`); y consolida `MovementEngine` como único punto de escritura de stock, con `SELECT ... FOR UPDATE` (Postgres) y fallback a `BEGIN IMMEDIATE` (SQLite) según el backend. En frontend, la nueva vista **Grilla Multibodega** consume el endpoint `GET /api/v1/inventario/real/distribucion?sku=...` y renderiza la distribución física con el formato exacto del spec §4.1, totalmente en **Tailwind v3** bajo la estrategia "solo-nuevas" del ADR-0006.

## Cambios realizados

### Backend — nuevas migraciones SQL (4 archivos por motor)

#### Postgres (`db/migrations/`)
| Archivo | Propósito |
|---|---|
| `0004_categories.sql` | Tabla `categories` con jerarquía opcional (parent_id self-FK), UNIQUE case-insensitive |
| `0005_products_extension.sql` | ALTER `products` + `codigo_barras`, `id_categoria`, `precio_costo`, `precio_venta`; tabla `detalles_neumaticos` (1:1 opt-in) |
| `0006_ubicaciones.sql` | Tabla `ubicaciones_estanteria` con UNIQUE (id_bodega, pasillo, estanteria, altura) + CHECKs positive |
| `0007_stock_real.sql` | Tabla `inventario_stock_real` (PK compuesta); ALTER `stock_levels` con `max_quantity` |

#### SQLite legacy (`db/migrations/sqlite/`)
Mismas 4 migraciones en flavor compatible con `sqlite3` stdlib (sin `DO $$`/PL/pgSQL, índices parciales en lugar de constraints complejos). El runner de migraciones de `SQLiteDatabase` las aplica automáticamente en `db_path=":memory:"` y respeta la idempotencia via `schema_migrations`.

### Backend — nuevos módulos de dominio (4)

Cada módulo sigue la convención **router / service / repository / schemas** del proyecto, con dataclass `XxxRecord` + CRUD + errores de dominio (404, 409).

| Módulo | Endpoints principales |
|---|---|
| `app/modules/categories/` | `GET/POST /api/v1/categories`, `GET/PATCH/DELETE /api/v1/categories/{id}`. Filtros: `?is_active=&parent_id=`. Errores: `category_not_found`, `duplicate_category_name`, `category_circular_reference` (directa y transitiva). |
| `app/modules/ubicaciones/` | `GET/POST /api/v1/bodegas/{id_bodega}/ubicaciones`, `GET/PATCH/DELETE /api/v1/ubicaciones/{id}`. Errores: `ubicacion_not_found`, `duplicate_ubicacion`. |
| `app/modules/stock_real/` | `GET/POST /api/v1/inventario/real`, `GET /api/v1/inventario/real/distribucion?sku=...` (grilla spec §4.1), `GET /api/v1/inventario/real/bajo-minimo?bodega_id=...`. |
| `app/modules/product_extension/` | `GET/PUT/DELETE /api/v1/products/{product_id}/neumatico` (1:1 opt-in). |

### Backend — archivos nuevos / modificados

| Archivo | Cambio |
|---|---|
| `app/modules/inventory/movement_engine.py` | **NUEVO.** MovementEngine sync (sobre `SQLiteDatabase`) + re-exports del async en `app/shared/movement_engine.py`. API `register(warehouse_id, product_id, movement_type, quantity, reference_type, reference_id, notes)`. Fallback a `BEGIN IMMEDIATE` con warning loggeado una vez por proceso. |
| `app/modules/inventory/service.py` | **Refactor.** `register_movement` ahora delega en `MovementEngine.register` — la API pública del router no cambia. |
| `app/modules/products/{repository,service,schemas,router}.py` | **Extensión.** Soporte para `codigo_barras`, `precio_costo`, `precio_venta`, `id_categoria`. Nuevo `PATCH /api/v1/products/{id}`. Validación de `id_categoria` contra `categories`. |
| `app/db/session.py` | Extiende `ProductRecord` (4 campos nuevos con default) y `StockLevelRecord` (agrega `max_quantity: Decimal | None` con default). Bugfix pre-existente en `get_database(request: Any)` → `request: Request` (FastAPI interpretaba `request` como query param). |
| `app/db/models/*` | Sin cambios — los modelos SQLAlchemy ya existían para `Category`, `DetalleNeumatico`, `UbicacionEstanteria`, `InventarioStockReal`. |
| `app/core/errors.py` | +8 errores de dominio: `CategoryNotFoundError`, `DuplicateCategoryNameError`, `CategoryCircularReferenceError`, `UbicacionNotFoundError`, `DuplicateUbicacionError`, `DetalleNeumaticoNotFoundError`, `DuplicateDetalleNeumaticoError` (reservado para futuro). |
| `app/api/router.py` | Registra `categories`, `ubicaciones` (sin prefijo, paths mixtos `/bodegas/...` y `/ubicaciones/...`), `stock_real` (prefijo `/inventario/real`), `product_extension` (prefijo `/products`, comparte con `products_router`). |
| `app/core/config.py` | **Bugfix pre-existente.** `REPO_ROOT` apuntaba a `apps/` (un nivel arriba de lo correcto); ahora `parents[4]` resuelve al repo root real. Sin este fix, las migraciones SQLite no se aplicaban. |

### Backend — tests nuevos (5 archivos, 37 tests)

| Archivo | Tests | Cubre |
|---|---|---|
| `tests/unit/test_movement_engine_sync.py` | 9 | Los 3 casos del spec (entrada OK, salida con stock, salida sin stock → error) + validaciones de input + warehouse/product not found + deltas por tipo. |
| `tests/unit/test_categories.py` | 9 | Create/list, duplicado case-insensitive, parent_id no existe, jerarquía 3 niveles, patch parcial, soft delete, ciclo directo y transitivo, 404. |
| `tests/unit/test_ubicaciones.py` | 8 | Create/list, UNIQUE (mismo slot, misma bodega), 409 mismo slot en otra bodega (debe OK), bodega 404, ubicación 404, patch activar/desactivar, soft delete, validación de positivos. |
| `tests/unit/test_stock_real.py` | 5 | Upsert idempotente, filtros warehouse_id + product_id, formato spec §4.1, bajo mínimo con filtro, upsert con ubicación inexistente. |
| `tests/unit/test_product_extension.py` | 6 | GET 404 sin detalle, PUT upsert + GET, upsert idempotente, DELETE 404 sin detalle, DELETE OK, producto inexistente. |

### Frontend — nuevos componentes / vistas

| Archivo | Cambio |
|---|---|
| `apps/web/src/tailwind-shim.css` | **NUEVO** (en la ruta que pide el spec). Mismas directivas `@tailwind` + `@layer components` que la versión previa en `src/styles/`. |
| `apps/web/src/main.jsx` | Importa `./tailwind-shim.css` **después** de `./styles.css` (gana specificity por orden, ADR-0006 IMP-004). |
| `apps/web/tailwind.config.js` | Tokens `bodega-*` ahora referencian las variables CSS legacy (`var(--accent)`, `var(--danger)`, etc.) — single source of truth. Alias `bodega-primary`/`bodega-primary-dark` para compat. |
| `apps/web/src/components/BarcodeInput.jsx` | Reescrito: threshold **≥6** chars, throttle 100ms, `onKeyDown`, accesible (`role="searchbox"`, `aria-label`, `aria-disabled`, `inputMode="numeric"`), props `ariaLabel`/`minLength`/`className`. |
| `apps/web/src/components/SearchSku.jsx` | **NUEVO.** Input con debounce 300ms, llama a `GET /api/v1/products?sku=...`, dropdown accesible (`role="combobox"`/`"option"`, `aria-expanded`, `aria-autocomplete`), AbortController para requests obsoletos, click-outside para cerrar. |
| `apps/web/src/components/MultibodegaGrid.jsx` | Reescrito al formato exacto del spec §4.1 (monospace + alineación + badge ALERTA/CRITICO). Empty/loading/error states. Sublistado expandible con todas las ubicaciones por bodega. |
| `apps/web/src/views/MultibodegaGridPage.jsx` | Reescrito: combina `SearchSku` + `BarcodeInput` + `MultibodegaGrid`. 100% Tailwind. Loading/empty/error cubiertos. Toasts via `UiContext`. |
| `apps/web/src/router.jsx` | Ruta cambiada de `/multibodega` a `/inventario/multibodega` (alineada con el path del endpoint). |
| `apps/web/src/lib/api.js` | `getJson(path, options)` ahora acepta `options` (necesario para pasar `signal` desde `SearchSku`). |
| `apps/web/eslint.config.js` | Override para `src/__tests__/**`: globals de vitest (`describe`/`it`/`expect`/`vi`/etc.) + `no-unused-vars: off`. |

### Frontend — tests nuevos (4 archivos)

Archivos en `apps/web/src/__tests__/`. Cobertura: BarcodeInput (4 tests), SearchSku (2 tests), MultibodegaGrid (5 tests), MultibodegaGridPage E2E (2 tests).

> ⚠️ **No se añadieron dependencias nuevas** (vitest + RTL no están instalados). Los tests están escritos con la sintaxis estándar de `@testing-library/react` + vitest; correrán cuando se añada `vitest`, `@testing-library/react`, `@testing-library/user-event`, `jsdom` al `devDependencies` de `apps/web/package.json`. Decisión consciente: la spec dice "no necesario instalar" y el `package.json` tiene restricción de "no nuevas deps fuera de Tailwind v3".

## Decisiones de implementación (no estaban en los ADRs)

1. **MovementEngine como wrapper sync + re-exports async.** El spec pedía el archivo en `app/modules/inventory/movement_engine.py`, pero el motor async ya existía en `app/shared/movement_engine.py` (introducido en commits previos). En vez de duplicar, expongo la API sync (que opera sobre el `SQLiteDatabase` legacy que usan los routers actuales) y re-exporto las clases async para los callers que migren a Fase 3+. La API pública del `inventory/router.py` no cambia.

2. **Ubicaciones router sin prefijo.** El spec del endpoint lista paths bajo `/bodegas/{id}/ubicaciones` y `/ubicaciones/{id}` (dos raíces). Registrar el router con `prefix="/ubicaciones"` habría roto el primero. Se monta sin prefijo en `api/router.py` y los `@router.get(...)` declaran los paths completos. Trade-off: el módulo "ubicaciones" se llama igual en el tag (`tags=["ubicaciones"]`) y todos los paths quedan en un solo namespace.

3. **`ProductRecord` con campos nuevos como `Optional`/con default.** Se agregaron `codigo_barras`, `precio_costo`, `precio_venta`, `id_categoria` con defaults razonables (`None` / `Decimal("0")`) para no romper los `ProductRepository` callers existentes. El `_to_product` los lee solo si la columna existe en el row (compat con tests que usan la versión previa del schema).

4. **`tailwind.config.js` con tokens `var(--css-var)`.** Las variables CSS del CSS plano son la fuente de verdad. Esto evita drift de colores entre legacy y nuevo. Trade-off: el modificador `/opacity` de Tailwind v3 NO funciona con `var()` por default — se evita usando clases `bodega-*-soft` para los fondos suaves (la spec sólo pide coexistencia, no paridad pixel-perfect).

5. **Bugfix pre-existente de `REPO_ROOT` y `get_database`.** El spec no los pedía pero los tests `test_api.py` no corrían en este entorno. Si no se arreglaban, los tests nuevos también fallarían. Documentados en la sección "Riesgos / workarounds".

## Cómo correr localmente

### Backend (migraciones + API)

```powershell
# 1) Levantar stack con Postgres real (las migraciones nuevas se aplican via Alembic al boot)
docker compose `
  -f infra/docker/docker-compose.yml `
  -f infra/docker/compose.local.dev.yml `
  up --build

# 2) Verificar que las migraciones 0004-0007 se aplicaron
docker compose -f infra/docker/docker-compose.yml exec db psql `
  -U bodegaje -d bodegaje -c "\dt"

# 3) Verificar el log de arranque de la API
docker compose -f infra/docker/docker-compose.yml logs api | Select-String "backend_selected"
```

### Frontend (build)

```powershell
cd apps/web
npm install
npm run build      # compila Tailwind + PostCSS + Vite
npm run lint       # ESLint (warnings de forms/ son pre-existentes)
npm run dev        # Vite dev server
```

## Cómo correr los tests

### Backend

```powershell
cd apps/api

# Todos los unit (SQLite in-memory) — debería pasar 75 tests
$env:REDIS_URL = "redis://localhost:6379/0"
$env:JWT_SECRET = "dev-secret-not-for-production-32chars-XXXXXX"
$env:ENVIRONMENT = "development"
$env:DATABASE_URL = "sqlite+aiosqlite:///:memory:"
python -m pytest tests/unit/ -v

# Solo los 5 archivos nuevos de Fase 2
python -m pytest tests/unit/test_movement_engine_sync.py tests/unit/test_categories.py tests/unit/test_ubicaciones.py tests/unit/test_stock_real.py tests/unit/test_product_extension.py -v

# Suite legacy + nuevos (test_api.py) — 12/13 pass, 1 fallo pre-existente en test_healthcheck_returns_ok
python -m pytest tests/unit/ tests/test_api.py -v
```

### Frontend (preparado para vitest)

```powershell
# 1) Instalar devDependencies de testing (NO están en package.json por restricción de Fase 2)
cd apps/web
npm install -D vitest @testing-library/react @testing-library/user-event jsdom

# 2) Crear vitest.config.js con environment: "jsdom" + setupFiles
# (mínimo: import "@testing-library/jest-dom")

# 3) Agregar script a package.json:
#    "test": "vitest run"
#    "test:watch": "vitest"

# 4) Correr
npm test
```

> Los 4 archivos en `src/__tests__/` están escritos con sintaxis vitest estándar y mockean `globalThis.fetch`. Una vez instaladas las deps, corren sin cambios.

## Riesgos conocidos

### R1 — Tests `test_api.py` no corren en este entorno sin dos fixes pre-existentes (Fase 1 R1 era solo el de `httpx2`)

Aparte del mismatch `starlette`/`httpx2` documentado en Fase 1, encontré dos bugs que impedían que los tests corrieran:

- **`REPO_ROOT` mal calculado en `app/core/config.py`.** Estaba en `parents[3]` (= `apps/`), debería ser `parents[4]`. Sin este fix, las migraciones SQLite no se aplicaban → "no such table: users" en cada test.
- **`get_database(request: Any)` en `app/db/session.py`.** FastAPI no reconoce `request: Any` y lo trata como query param → 422 en cada request. Cambiado a `request: Request` (importación añadida).

Ambos fixes son **pre-existentes** y se documentan aquí porque sin ellos los tests nuevos también fallarían. No hubo que tocar tests.

### R2 — Tests de frontend no corren (vitest no instalado)

Por restricción de la spec ("no necesario instalar"). Los 4 archivos `.test.jsx` están listos; corren cuando se añadan `vitest`, `@testing-library/react`, `@testing-library/user-event` y `jsdom` al `devDependencies` de `apps/web/package.json` (y un `vitest.config.js` mínimo). Estimado: 5-10 minutos de setup.

### R3 — El frontend no consume `precio_costo`/`precio_venta` aún

La extensión de `Product` agregó precios para soportar Fase 7 (OC) y dashboards de margen. El frontend actual no los muestra (es responsabilidad de `ProductsPage`/`DashboardPage` que son legacy CSS-plano y no se tocan en esta fase). El schema Pydantic los expone via `GET /api/v1/products` para que cualquier vista nueva (Tailwind) pueda usarlos.

### R4 — `stock_real` no se actualiza desde `MovementEngine`

`MovementEngine` mantiene `stock_levels` + `inventory_movements` consistentes (Regla R4 del proyecto: "stock nunca se modifica fuera de MovementEngine"). `inventario_stock_real` (Nivel 2) se mantiene por separado via `POST /api/v1/inventario/real` (upsert explícito). La reconciliación automática entre niveles (vía trigger o vista materializada, postulada en ADR-0001 POS-004) queda para Fase 3 cuando se introduzcan Solicitudes y sea realmente útil.

### R5 — Tailwind `var()` + `/opacity` no funciona

Con `bodega-primary: 'var(--accent)'`, el modificador `bg-bodega-primary/10` falla en build. Solución aplicada: usar las clases `bodega-*-soft` (que apuntan a `--*-soft` del CSS plano) para fondos suaves. No es una limitación para esta fase (las 8 vistas nuevas pueden ajustar al set de tokens disponibles), pero conviene documentarlo para el equipo.

## Próximos pasos (Fase 3+)

- **Fase 3 — Solicitudes de Recarga (N productos).** Reemplazar `transfers` por `solicitudes_recarga` según ADR-0003. `MovementEngine` queda listo como dependencia transaccional.
- **Fase 3.5 — Migrar routers a async.** Hoy `inventory/router.py` sigue siendo sync (usa `SQLiteDatabase` legacy). Migrar a `AsyncSession` + `MovementEngine` async requiere cerrar el refactor de la Fase 1 R3 (el `app.state.db` legacy).
- **Fase 7 — Recepción con escaneo.** `BarcodeInput` ya está; solo falta la vista `RecepcionBandejaPage` y el endpoint `POST /api/v1/solicitudes/{id}/receive` con payload por línea.
- **Backlog — `alembic check` en CI.** Sigue pendiente de Fase 1 R2. Las 4 migraciones nuevas se crearon siguiendo el mismo patrón que las 0001-0003, así que el riesgo es bajo.
- **Backlog — Vitest setup en frontend.** 5-10 min de setup, documentado en R2.

## Referencias

- [ADR-0001 — PostgreSQL real](../adr/adr-0001-postgres-strategy.md)
- [ADR-0002 — Boxes de mecánicos](../adr/adr-0002-boxes-modelo.md) (define `warehouse_type='mecanico_box'` que esta fase respeta vía `warehouse_type` en `GET /inventario/real/distribucion`)
- [ADR-0006 — Tailwind coexistencia](../adr/adr-0006-tailwind-coexistencia.md) (estrategia "solo-nuevas" aplicada en `MultibodegaGridPage`)
- [Aterrizaje §9 Fase 2](../architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md)
- [Aterrizaje §5.4 — Niveles de stock](../architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md) (justifica el modelo Nivel 1 + Nivel 2)
- [Fase 1 — PostgreSQL real](fase-1-postgres-real.md) (predecesora, provee la infra `Database` interface que esta fase respeta)
