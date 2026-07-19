# Auditoría de código — Fases 1 y 2 (Bodegaje)

**Fecha:** 2026-07-14
**Alcance:** `apps/api/` + `apps/web/` + `db/migrations/` (Postgres y SQLite)
**ADRs vigentes:** 0001, 0002, 0003, 0004, 0005, 0006
**Documentos de fase:** `docs/fases/fase-1-postgres-real.md`, `docs/fases/fase-2-multibodega-fisica.md`
**Auditor:** rol Code Auditor (sin modificaciones; solo reporte)

---

## Resumen ejecutivo

### Veredicto: **NECESITA AJUSTES MENORES (con un 🔴 crítico pendiente)**

El código entregado en Fase 1 (Postgres real + interface `Database` + tests integration con testcontainers) y Fase 2 (multibodega física: 4 módulos nuevos, MovementEngine sync/async, BarcodeInput/SearchSku/MultibodegaGrid frontend) cumple la *intención* de los 6 ADRs vigentes y mantiene una arquitectura limpia **a nivel de los nuevos módulos**. La separación `router → service → repository` se respeta; los `Pydantic schemas` validan inputs; los errores de dominio están tipados; los `Print` están prohibidos (validado por `test_logging.py::TestNoPrintStatements`).

Sin embargo, el "doble fuente de verdad" del schema (modelos SQLAlchemy vs migraciones SQL SQLite) está generando **bugs latentes** que la suite de tests no detecta porque gran parte de los CHECKs/FKs de Fase 1+2 se skipean en SQLite. La cobertura de **concurrencia real con `SELECT FOR UPDATE` en Postgres** — pieza angular del ADR-0001 — está **skipeada con `pytest.skip()`** y no se valida; el `MovementEngine` async que sí usa `with_for_update()` nunca se ejecuta contra Postgres en CI.

### 5 hallazgos críticos (resumen)

1. 🔴 **Migraciones SQLite 0001-0003 NO reflejan ADR-0002** — falta `parent_warehouse_id` y los CHECKs `chk_warehouses_type_valid` / `parent_warehouse_required_for_box` en `db/migrations/sqlite/0001` y `0002`. El `app/db/demo.py` usa `warehouse_type='central'/'sucursal'` que viola el modelo nuevo. Tests pasan silenciosamente porque SQLite legacy no tiene esos CHECKs.
2. 🔴 **Tests de concurrencia real en Postgres son `pytest.skip()` puros** — `test_concurrent_movement_engine.py:31-50` declara los 2 tests críticos y los salta sin implementación. La promesa del ADR-0001 ("concurrencia real con `SELECT FOR UPDATE`") **no está validada por test**.
3. 🔴 **`LoginPage.jsx` (legacy, pero vivo) pre-carga `demo123` y muestra las 4 credenciales en la UI** — riesgo de seguridad severo, no mitigado por código de Fase 1/2.
4. 🔴 **`MovementEngine._immediate_transaction` accede a `self._db._connection` saltando el `RLock`** de `SQLiteDatabase` — race condition residual en concurrencia sync. Documentado como "writer lock" pero **no lo es**: cualquier otro writer que llame `db.execute()` por fuera del motor entra a la misma conexión sin lock.
5. 🔴 **`apps/api/app/modules/inventory/multibodega.py` (Fase 6) tiene un query estructuralmente roto** — `InventarioStockReal := UbicacionEstanteria` dentro de un `select()` con comentario walrus; `ubicaciones=[]` hardcodeado. Aunque el módulo no está en el router principal, demuestra copy-paste descuidado y código muerto en `app/`.

---

## Hallazgos detallados

### 1. Calidad de código

#### 🔴 [C-1] Migraciones SQLite desactualizadas con respecto al modelo
**Archivos:** `db/migrations/sqlite/0001_inventory_mvp.sql`, `db/migrations/sqlite/0002_transfers_workflow.sql`, `db/migrations/sqlite/0003_auth_and_audit.sql`
**Evidencia:**
```sql
-- sqlite/0001_inventory_mvp.sql
CREATE TABLE IF NOT EXISTS warehouses (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    warehouse_type TEXT NOT NULL,    -- sin CHECK; acepta "central"/"sucursal"
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
-- NO tiene: parent_warehouse_id, CHECK de tipo, CHECK de box
```
Comparado con `app/db/models/warehouses.py:20-31`:
```python
__table_args__ = (
    CheckConstraint(
        "warehouse_type IN ('principal', 'auxiliar', 'mecanico_box')",
        name="warehouse_type_valid",
    ),
    CheckConstraint(
        "(warehouse_type IN ('principal', 'auxiliar') AND parent_warehouse_id IS NULL) "
        "OR (warehouse_type = 'mecanico_box' AND parent_warehouse_id IS NOT NULL)",
        name="parent_warehouse_required_for_box",
    ),
)
```
Y `app/db/demo.py:50-53` usa `warehouse_type="central"/"sucursal"` que **violan el CHECK** del modelo nuevo.

