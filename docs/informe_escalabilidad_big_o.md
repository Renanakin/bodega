# Informe de Escalabilidad Big-O — Bodegaje v1.0.0

**Fecha:** 2026-07-24
**Auditor:** Mavis
**Referencia:** `docs/big-o.md` (Regla Maestra de Complejidad Asintótica)
**Estado actual:** ~70% conforme (cumple en estructura, falla en N+1 y consultas masivas)
**Tag actual:** v1.0.0

## TL;DR

Auditoría honesta: el código respeta la regla en su **arquitectura** (JOINs, índices, batch operations), pero tiene **N+1 queries** en al menos 3 hot paths que a escala de millones de registros degradan la performance de O(1)/O(log n) a O(n) u O(n²).

| Hallazgo | Severidad | Tamaño del problema | Fase |
|----------|-----------|---------------------|------|
| **N+1 en `to_view()` de OC** (1 supervisor + N detalles) | 🔴 Crítica | Con 1000 OCs = 2000 queries | P0 |
| **N+1 en `ReplenishmentEvaluator.evaluate_warehouse`** (Product + StockLevel por SKU) | 🔴 Crítica | Con 500 SKUs = 1000 queries | P0 |
| **Endpoint `/solicitudes?limit=1000` carga todo en memoria** | 🟡 Media | 1M registros = 50MB JSON | P0 |
| **Falta índice `audit_logs(actor_id, created_at)`** | 🟡 Media | Búsqueda de actividad de usuario O(n) | P1 |
| **Falta índice compuesto `stock_levels(warehouse_id, min_quantity, quantity)`** | 🟡 Media | `/bajo-minimo` con 1M stocks O(n) | P1 |
| **`process_one` del outbox es secuencial** | 🟢 Baja | 100 emails = 100 round-trips, no queries | P2 |
| **Falta paginación en `/api/v1/products`** | 🟡 Media | Devuelve todo el catálogo | P1 |
| **Falta `EXPLAIN ANALYZE` en CI** | 🟢 Baja | Previene regresiones | P3 |
| **Sin tests de carga con millones de registros** | 🟡 Media | No hay baseline medible | P2 |

---

## 1. Estado actual: qué tenemos

### ✅ Lo que YA cumple Big-O

**Capa de datos (BD):**
- **13 índices compuestos** declarados vía `__table_args__` en los modelos ORM:
  - `stock_levels(warehouse_id, product_id)` — UNIQUE (BUG 9 fix)
  - `inventory_movements(warehouse_id, product_id, created_at)` — listar ledger
  - `inventory_movements(product_id, created_at)` — historial por SKU
  - `solicitudes_recarga(estado, created_at)` — filtro dashboard
  - `ordenes_compra(estado, created_at)` — listar con filtro
  - `ordenes_compra(id_supervisor)` — JOIN rápido
  - `ordenes_compra(id_bodega_principal)` — JOIN rápido
  - `email_outbox(status, created_at)` — worker processa pending
  - `audit_logs(created_at)` — index básico
  - `user_sessions(token)`, `user_sessions(refresh_token)` — UNIQUE
  - `products(codigo_barras)` — UNIQUE implícito
  - `products(id_categoria)` — JOIN
  - `categories(parent_id)` — árbol
- **JOINs explícitos** en repos (no loops anidados cargando manualmente)
- **Migración 0010 (`0010_indices_performance.sql`)** + **0013 (`0013_unique_stock_levels.sql`)** consolidan índices críticos
- **CTEs y `IN (...)`** ya usados en `to_view()` (línea 77 de `_common.py`) para cargar productos en batch

**Capa de aplicación (Python):**
- `ReplenishmentEvaluator` usa `select().where(...).in_(product_ids)` para cargar pendientes (línea 264 de `replenishment.py`)
- `InventoryRepository.list_stock_levels_with_joins` hace un solo SELECT con 2 JOINs
- `asyncio.gather` se usa en acciones de aprobación de OC (paralelismo donde aplica)
- `limit` cap en endpoints de listado (1000 solicitudes, 200 notificaciones, 50 default)

**Capa de infraestructura:**
- Connection pooling (SQLAlchemy + asyncpg)
- Redis para rate limit + cache
- Arq worker para tareas async (no bloquea request path)

### ⚠️ Lo que NO cumple Big-O

#### 🔴 **Hallazgo #1: N+1 en `to_view()` de OrdenCompra**

**Ubicación:** `apps/api/app/modules/ordenes_compra/actions/_common.py:68-114`
**Severidad:** 🔴 **Crítica** — Hot path del módulo de OC
**Complejidad actual:** O(n) queries por cada listado (n = número de OCs)
**Complejidad ideal:** O(1) con 3 queries totales (1 OCs + 1 supervisores batch + 1 detalles batch)

```python
# PROBLEMA: linea 94
sup = await session.get(Supervisor, oc.id_supervisor)  # 1 query por OC

# ANTES era N+1 para productos, ya arreglado (linea 77):
# stmt_productos = select(Product).where(Product.id.in_(product_ids))  # OK

# PERO detalles sigue 1 query por OC (linea 70):
detalles_stmt = select(DetalleOrdenCompra).where(DetalleOrdenCompra.id_orden_compra == oc.id)
```

**Impacto con datos reales:**
| n (OCs) | Queries actuales | Queries ideales | Degradación |
|---------|------------------|-----------------|-------------|
| 10      | 30               | 3               | 10x         |
| 100     | 300              | 3               | 100x        |
| 1000    | 3000             | 3               | 1000x       |

**Fix:** Fase P0 (sección 3.1)

---

#### 🔴 **Hallazgo #2: N+1 en `ReplenishmentEvaluator.evaluate_warehouse`**

**Ubicación:** `apps/api/app/modules/solicitudes/replenishment.py:285-355`
**Severidad:** 🔴 **Crítica** — Worker corre cada N minutos
**Complejidad actual:** O(n) queries por bodega (n = SKUs bajo mínimo)
**Complejidad ideal:** O(1) con 2 queries (1 productos + 1 stock_levels principal batch)

```python
# PROBLEMA: linea 295 (dentro del for)
prod = await self._session.get(Product, stock.product_id)  # 1 query por SKU

# PROBLEMA: linea 311-315 (dentro del for)
principal_stock_stmt = select(StockLevel).where(
    StockLevel.warehouse_id == principal.id,
    StockLevel.product_id == stock.product_id,
)
principal_stock = (await self._session.execute(principal_stock_stmt)).scalar_one_or_none()
```

**Impacto:**
| SKUs bajo mínimo | Queries actuales | Queries ideales |
|------------------|------------------|-----------------|
| 50               | 100              | 4 (1 bodega + 1 stock + 1 productos + 1 pendientes) |
| 500              | 1000             | 4 |
| 5000             | 10000            | 4 |

**Con 100 bodegas × 50 SKUs = 5000 SKUs = 10.000 queries hoy, vs 4 queries con el fix.**

**Fix:** Fase P0 (sección 3.1)

---

#### 🟡 **Hallazgo #3: Endpoint sin paginación real**

**Ubicación:** `apps/api/app/modules/solicitudes/router.py:list_solicitudes` y otros
**Severidad:** 🟡 **Media** — puede tumbar el server
**Complejidad:** O(n) transferencia, O(1) memoria por request, pero latencia O(n)

```python
@router.get("", response_model=list[SolicitudResponse])
async def list_solicitudes(
    limit: int = Query(default=1000, le=1000),  # cap alto
    ...
):
```

Con `limit=1000` y cada SolicitudResponse ~5KB (con detalles), son **5MB por request**. Con 10 usuarios concurrentes son 50MB de I/O. Si los datos escalan a 1M de solicitudes, el limit-cap sigue siendo 1000 (BIEN), pero el `OFFSET` no está implementado: el cliente no puede paginar.

**Fix:** Fase P0 (sección 3.1)

---