**Impacto:** tests pasan en SQLite (no enforza CHECKs), pero `reset_demo_database()` fallará si se corre contra el modelo actual; cualquier test que cree un `Warehouse` con `warehouse_type='central'` vía SQLAlchemy fallará con `IntegrityError` no en SQLite.
**Fix:** regenerar las 3 migraciones SQLite espejo (o cambiar `_apply_migrations` para usar `Base.metadata.create_all`); actualizar `demo.py` a `'principal'/'auxiliar'`.

#### 🟠 [C-2] `MultibodegaGrid` frontend: ningún test pasa efectivamente
**Archivo:** `apps/web/src/__tests__/MultibodegaGrid.test.jsx:1-7`
```jsx
/**
 * Requiere: vitest + @testing-library/react + jsdom.
 * (No instalados todavía por restricción de Fase 2 — ver doc de la fase.)
 */
```
**Evidencia:** `package.json` (verificado via `apps/web/package.json` en doc de Fase 2 R2) no incluye `vitest`. Los 4 archivos de tests están escritos pero **no se ejecutan** — el doc de Fase 2 R2 lo reconoce pero no resuelve.

**Impacto:** las aserciones del formato spec §4.1 no se validan. Si alguien rompe el layout, nadie se entera hasta QA manual.
**Fix:** añadir `vitest + @testing-library/react + @testing-library/user-event + jsdom` a `devDependencies` (5-10 min, ya estimado por la doc). Ejecutar `npm test` en CI `lint-frontend` (que ya hace `npm run lint && npm run build`).

#### 🟠 [C-3] `multibodega.py` (Fase 6) tiene query roto y código muerto
**Archivo:** `apps/api/app/modules/inventory/multibodega.py:90-95, 121`
```python
ub_stmt = (
    select(InventarioStockReal := UbicacionEstanteria, UbicacionEstanteria, StockLevel)  # type: ignore[misc]
    .join(StockLevel, UbicacionEstanteria.id_bodega == StockLevel.warehouse_id)
    .where(StockLevel.product_id == producto.id)
)
# Nota: para Fase 6+, cuando se llene inventario_stock_real, esta query devolvera datos.
...
bodegas_view.append(
    DistribucionPorBodega(
        ...
        ubicaciones=[],  # Se llenara cuando inventario_stock_real se use (Fase 6+)
    )
)
```
**Evidencia:** la asignación `InventarioStockReal := UbicacionEstanteria` es un walrus operator que no es la intención del programador; el FROM no incluye `inventario_stock_real` (la tabla que debería alimentar el Nivel 2). Y la lista `ubicaciones=[]` siempre está vacía.
**Impacto:** código no usado (no está en `api/router.py`), pero es **code-rot** que el próximo developer va a "arreglar" pensando que funciona. Sugiere confusión entre el `stock_real/` de Fase 2 (que SÍ funciona) y este.
**Fix:** eliminar el archivo o marcarlo claramente como "deprecated, use `stock_real/service.py`". 

#### 🟠 [C-4] `products/router.py:44` accede a `service._repository` directamente
**Archivo:** `apps/api/app/modules/products/router.py:43-47`
```python
if sku is not None:
    normalized = sku.strip().upper()
    product = service._repository.get_by_sku(normalized)  # noqa: SLF001
    return [product] if product is not None else []
```
**Evidencia:** acceso a atributo privado del service con `noqa`. Indica que la API de `ProductService` no expone `get_by_sku`, por lo que el router la bypasea.
**Impacto:** el método `list_products(sku=...)` del service no se usa; acoplamiento fuerte router→repository. Si el día de mañana el filtro de SKU se vuelve case-insensitive, hay que tocar el router.
**Fix:** añadir `get_product_by_sku(sku)` al service (también arregla bug de filtro — ver [C-5]).

#### 🟠 [C-5] Filtro `?sku=` en `GET /products` hace match EXACTO, no búsqueda
**Archivo:** `apps/api/app/modules/products/router.py:42-47`
**Evidencia:** `service._repository.get_by_sku(normalized)` retorna un único producto (o ninguno). El `SearchSku` frontend hace un debounce y muestra dropdown — pero el backend solo matchea exact.
**Impacto:** un usuario que escribe "ACE" no encuentra "ACE-001". El dropdown del frontend se ve "vivo" pero solo retorna resultados cuando se escribe el SKU completo.
**Fix:** implementar `LIKE 'ACE%'` o `ILIKE 'ACE%'` (Postgres) en el repository. O usar `search_products(query, limit=10)`.

#### 🟡 [C-6] Docstrings presentes en 100% de funciones públicas de Fase 2
**Evidencia:** verificado en `categories/`, `ubicaciones/`, `stock_real/`, `product_extension/`, `MovementEngine`. Todos los archivos tienen module docstring + docstrings en clases/métodos públicos. ✅
**Único faltante:** `app/modules/inventory/movement_engine.py:326` `_cm` es un inner context manager sin docstring (es interno, aceptable).