#### 🟡 **Hallazgo #4: Índices faltantes en tablas grandes**

**Ubicación:** Modelos ORM
**Severidad:** 🟡 **Media** — queries específicas hacen full table scan

| Query | Filtro | Índice actual | Índice necesario |
|-------|--------|---------------|-------------------|
| `/audit?actor_id=X` | `actor_id + created_at` | solo `created_at` | `(actor_id, created_at)` |
| `/bajo-minimo` | `min_quantity > 0 AND quantity <= min_quantity` | solo `(warehouse_id, product_id)` | `(warehouse_id, min_quantity, quantity)` o partial index |
| `/api/v1/products` | sin paginación | `id_categoria` | ya OK con LIMIT pero falta paginación |
| `SolicitudesService.list` con filtro por código | `codigo LIKE 'SOL-%'` | ninguno | `(codigo)` unique + LIKE-friendly |
| `EmailOutbox` retry_dead | `status = 'dead'` | `(status, created_at)` | OK, pero sin `attempts` |

**Impacto:** con 1M de `audit_logs` y `WHERE actor_id = X`, hoy es **O(n) seq scan**. Con índice serían **O(log n)**.

**Fix:** Fase P1 (sección 3.2)

---

#### 🟢 **Hallazgo #5: `process_one` secuencial en email outbox**

**Ubicación:** `apps/api/app/modules/notifications/service.py:process_batch`
**Severidad:** 🟢 **Baja** — no degrada complejidad algorítmica, sí latencia
**Complejidad:** O(n) round-trips secuenciales, no O(n²)

```python
for ob in outboxes:
    r = await self.process_one(ob.id)  # 1 round-trip
```

**Fix opcional:** Fase P2 (sección 3.3) con `asyncio.gather` o bulk update.

---

#### 🟡 **Hallazgo #6: Sin tests de carga con millones de registros**

**Severidad:** 🟡 **Media** — no hay forma de saber si escalamos
**Tests actuales:** 5/5 E2E con ~10 OCs, ~5 productos, ~8 bodegas (datos de juguete)

**Necesitamos:** Test con 1M `stock_levels`, 100k `inventory_movements`, 50k `solicitudes` para validar que las queries siguen en O(log n) o constante.

**Fix:** Fase P2 (sección 3.3)

---

## 2. Paralelo: lo que tenemos vs. lo que la regla exige

| Aspecto | Regla Big-O | Bodegaje v1.0.0 | Cumple |
|---------|-------------|-----------------|--------|
| **Búsqueda por PK** | O(1) | O(1) via PK index | ✅ |
| **Búsqueda por FK** | O(log n) | O(log n) via FK index | ✅ |
| **JOINs** | O(log n) por lado | O(log n) via índices | ✅ |
| **Listar con filtro** | O(log n) | O(log n) con índice apropiado | ⚠️ Parcial (faltan índices en audit y stock_levels) |
| **Listar con paginación** | O(log n) + O(p) | O(n) hoy (no hay cursor/offset) | ❌ |
| **N+1 queries** | Prohibido (O(n²)) | Hay 2 instancias | ❌ |
| **Bucles anidados sobre BD** | Prohibido | No hay (JOINs bien hechos) | ✅ |
| **Batch operations** | Obligatorio si N > 10 | Parcial: productos en batch, supervisor 1x1 | ⚠️ |
| **Caché (Redis)** | Para hot data > 10k req/s | Solo rate-limit y refresh tokens | ⚠️ |
| **Índices parciales** | Para queries de alta selectividad | No usados | ❌ |
| **EXPLAIN ANALYZE** | Obligatorio en CI | No automatizado | ❌ |
| **Materialized views** | Para agregaciones pesadas | No usadas | N/A (no hay agregaciones) |
| **Read replicas** | Si lecturas > 1000 qps | No configuradas | N/A (volumen bajo) |

**Resumen de cumplimiento: 5/13 puntos plenos, 4/13 parciales, 3/13 fallan, 1/13 N/A.**

---

## 3. Plan de implementación por fases