#### 🟡 [C-7] Función `_to_warehouse`, `_to_product`, etc. en repositories son pequeñas (<15 líneas)
✅ Los repositorios tienen `_to_xxx(row)` helpers consistentes; no hay funciones > 50 líneas en los 4 módulos nuevos de Fase 2.

---

### 2. Seguridad

#### 🔴 [S-1] `LoginPage.jsx` expone credenciales demo en la UI
**Archivo:** `apps/web/src/views/LoginPage.jsx:13, 67-70`
```jsx
const [password, setPassword] = useState("demo123");
...
<div>`admin` / `demo123`</div>
<div>`supervisor` / `demo123`</div>
<div>`origen` / `demo123`</div>
<div>`destino` / `destino` / `demo123`</div>
```
**Evidencia:** el `useState("demo123")` pre-carga la contraseña en texto claro; las 4 credenciales se renderizan en pantalla.

**Impacto:** un usuario que olvida su contraseña la lee en la UI. En un demo comercial está bien; en producción es una fuga de credenciales severa. El demo-tutorial-commercial también las publica en `docs/operations/demo-tutorial-commercial-2026-06-25.md`.
**Fix:** quitar el default de `useState`, y mostrar las credenciales solo si `import.meta.env.DEV` o una flag explícita. **Crítico antes de exponer el sistema públicamente.**

#### 🟠 [S-2] `password_hash_iterations: 120_000` está por debajo de OWASP 2023
**Archivo:** `apps/api/app/core/config.py:88`
```python
password_hash_iterations: int = Field(default=120_000, ge=10_000)
```
**Evidencia:** OWASP Password Storage Cheat Sheet 2023 recomienda ≥600.000 iteraciones para PBKDF2-HMAC-SHA256. 120.000 es ~5x más débil.
**Impacto:** acelera brute-force de hashes robados en ~5x.
**Fix:** subir default a 600_000 (compatible con el código existente; los hashes viejos siguen válidos porque el salt+iterations se recomputan al login).

#### 🟠 [S-3] `app/db/demo.py` y `LoginPage.jsx` usan `demo123` como contraseña universal
**Archivos:** `app/db/demo.py:50-53`, `LoginPage.jsx:13, 67-70`, todos los tests de Fase 2
**Evidencia:** grep de `demo123` en repo: 28 ocurrencias (5 archivos de tests + LoginPage + demo + 1 doc). Cada test inserta un usuario `admin` con `password=demo123`.
**Impacto:** si en una demo se carga `reset_demo_database()` y el operador olvida cambiar la contraseña, el sistema queda con `admin/demo123` en producción.
**Fix:** el seed Python debe generar contraseñas aleatorias por usuario y loguearlas al arranque; en LoginPage, mostrar el username pero no la contraseña (que se asigna en el primer login o se envía por email).

#### 🟢 [S-4] Queries SQL: NO hay SQL injection (todos los `?` van parametrizados)
**Evidencia:** grep de patrones `f".*SELECT"` y `f".*WHERE"` muestra 8 matches en módulos; TODOS usan `?` y `tuple(params)`. Ejemplo `categories/repository.py:59-62`:
```python
where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
rows = self._db.query_all(
    f"SELECT * FROM categories {where} ORDER BY nombre",
    tuple(params),
)
```
**Convención:** segura **mientras** se mantenga la disciplina. No hay `string.format` ni `%` con input del usuario.

#### 🟢 [S-5] Endpoints públicos bien protegidos
**Evidencia:** los 4 routers nuevos usan `Depends(get_current_user)` para GETs y `Depends(require_roles("admin", "supervisor"))` para POST/PATCH/DELETE. Verificado:
- `categories/router.py:57, 85, 103`
- `ubicaciones/router.py:67, 101, 119`
- `stock_real/router.py:58`
- `product_extension/router.py:54, 65`

Solo `AuthService.get_user_by_token` es invocable sin user; eso es correcto (es el bootstrap del auth).

#### 🟢 [S-6] Tokens de aprobación (ADR-0005) bien implementados
**Archivo:** `apps/api/app/core/security.py:107-148`
**Evidencia:** usa `itsdangerous.URLSafeTimedSerializer` con `salt="bodegaje-approval-token"`, `max_age` configurable (default 7 días vía `Settings.approval_token_max_age_days`). `compare_digest` no aplica porque itsdangerous firma HMAC. `BadSignature` y `SignatureExpired` se manejan con errores específicos. ✅

---

### 3. Transacciones y race conditions

#### 🔴 [T-1] `MovementEngine._immediate_transaction` salta el `RLock` de `SQLiteDatabase`
**Archivo:** `apps/api/app/modules/inventory/movement_engine.py:316-318`
```python
conn = self._db._connection  # noqa: SLF001 — intencional, encapsula el detalle
started = not conn.in_transaction
if started:
    ...
    conn.execute("BEGIN IMMEDIATE")
```
**Evidencia:** el `SQLiteDatabase` envuelve la conexión con `RLock` (ver `session.py:531-535`); pero el `_immediate_transaction` accede a `self._db._connection` directamente y emite `BEGIN IMMEDIATE` por su cuenta. **No acquire el RLock.**

**Impacto:** si dos threads llaman a `MovementEngine.register()` concurrentemente sobre la misma `SQLiteDatabase`:
- Thread A hace `conn.execute("BEGIN IMMEDIATE")` → toma el SQLite reserved lock
- Thread B hace `conn.execute("BEGIN IMMEDIATE")` → BLOQUEA (SQLite es single-writer)
- O peor: Thread B pasa por `conn.in_transaction` antes de que A commitee, ve `False`, intenta `BEGIN IMMEDIATE`, se cuelga.

El `RLock` está ahí para serializar los writers a la misma conexión. Bypasearlo es **exactly** el caso de race que el lock previene.
**Fix:** el método `_immediate_transaction` debería llamar a `self._db.transaction()` (que sí usa el RLock) y luego emitir `BEGIN IMMEDIATE` dentro del lock, o cambiar la API de `SQLiteDatabase` para exponer un `begin_immediate()` que use el RLock.

#### 🔴 [T-2] Tests de concurrencia real en Postgres son `pytest.skip()` puros
**Archivo:** `apps/api/tests/integration/test_concurrent_movement_engine.py:31-50`
```python
class TestConcurrentMovementsPostgres:
    @pytest.mark.asyncio
    async def test_50_parallel_in_movements_postgres(
        self, postgres_required
    ) -> None:
        pytest.skip("Implementación específica para Postgres; ver test_sequential_locking")

    @pytest.mark.asyncio
    async def test_no_oversell_postgres(
        self, postgres_required
    ) -> None:
        pytest.skip("Implementación específica para Postgres; ver test_sequential_locking")
```
**Evidencia:** los 2 tests que validan la promesa del ADR-0001 ("concurrencia real con `SELECT FOR UPDATE`") están skipeados con `pytest.skip()` y **no hay test_sequential_locking** al que se refieran. `test_concurrent_postgres.py` existe pero NO usa el `MovementEngine`, hace el `with_for_update()` inline.

**Impacto:** el `MovementEngineAsync.apply()` con `.with_for_update()` (en `app/shared/movement_engine.py:97-104`) **nunca se valida bajo concurrencia real**. El docstring del módulo dice "previene oversell" pero es una afirmación sin evidencia automatizada.
**Fix:** implementar los 2 tests usando `MovementEngine.apply()` directamente con 50 tasks paralelas; o reescribir `test_50_parallel_in_movements_postgres` con la factory async. Tiempo estimado: 1-2 horas.

#### 🟠 [T-3] `MovementEngine.sync` (Fase 0/1) y `MovementEngine.async` (Fase 3) tienen APIs distintas
**Archivos:** `apps/api/app/modules/inventory/movement_engine.py:78-100` vs `apps/api/app/shared/movement_engine.py:73-127`
**Evidencia:**
- Sync: `register(warehouse_id, product_id, movement_type, quantity, reference_type, reference_id, notes) -> MovementResult`
- Async: `apply(MovementRequest(warehouse_id, product_id, movement_type, quantity, reference_type, reference_id, notes, user_id)) -> MovementResult`

El `register()` del sync retorna un `MovementResult` con `warehouse_code`, `product_sku`, `product_name` (los lee de la BD); el async no los incluye (los lee internamente pero no los expone en el dataclass).
**Impacto:** cualquier migración sync→async tiene que adaptar el dataclass. Documentado en Fase 2 ("MovementEngine como wrapper sync + re-exports async"), pero el contrato divergente puede causar bugs sutiles.
**Fix:** unificar el dataclass `MovementResult` con los mismos campos en ambos.

#### 🟠 [T-4] `stock_real` no se actualiza desde `MovementEngine` (reconocible pero...)
**Archivo:** `apps/api/app/modules/inventory/movement_engine.py:193-218` (inserta en `stock_levels` + `inventory_movements`; **no** toca `inventario_stock_real`).
**Evidencia:** doc de Fase 2 R4 lo documenta como "reconciliación automática entre niveles ... queda para Fase 3". Mientras tanto, `stock_levels` y `inventario_stock_real` pueden divergir.
**Impacto:** `GET /inventario/real/distribucion` muestra el Nivel 1 (suma de stock_levels) Y el Nivel 2 (ubicaciones), pero la suma de Nivel 2 puede no coincidir con Nivel 1.
**Fix:** no es bloqueante (está documentado), pero añadir un test que detecte divergencias y un job de reconciliación en Fase 4.

#### 🟢 [T-5] Commit/rollback bien manejados en los routers de Fase 2
**Evidencia:** todos los routers delegan al service, que delega al repository, que usa `db.execute()`. Las excepciones de dominio (`DuplicateUbicacionError`, `CategoryNotFoundError`, etc.) se propagan al handler global `domain_error_handler` (en `core/errors.py`) que retorna JSON 4xx. No hay try/except que silencie errores en los 4 módulos nuevos.