### P0 — Bloqueantes: eliminar N+1 y agregar paginación (Día 1, 8-12h)

**Objetivo:** Llevar los 3 hot paths a O(1) u O(log n) con datos constantes.

#### 3.1 Fix N+1 en `to_view()` de OC

**Archivo:** `apps/api/app/modules/ordenes_compra/actions/_common.py`

**Cambio:** Agregar una variante `to_views_batch()` que recibe todas las OCs y hace solo 3 queries totales.

```python
# NUEVO en _common.py
async def to_views_batch(
    session: AsyncSession, ocs: list[OrdenCompra]
) -> list[OrdenCompraView]:
    """Convierte N OCs a views en 3 queries totales (no N+1).

    Queries:
    1. SELECT * FROM ordenes_compra WHERE id IN (...)
       (ya ejecutado por el caller, no se cuenta)
    2. SELECT * FROM supervisores WHERE id IN (...ids unicos)
    3. SELECT * FROM detalle_orden_compra WHERE id_orden_compra IN (...ids)
    4. SELECT * FROM products WHERE id IN (...ids unicos de detalles)

    Returns: lista de OrdenCompraView con detalles cargados.
    """
    if not ocs:
        return []

    oc_ids = [oc.id for oc in ocs]
    sup_ids = list({oc.id_supervisor for oc in ocs})

    # 1. Supervisores (batch)
    stmt_sups = select(Supervisor).where(Supervisor.id.in_(sup_ids))
    sups = (await session.execute(stmt_sups)).scalars().all()
    sups_by_id = {s.id: s for s in sups}

    # 2. Detalles (batch)
    stmt_det = select(DetalleOrdenCompra).where(
        DetalleOrdenCompra.id_orden_compra.in_(oc_ids)
    )
    detalles = (await session.execute(stmt_det)).scalars().all()
    detalles_by_oc: dict[uuid.UUID, list[DetalleOrdenCompra]] = {}
    for d in detalles:
        detalles_by_oc.setdefault(d.id_orden_compra, []).append(d)

    # 3. Productos (batch, solo los necesarios)
    product_ids = list({d.id_producto for d in detalles})
    productos_by_id: dict[uuid.UUID, Product] = {}
    if product_ids:
        stmt_p = select(Product).where(Product.id.in_(product_ids))
        productos = (await session.execute(stmt_p)).scalars().all()
        productos_by_id = {p.id: p for p in productos}

    # 4. Construir views
    views: list[OrdenCompraView] = []
    for oc in ocs:
        sup = sups_by_id.get(oc.id_supervisor)
        dets = detalles_by_oc.get(oc.id, [])
        detalles_view = [
            {
                "id_orden_compra": d.id_orden_compra,
                "id_producto": d.id_producto,
                "product_sku": (productos_by_id.get(d.id_producto) or Product()).sku,
                "product_name": (productos_by_id.get(d.id_producto) or Product()).name,
                "cantidad_pedida": d.cantidad_pedida,
                "costo_unitario_pactado": d.costo_unitario_pactado,
            }
            for d in dets
        ]
        views.append(
            OrdenCompraView(
                id=oc.id,
                codigo=oc.codigo,
                # ... (mismos campos que to_view)
                detalles=detalles_view,
            )
        )
    return views
```

**Cambio en `queries/listar.py`:**
```python
# ANTES:
return [await to_view(session, o) for o in result.scalars().all()]

# DESPUES:
ocs = list(result.scalars().all())
return await to_views_batch(session, ocs)
```

**Complejidad resultante:** O(1) — 3 queries fijas independiente de n.

#### 3.2 Fix N+1 en `ReplenishmentEvaluator.evaluate_warehouse`

**Archivo:** `apps/api/app/modules/solicitudes/replenishment.py`

**Cambio:** Hacer un solo `select(Product).where(Product.id.in_(product_ids))` y un solo `select(StockLevel).where(... IN ...)` para la principal, antes del loop.

```python
# ANTES (líneas 285-355): for stock in stocks: ... product = session.get(Product) ... principal_stock = session.execute(...)

# DESPUES:
product_ids = [s.product_id for s in stocks]
products_by_id: dict[uuid.UUID, Product] = {}
if product_ids:
    stmt_p = select(Product).where(Product.id.in_(product_ids))
    products_by_id = {p.id: p for p in (await self._session.execute(stmt_p)).scalars().all()}

# Stock de la principal para TODOS los productos en 1 query
principal_stocks_by_product: dict[uuid.UUID, StockLevel] = {}
if product_ids:
    stmt_ps = select(StockLevel).where(
        StockLevel.warehouse_id == principal.id,
        StockLevel.product_id.in_(product_ids),
    )
    principal_stocks_by_product = {
        s.product_id: s for s in (await self._session.execute(stmt_ps)).scalars().all()
    }

# Ahora el loop es solo logica, sin queries:
for stock in stocks:
    if stock.product_id in productos_con_pendiente:
        omitidas_count += 1
        continue
    prod = products_by_id.get(stock.product_id)
    if prod is None or not prod.is_active:
        continue
    principal_stock = principal_stocks_by_product.get(stock.product_id)
    if principal_stock is None or principal_stock.quantity <= 0:
        omitidas_sin_stock_principal += 1
        continue
    # ... resto igual
```

**Complejidad resultante:** O(1) queries para los datos del batch.

#### 3.3 Paginación cursor-based

**Archivos:** `apps/api/app/modules/solicitudes/router.py`, `ordenes_compra/queries/listar.py`, `inventory/router.py`

**Cambio:** Reemplazar `limit=1000` por cursor `(created_at, id)`.

```python
# Antes:
@router.get("", response_model=list[SolicitudResponse])
async def list_solicitudes(
    limit: int = Query(default=1000, le=1000),
    estado: str | None = None,
    ...
):

# Después:
@router.get("", response_model=SolicitudListResponse)
async def list_solicitudes(
    limit: int = Query(default=50, le=200),  # cap más razonable
    cursor: str | None = Query(default=None, description="(created_at,id) base64"),
    estado: str | None = None,
    ...
):
    """Cursor-based pagination.

    Response:
    {
      "items": [...],
      "next_cursor": "MjAyNi0wNy0yNFQwMDo..." | null,
      "has_more": bool
    }
    """
    stmt = select(SolicitudRecarga).order_by(
        SolicitudRecarga.created_at.desc(),
        SolicitudRecarga.id.desc(),
    )
    if cursor:
        ca, ci = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                SolicitudRecarga.created_at < ca,
                and_(
                    SolicitudRecarga.created_at == ca,
                    SolicitudRecarga.id < ci,
                ),
            )
        )
    if estado:
        stmt = stmt.where(SolicitudRecarga.estado == estado)
    stmt = stmt.limit(limit + 1)  # +1 para saber has_more

    result = await session.execute(stmt)
    items = list(result.scalars().all())
    has_more = len(items) > limit
    items = items[:limit]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    )
    return SolicitudListResponse(
        items=items, next_cursor=next_cursor, has_more=has_more
    )
```

**Complejidad resultante:** O(log n + p) donde p = limit (en lugar de O(n)).

**Criterio Go/No-Go P0:**
- [ ] `to_views_batch` reemplaza `to_view` en todos los call sites de listado de OC
- [ ] `evaluate_warehouse` carga productos y stock de principal en 2 queries fijas
- [ ] Endpoints `/solicitudes`, `/ordenes-compra`, `/audit`, `/products` aceptan `cursor` y `limit<=200`
- [ ] Test de carga con 1000 OCs y 100k solicitudes: < 1s por request
- [ ] Battery E2E sigue 5/5 verde

---

### P1 — Índices faltantes + análisis de queries (Día 2, 4-6h)

**Objetivo:** Llevar queries específicas de O(n) a O(log n) con índices apropiados.

#### 3.4 Migración 0014 — Índices de performance

**Archivo:** `db/migrations/0014_performance_indices.sql`