---

### 4. Tests

#### 🟠 [Q-1] Tests de Fase 2 NO se ejecutan en CI contra Postgres
**Archivo:** `.github/workflows/ci.yml:50-67`
**Evidencia:** CI corre `pytest --cov=app --cov-fail-under=80` con `DATABASE_URL=postgresql+asyncpg://...`. Pero los tests de Fase 2 (`test_categories.py`, `test_ubicaciones.py`, `test_stock_real.py`, `test_product_extension.py`, `test_movement_engine_sync.py`) usan `create_app(db_path=":memory:")` que **ignora** `DATABASE_URL` y crea un SQLite in-memory (ver `app/main.py:_resolve_backend`, caso 1).

Entonces en CI:
- Los tests de Fase 2 corren contra SQLite (rápido, no validan Postgres)
- Los tests marcados con `pytest.mark.integration` corren contra Postgres (lentos, pero los de Fase 2 NO están marcados)
- El coverage se infla porque la suite sync testea paths que en producción corren async

**Impacto:** la cobertura `--cov-fail-under=80` puede pasar en CI con código que rompe en runtime async.
**Fix:** marcar los tests de Fase 2 como `@pytest.mark.integration` o ejecutar dos suites: `pytest -m "not integration"` con SQLite y `pytest -m integration` con Postgres.

#### 🟠 [Q-2] Tests de Fase 2 usan `demo123` hardcodeado en 5 archivos
**Archivos:** `test_categories.py:28, 49`, `test_ubicaciones.py:27, 44`, `test_stock_real.py:24, 36`, `test_product_extension.py:25, 37`
**Evidencia:** todos usan `password="demo123"` literal.
**Impacto:** si se rota el hash policy (más iteraciones, por [S-2]), los tests fallan porque el hash demora. O si se quiere cambiar la contraseña, hay que tocar 5 archivos. Es code-smell.
**Fix:** centralizar en una fixture: `DEFAULT_TEST_PASSWORD = os.getenv("TEST_USER_PASSWORD", "demo123")` o usar `secrets.token_urlsafe()` por test.

#### 🟠 [Q-3] Tests de Schema Constraints se skipean en SQLite
**Archivo:** `apps/api/tests/integration/test_schema_constraints.py:23-29`
```python
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _is_postgres(),
    reason="FK enforcement en SQLite async es limitado; test válido en Postgres",
)
async def test_product_with_invalid_category_fails(...)
```
**Evidencia:** 3 tests están skippeados en SQLite: `test_product_with_invalid_category_fails`, `test_warehouse_parent_must_exist`, `test_email_invalid_status_rejected`.
**Impacto:** el equipo es HONESTO sobre la limitación, pero la consecuencia es que la suite que se corre en CI local (SQLite) NO valida FKs de Fase 2 (productos → categorías, warehouses → boxes).
**Fix:** añadir `aiosqlite` con `PRAGMA foreign_keys=ON` (ya se hace en conftest.py:35-37 con `StaticPool`); entonces SQLite enforcará las FKs. Verificar que el `check_same_thread=False` no rompa el StaticPool.

#### 🟡 [Q-4] Tests de Fase 2 están aislados (cada uno crea su BD en setUp)
**Evidencia:** `test_categories.py:43-47`, `test_ubicaciones.py:55-58`, `test_stock_real.py:48-51`: todos usan `setUp` que crea `create_app(db_path=":memory:")` y `tearDown` con `self.app.state.db.close()`. ✅

#### 🟡 [Q-5] Tests cubren happy path + casos de error
**Evidencia:** `test_categories.py` cubre 9 casos (create, list, dup, parent 404, jerarquía 3 niveles, PATCH, soft delete, ciclo directo, ciclo transitivo, 404). `test_ubicaciones.py`: 8 casos. `test_stock_real.py`: 5 casos. `test_product_extension.py`: 6 casos. ✅ Cobertura buena para Fase 2.

#### 🟡 [Q-6] Frontend: 4 archivos de tests escritos, ninguno corre
**Archivos:** `apps/web/src/__tests__/BarcodeInput.test.jsx`, `SearchSku.test.jsx`, `MultibodegaGrid.test.jsx`, `MultibodegaGridPage.test.jsx`
**Evidencia:** el doc de Fase 2 R2 lo documenta: "vitest no instalado por restricción de la spec". Los tests están bien escritos (sintaxis vitest estándar) pero no se ejecutan.
**Fix:** instalar vitest + deps + añadir `npm test` a CI (5-10 min).

---

### 5. Frontend

#### 🟠 [F-1] `BarcodeInput` no maneja IME composition
**Archivo:** `apps/web/src/components/BarcodeInput.jsx:46-67`
**Evidencia:** el `onKeyDown` acumula caracteres en `bufferRef` sin chequear `event.isComposing` ni `event.keyCode === 229` (que es el flag de IME intermedio).
**Impacto:** un usuario escribiendo en IME chino/japonés/coreano presionará teclas que NO son parte del barcode, y el buffer se contaminará con el pinyin/hiragana. Para un sistema de inventario de neumáticos en Chile esto es menor, pero es un bug clásico de IME + barcode.
**Fix:**
```js
if (event.isComposing || event.keyCode === 229) return;
if (event.key === "Enter") { ... }
if (/^[A-Za-z0-9\-._]$/.test(event.key)) { bufferRef.current += event.key; }
```