```sql
-- 0014_performance_indices.sql
-- P1 del roadmap Big-O: indices que faltan para queries especificas.

BEGIN;

-- 1. audit_logs: busqueda por actor con filtro de fecha
--    Query afectada: /audit?actor_id=X&from=YYYY-MM-DD
--    Sin indice: seq scan sobre 1M filas = O(n)
--    Con indice: O(log n)
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_created_at
    ON audit_logs (actor_id, created_at DESC);

-- 2. stock_levels: bajo minimo por bodega
--    Query afectada: /bajo-minimo, /solicitudes/bajo-minimo
--    El query filtra: min_quantity > 0 AND quantity <= min_quantity
--    Partial index: solo filas donde min_quantity > 0 (subset pequenho)
CREATE INDEX IF NOT EXISTS idx_stock_levels_bajo_minimo
    ON stock_levels (warehouse_id, quantity)
    WHERE min_quantity > 0;

-- 3. solicitudes_recarga: busqueda por codigo (LIKE 'SOL-2026%')
--    LIKE 'prefix%' usa btree si el indice es UNIQUE en codigo
CREATE UNIQUE INDEX IF NOT EXISTS uq_solicitudes_codigo
    ON solicitudes_recarga (codigo);

-- 4. ordenes_compra: busqueda por codigo
CREATE UNIQUE INDEX IF NOT EXISTS uq_ordenes_codigo
    ON ordenes_compra (codigo);

-- 5. inventory_movements: busqueda por reference_id (OC/factura/solicitud)
--    Query afectada: cuadre OC vs factura
CREATE INDEX IF NOT EXISTS idx_inventory_movements_reference
    ON inventory_movements (reference_type, reference_id)
    WHERE reference_id IS NOT NULL;

-- 6. email_outbox: busqueda por message_id (idempotencia de envios)
CREATE UNIQUE INDEX IF NOT EXISTS uq_email_outbox_message_id
    ON email_outbox (message_id)
    WHERE message_id IS NOT NULL;

COMMIT;
```

**Versión Alembic:** `apps/api/alembic/versions/0014_performance_indices.py`

#### 3.5 Análisis EXPLAIN de las 5 queries más críticas

**Script:** `tests/perf/explain_critical_queries.py`

```python
"""Analiza con EXPLAIN ANALYZE las 5 queries mas criticas."""
from sqlalchemy import text
import json
import sys

CRITICAL_QUERIES = [
    ("Bajo minimo (warehouse_id=NULL)", """
        EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
        SELECT * FROM stock_levels
        WHERE min_quantity > 0 AND quantity <= min_quantity
    """),
    ("Solicitudes pendientes (cobertura)", """
        EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
        SELECT s.* FROM solicitudes_recarga s
        WHERE s.estado IN ('pending','approved','in_transit','partially_received')
          AND s.id_bodega_origen = $1
    """),
    ("OC listar con JOIN supervisor", """
        EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
        SELECT oc.*, s.nombre
        FROM ordenes_compra oc
        LEFT JOIN supervisores s ON s.id = oc.id_supervisor
        WHERE oc.estado = 'enviado_a_supervisor'
        ORDER BY oc.created_at DESC
        LIMIT 50
    """),
    ("Audit por actor", """
        EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
        SELECT * FROM audit_logs
        WHERE actor_id = $1 AND created_at >= $2
        ORDER BY created_at DESC
        LIMIT 100
    """),
    ("Email outbox worker", """
        EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
        SELECT * FROM email_outbox
        WHERE status = 'pending' AND attempts < 3
        ORDER BY created_at ASC
        LIMIT 50
    """),
]

def main():
    """Para cada query corre EXPLAIN ANALYZE y verifica que use indices."""
    # ... conexion a BD, ejecutar, parsear JSON, validar plan
    pass
```