#### 🟠 [F-2] Throttle 100ms es demasiado agresivo para scanners lentos
**Archivo:** `apps/web/src/components/BarcodeInput.jsx:36, 64`
**Evidencia:**
```js
const THROTTLE_MS = 100;
...
if (now - lastKeyAtRef.current > THROTTLE_MS) {
    bufferRef.current = ""; // Reset si hay pausa humana
}
```
**Impacto:** scanners USB baratos (Honeywell, Tera, etc.) pueden tener jitter de 200-300ms entre caracteres cuando el buffer se llena. Cada pausa >100ms resetea el buffer → el barcode nunca se completa → `onScan` nunca dispara.
**Fix:** subir a 250-300ms (el spec industrial típico es 200ms entre chars; 250ms cubre el 95% de los scanners). O hacer el throttle configurable por prop.

#### 🟠 [F-3] `SearchSku` no aborta el fetch en `useEffect` cleanup → memory leak
**Archivo:** `apps/web/src/components/SearchSku.jsx:48-87`
**Evidencia:** el `useEffect` declara `controller.abort()` en su `if (abortRef.current)` al inicio del nuevo fetch, pero el `return () => { clearTimeout(debounceRef.current); }` **no aborta** el `controller` activo. Si el componente se desmonta con un fetch en vuelo, el `.then()` se ejecuta y llama `setResults`/`setLoading` sobre un componente desmontado.
**Impacto:** warning de React ("Can't perform a state update on an unmounted component") en consola, y memory leak menor (la respuesta completa se mantiene en memoria hasta GC). No es crítico pero ensucia el log.
**Fix:** añadir al cleanup:
```js
return () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (abortRef.current) abortRef.current.abort();
};
```

#### 🟡 [F-4] `BarcodeInput.onChange` y `onKeyDown` mantienen state paralelo
**Archivo:** `apps/web/src/components/BarcodeInput.jsx:42, 53, 57-61`
**Evidencia:** hay `value` (state) y `bufferRef.current` (ref). El `onChange` actualiza `value`; el `onKeyDown` actualiza `bufferRef`. No hay sincronización entre ambos: si el usuario pega un barcode con `Ctrl+V`, el `onChange` recibe el texto completo, pero `onKeyDown` no se dispara → `bufferRef` queda vacío.
**Impacto:** pegar un barcode con `Ctrl+V` no dispara `onScan` (el fallback "usar `value`" en línea 57-61 sí funciona, pero solo si se presiona Enter después).
**Fix:** sincronizar buffer con value: en el `onChange`, si `e.target.value.length >= minLength`, llamar `onScan(e.target.value.trim())`.

#### 🟡 [F-5] Accesibilidad bien lograda en los 3 componentes
**Evidencia:**
- `BarcodeInput`: `role="searchbox"`, `aria-label`, `aria-disabled`, `inputMode="numeric"`, `spellCheck={false}`. ✅
- `SearchSku`: `role="combobox"`, `aria-expanded`, `aria-autocomplete="list"`, items con `role="option" aria-selected="false"`. ✅
- `MultibodegaGrid`: `role="region"`, `aria-label` específico por bodega, badge con `aria-label` diferenciado. ✅

#### 🟡 [F-6] Validación de cliente mínima
**Evidencia:** `MultibodegaGridPage.jsx` no valida que el SKU tenga formato antes de enviar al backend. El backend SÍ normaliza (uppercase) y el servicio retorna 404 con código claro, así que no es bloqueante. Pero el usuario puede enviar "   " (solo espacios) y recibir un error genérico en vez de feedback inmediato.
**Fix:** trim + longitud mínima en el cliente antes de llamar a `fetchDistribucion`.

---

### 6. Documentación

#### 🟡 [D-1] Docstrings presentes y útiles en los 4 módulos de Fase 2
**Evidencia:** verificado en `categories/`, `ubicaciones/`, `stock_real/`, `product_extension/`. Cada archivo tiene:
- Module docstring con regla/convención que aplica
- Class docstring con responsabilidad
- Method docstring con Args/Returns/Raises cuando aplica
✅

#### 🟡 [D-2] ADRs reflejan el código real (con un matiz)
**Evidencia:** los 6 ADRs vigentes tienen secciones "Implementation Notes" que mapean 1:1 a archivos reales:
- ADR-0001 IMP-002 → `apps/api/alembic/` ✅
- ADR-0001 IMP-003 → `tests/test_api_integration.py` ✅ (parcialmente, ver [T-2])
- ADR-0002 IMP-002 → `app/modules/warehouses/service.py:validate_warehouse_type` ❌ NO EXISTE
- ADR-0002 IMP-003 → `GET /api/v1/warehouses?type=mecanico_box` ❌ NO EXISTE
- ADR-0006 IMP-003 → `apps/web/src/tailwind-shim.css` ✅

**El ADR-0002 IMP-002 dice:** "Validar `warehouse_type` server-side en `apps/api/app/modules/warehouses/service.py` con enum explícito" — **no se implementó**. El `WarehouseService.create_warehouse` no valida contra los 3 valores permitidos.
**Fix:** añadir un `WarehouseTypeEnum` y validar.

#### 🟡 [D-3] Doc de Fase 2 R5 documenta correctamente la limitación de Tailwind + `var()` + `/opacity`
**Evidencia:** el doc de Fase 2 R5 lo dice. ✅

#### 🟡 [D-4] Doc de Fase 1 R3 documenta la doble existencia (SQLite legacy + Postgres)
**Evidencia:** el doc de Fase 1 R3 lo dice. Pero el código de `main.py:88-95` muestra que el `app.state.db` SIEMPRE es SQLite legacy aunque el `db_backend` sea `postgres`. El código no refleja la magnitud del problema (los routers **no escriben en Postgres**, lo dice el doc pero el código no lo hace explícito). Aceptable.

---

### 7. Coherencia entre ADRs y código

#### 🟢 [A-1] ADR-0001 (Postgres) bien aterrizado en código
**Mapeo:**
- IMP-001 (Database interface) → `app/db/session.py:194-281` ✅
- IMP-002 (Alembic) → `apps/api/alembic/env.py` ✅
- IMP-003 (tests split) → `tests/unit/` vs `tests/integration/` ✅
- IMP-004 (DB_BACKEND flag) → `core/config.py:71-83` ✅
- IMP-005 (test_api_integration.py corre) → ✅ parcial, ver [T-2]

**Consecuencias POS-001, 002, 003, 004, 005:** todas reflejadas en código.

#### 🟠 [A-2] ADR-0002 (Boxes) tiene 2 IMPs sin implementar
- IMP-002 (validar `warehouse_type` en service con enum) → NO IMPLEMENTADO
- IMP-003 (`GET /warehouses?type=mecanico_box`) → NO IMPLEMENTADO
- IMP-004 (seed: 1 principal + 3 auxiliares + 6 boxes) → NO IMPLEMENTADO (solo se ve 1 bodega CENTRAL en `app/db/demo.py` y `app/db/seed.py`)
- IMP-005 (`ReplenishmentEvaluator` agrega recursivo) → NO IMPLEMENTADO (Fase 4)

**Impacto:** la decisión del ADR existe, el modelo la soporta, pero el "como" (validación + endpoint + seed + job) queda en deuda para Fase 4.

#### 🟢 [A-3] ADR-0003 (Solicitudes) — coherente (código de Fase 3+ ya implementado, fuera de scope)
#### 🟢 [A-4] ADR-0004 (SMTP async) — coherente con código existente (también Fase 3+)
#### 🟢 [A-5] ADR-0005 (Token approval) — implementado correctamente en `core/security.py`
#### 🟢 [A-6] ADR-0006 (Tailwind coexistencia) — implementado según spec

---

## Tabla resumen

| Categoría | 🔴 Críticos | 🟠 Medios | 🟡 Bajos |
|---|---:|---:|---:|
| 1. Calidad de código | 1 | 4 | 2 |
| 2. Seguridad | 1 | 2 | 2 |
| 3. Transacciones | 2 | 2 | 1 |
| 4. Tests | 0 | 3 | 3 |
| 5. Frontend | 0 | 3 | 3 |
| 6. Documentación | 0 | 0 | 4 |
| 7. ADRs | 0 | 1 | 0 |
| **TOTAL** | **4** | **15** | **15** |

---

## Quick wins (cambios < 30 min)

1. **[S-1] Quitar `demo123` pre-cargado y credenciales visibles de `LoginPage.jsx`** — 5 min. CRÍTICO antes de cualquier demo pública.
2. **[T-1] `_immediate_transaction` debe acquire el RLock de `SQLiteDatabase`** — 10 min. Cambiar a `with self._db.transaction():` o exponer `db.begin_immediate()` que use el lock.
3. **[F-1] Añadir `event.isComposing` check en `BarcodeInput.onKeyDown`** — 5 min.
4. **[F-2] Subir `THROTTLE_MS` de 100 a 250 en `BarcodeInput`** — 2 min.
5. **[F-3] Añadir `abortRef.current.abort()` en cleanup de `SearchSku` useEffect** — 3 min.
6. **[S-2] Subir `password_hash_iterations` default a 600_000** — 1 min.
7. **[C-4][C-5] Mover `get_by_sku` al `ProductService` y usar `LIKE 'ACE%'` en el router** — 15 min.
8. **[A-2 IMP-002] Validar `warehouse_type` en `WarehouseService.create_warehouse`** — 10 min.
9. **[C-3] Eliminar `app/modules/inventory/multibodega.py` o marcarlo `@deprecated`** — 2 min.
10. **[Q-3] Habilitar `PRAGMA foreign_keys=ON` en conftest del integration test** — 5 min.