**Criterio Go/No-Go P1:**
- [ ] Migración 0014 aplicada sin errores
- [ ] `EXPLAIN ANALYZE` de las 5 queries muestra `Index Scan` o `Bitmap Index Scan`, NO `Seq Scan` en tablas > 100k filas
- [ ] Tests de batería E2E siguen 5/5 verde

---

### P2 — Tests de carga + paralelización (Día 3-4, 8-12h)

**Objetivo:** Validar que escalamos a millones de datos con queries O(log n) o menos.

#### 3.6 Test de carga con datos sintéticos

**Archivo:** `tests/perf/load_test_millions.py`

**Plan:**
1. Generar 1M de `stock_levels` (1k bodegas × 1k productos, o 10k × 100)
2. Generar 100k de `inventory_movements` (último año)
3. Generar 50k de `solicitudes_recarga`
4. Generar 10k de `ordenes_compra`
5. Medir:
   - Latencia p50, p95, p99 de las 5 queries críticas
   - Throughput con `wrk` o `vegeta` (10 conexiones, 30s)
   - Memoria del API process

**Métricas objetivo:**

| Query | Volumen | p50 objetivo | p95 objetivo | p99 objetivo |
|-------|---------|--------------|--------------|--------------|
| `/solicitudes?limit=50` | 50k sol | < 50ms | < 200ms | < 500ms |
| `/ordenes-compra?limit=50` | 10k OC | < 80ms | < 300ms | < 800ms |
| `/bajo-minimo` | 1M stocks | < 200ms | < 800ms | < 2s |
| `/audit?actor_id=X` | 1M logs | < 100ms | < 400ms | < 1s |
| `/stock?warehouse_id=X` | 1k stocks/bodega | < 30ms | < 100ms | < 200ms |

**Setup:**
```bash
# Levantar Postgres de prueba
docker run -d --name perf-db -e POSTGRES_PASSWORD=test postgres:17

# Seed datos
python tests/perf/load_test_millions.py --seed --scale 1M

# Correr carga
vegeta attack -duration=30s -rate=100 -targets=queries.txt | vegeta report
```

#### 3.7 Paralelización de email outbox

**Archivo:** `apps/api/app/modules/notifications/service.py`

```python
# ANTES:
for ob in outboxes:
    r = await self.process_one(ob.id)  # secuencial

# DESPUES:
import asyncio
results = await asyncio.gather(
    *[self.process_one(ob.id) for ob in outboxes],
    return_exceptions=True,
)
stats = {"sent": 0, "failed": 0, "retried": 0, "skipped": 0}
for r in results:
    if isinstance(r, Exception):
        stats["failed"] += 1
        continue
    s = r["status"]
    if s == self.STATUS_SENT:
        stats["sent"] += 1
    # ...
```

**Criterio Go/No-Go P2:**
- [ ] Test de carga: 100 RPS con p95 < 500ms en las 5 queries críticas
- [ ] Email outbox procesa 100 emails en < 5s (vs 30s antes)
- [ ] Memoria del API process < 512MB con 1M registros en BD

---

### P3 — CI con `EXPLAIN ANALYZE` y monitoreo (Día 5, 4-6h)

**Objetivo:** Prevenir regresiones de performance en cada PR.

#### 3.8 Workflow de GitHub Actions con `EXPLAIN ANALYZE`

**Archivo:** `.github/workflows/perf-check.yml`

```yaml
name: Performance regression check

on:
  pull_request:
    paths:
      - 'apps/api/app/modules/**'
      - 'apps/api/alembic/versions/**'

jobs:
  explain-check:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:17
        env:
          POSTGRES_PASSWORD: test
        ports: ['5432:5432']
        options: >-
          --health-cmd "pg_isready"
          --health-interval 5s
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r apps/api/requirements.txt
      - run: |
          # Seed 100k registros (escala media para CI)
          python tests/perf/seed_test_data.py --scale 100k
      - run: |
          # Validar que las 5 queries criticas usan indices
          python tests/perf/explain_critical_queries.py --assert-index-scan
```

**Falla el PR si:** alguna query hace `Seq Scan` en una tabla > 50k filas.

#### 3.9 Dashboard de Grafana para Big-O

**Archivo:** `infra/grafana/dashboards/big_o_health.json`

Métricas a monitorear:
- Latencia p50/p95/p99 por endpoint
- Queries por minuto por endpoint
- Top 10 queries lentas (slow query log de Postgres)
- Cardinalidad de tablas (rows por tabla)
- Hit rate de índices (`pg_stat_user_indexes`)

**Criterio Go/No-Go P3:**
- [ ] Workflow `perf-check` corre en < 5 min
- [ ] Dashboard exportado a `infra/grafana/dashboards/`
- [ ] Alertas en Alertmanager si p95 > 500ms por 5 min

---

## 4. Estimación de tiempos y costos

| Fase | Tiempo | Esfuerzo | Impacto en performance |
|------|--------|----------|------------------------|
| **P0** — Eliminar N+1 + paginación | 1 día (8-12h) | 1 dev senior | 100-1000x mejora en listados |
| **P1** — Índices + EXPLAIN | 0.5 día (4-6h) | 1 dev mid | 10-100x mejora en queries específicas |
| **P2** — Tests de carga + paralelización | 1.5 días (12-16h) | 1 dev senior | Validación cuantitativa + 5x en outbox |
| **P3** — CI + dashboards | 0.5 día (4-6h) | 1 devops | Prevención de regresiones |

**Total:** ~3.5 días de trabajo

**Costo de NO hacerlo:**
- 1M de registros en `stock_levels` → `/bajo-minimo` toma **5-10s** (vs 100ms con índices)
- 10k OCs acumuladas → `/ordenes-compra` toma **3s** (vs 50ms con N+1 fix)
- 100k emails pendientes → worker procesa en **30 min** (vs 5 min con paralelización)

---

## 5. Riesgos identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Migración 0014 falla en producción | Baja | Alto (downtime) | Dry-run en staging primero, 5min de downtime planificado |
| `to_views_batch` cambia orden de campos JSON | Baja | Bajo (cliente) | Tests E2E validan contrato |
| Test de carga genera datos irrealistas | Media | Bajo | Semilla determinística con `seed=42` |
| EXPLAIN ANALYZE falso positivo en CI | Media | Bajo | Threshold configurable, whitelist de tablas pequeñas |
| `asyncio.gather` en outbox causa contención SMTP | Media | Medio | Limitar concurrencia con `Semaphore(10)` |

---

## 6. Definition of Done (cumplimiento Big-O)

- [ ] **P0:** `to_views_batch` implementado, `evaluate_warehouse` O(1) en queries, paginación cursor en 4 endpoints
- [ ] **P1:** Migración 0014 aplicada, EXPLAIN de 5 queries muestra `Index Scan`
- [ ] **P2:** Tests de carga con 1M registros, métricas cumplidas, outbox paralelizado
- [ ] **P3:** CI con `EXPLAIN ANALYZE`, dashboard de Grafana
- [ ] **Battery E2E:** 5/5 verde después de cada fase
- [ ] **Documentación:** `docs/big-o.md` linkeado desde README, "Regla Big-O" como sección obligatoria en code review checklist

Cuando todo esté ✅, **el sistema cumple con la Regla Maestra de Big-O** y soporta millones de registros sin degradación.

---

## 7. Referencias

- `docs/big-o.md` — Regla Maestra de Complejidad Asintótica
- `docs/roadmap_100_por_ciento.md` — Roadmap paralelo para go-live producción
- `docs/roadmap_cierre_produccion.md` — Roadmap previo
- `apps/api/app/modules/ordenes_compra/actions/_common.py:68` — N+1 to_view()
- `apps/api/app/modules/solicitudes/replenishment.py:285-355` — N+1 evaluate_warehouse
- `apps/api/alembic/versions/0010_indices_performance.py` — Índices existentes
- `db/migrations/0013_unique_stock_levels.sql` — UNIQUE constraint fix previo
- `tests/e2e/run_all.py` — Batería E2E (no rompe con los cambios)