---

## Verificación adversarial

| # | Probe | Resultado |
|---|---|---|
| 1 | ¿Hay `print()` en código de producción? | ✅ No hay, validado por `TestNoPrintStatements` (test_logging.py) |
| 2 | ¿Hay SQL injection en queries? | ✅ No hay (todos `?` parametrizados) |
| 3 | ¿El `MovementEngine` realmente hace `SELECT FOR UPDATE` en Postgres? | ❌ NO validado — el `MovementEngineAsync.apply()` usa `.with_for_update()` ([shared/movement_engine.py:97-104]) pero los tests de concurrencia están skipeados [T-2]. |
| 4 | ¿Hay race condition posible en el stock? | ❌ Sí, en sync: el `_immediate_transaction` salta el RLock [T-1] |
| 5 | ¿Los `commit/rollback` están bien manejados? | ✅ Sí en todos los routers de Fase 2 (sin try/except que silencie) |
| 6 | ¿Hay cobertura de happy + error? | ✅ Sí en los tests de Fase 2 (9+8+5+6 casos) |
| 7 | ¿Tests aislados (BD limpia por test)? | ✅ Sí, `setUp` con `create_app(":memory:")` |
| 8 | ¿Tests dependientes de orden? | ✅ No, cada test crea su propio `admin` user |
| 9 | ¿`BarcodeInput` maneja IME? | ❌ No [F-1] |
| 10 | ¿Throttle robusto contra scanners lentos? | ❌ 100ms es muy agresivo [F-2] |
| 11 | ¿Vistas nuevas accesibles? | ✅ `role`, `aria-label`, `aria-expanded` bien |
| 12 | ¿Memory leaks (useEffect sin cleanup)? | ⚠️ `SearchSku` no aborta el controller en cleanup [F-3] |
| 13 | ¿Formularios validan en cliente? | ⚠️ `MultibodegaGridPage` no valida antes de enviar |
| 14 | ¿Docstrings en funciones públicas? | ✅ Sí en los 4 módulos nuevos |
| 15 | ¿ADRs reflejan código real? | ⚠️ ADR-0002 IMP-002/003/004 no implementados [A-2] |
| 16 | ¿Los 6 ADRs son coherentes entre sí? | ✅ Sí, no hay contradicciones detectadas |
| 17 | ¿Las alternatives considered tienen razones válidas? | ✅ Sí en los 6 |
| 18 | ¿Consecuencias realistas? | ✅ Sí (POS-001 de ADR-0001 = `with_for_update()`; NEG-003 = "tests más lentos" → validado) |
| 19 | ¿Semillas/demo seguras? | ❌ `demo123` hardcodeado en `LoginPage.jsx` y `app/db/demo.py` [S-3] |
| 20 | ¿Tokens de aprobación bien generados? | ✅ HMAC con `itsdangerous`, max_age configurable |

---

## Conclusión

**Veredicto: NECESITA AJUSTES MENORES (4 críticos, 15 medios, 15 bajos).**

El código de Fase 1+2 es estructuralmente correcto: sigue la convención `router → service → repository`; usa `Pydantic` para validación; los errores de dominio están tipados y se traducen a HTTP correctamente; el logging estructurado está en su lugar. Los 6 ADRs vigentes tienen sentido y la mayoría se reflejan en código.

Los **4 críticos** son arreglables en <30 min cada uno (ver Quick wins). Ninguno es un refactor arquitectónico; todos son fixes puntuales:

1. Migraciones SQLite desactualizadas (deuda técnica pre-existente, agravada por Fase 2).
2. Tests de concurrencia real en Postgres son `pytest.skip()` puros (Fase 1 R2 no resuelto).
3. `LoginPage.jsx` expone credenciales demo en la UI (legacy, pero bloqueante para demo público).
4. `MovementEngine` sync salta el `RLock` de `SQLiteDatabase` (race condition residual).

**Recomendación:** emitir un patch con los 10 quick wins antes de la próxima demo; priorizar el ADR-0002 IMPs faltantes (validación warehouse_type + endpoint `?type=`) y la implementación de los 2 tests de concurrencia Postgres como deuda para la siguiente iteración.

---

## Referencias

- ADRs: `docs/adr/adr-0001-postgres-strategy.md` ... `adr-0006-tailwind-coexistencia.md`
- Fase 1: `docs/fases/fase-1-postgres-real.md`
- Fase 2: `docs/fases/fase-2-multibodega-fisica.md`
- Aterrizaje: `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md`
- Roadmap: `docs/fases/roadmap-fase-3-a-10.md`
- CI: `.github/workflows/ci.yml`

**Nota final del auditor:** No se modificó ningún archivo del proyecto. El reporte es el único deliverable. Los archivos en `docs/reviews/` son efímeros (no versionados en repo principal) — confirmar antes de commitear.
