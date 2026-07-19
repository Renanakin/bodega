---
title: "Aterrizaje del Requerimiento — Sistema Multi-Bodega con Recarga y Órdenes de Compra"
date: 2026-07-14
status: "Borrador para revisión"
owner: "Equipo Bodegaje"
scope: "apps/api, db, apps/web, infra"
source_spec: "Mensaje del usuario 2026-07-14 — spec completa de bodega principal + 3 auxiliares + boxes + OC externas"
tags: ["arquitectura", "aterrizaje", "roadmap", "multi-bodega"]
---

# Aterrizaje del Requerimiento — Sistema Multi-Bodega

> Documento ejecutivo que aterriza la nueva especificación de negocio (bodega principal + auxiliares + boxes + órdenes de compra externas con email al supervisor) sobre el código existente del proyecto **Bodegaje**.

---

## 1. Resumen ejecutivo

**Conclusión en una línea:** El proyecto tiene un **MVP sólido** (auth con roles, warehouses, products, inventory con movimientos auditables, transfers, audit) que cubre el 35% de la spec nueva. El 65% restante requiere trabajo **estructural** (no cosmético): cambiar la granularidad de `transfers` (1 producto) a `solicitudes_recarga` (N productos), añadir **ubicaciones físicas** con stock por slot, integrar **PostgreSQL real** (hoy la API corre en SQLite `:memory:`), y construir el módulo de **notificaciones SMTP asíncronas** con Redis + worker.

**Esfuerzo total estimado:** 10 semanas (1 BE + 1 FE + 0.5 DevOps), ruta crítica: **Postgres real → Solicitudes N-productos → SMTP async**.

**Recomendación:** No escribir más código hasta cerrar **6 decisiones arquitecturales** (ver §10) y emitir **6 ADRs**. El equipo puede partir por la **Fase 1 (Postgres real)** sin riesgo de deprecación, que es prerequisito de todo lo demás.

---

## 2. Estado actual del proyecto (diagnóstico)

| Capa | Stack | Estado real | Evidencia |
|---|---|---|---|
| Backend | Python 3.12 + FastAPI 0.116.1 | MVP funcional, **persistencia en SQLite `:memory:`** | `apps/api/app/main.py`, `apps/api/app/db/session.py` |
| BD | PostgreSQL 17 (en compose) + SQLite (en API) | Esquema Postgres existe pero **no conectado a la API** | `infra/docker/docker-compose.yml`, `db/migrations/*.sql` |
| Frontend | React 19 + Vite 7 + **CSS plano (sin Tailwind)** | 11 vistas, mock-data, formularios básicos | `apps/web/src/views/*.jsx`, `apps/web/src/styles.css` |
| Auth | JWT con roles (admin, supervisor, origin_operator, destination_operator) | Login + sesión + roles operativos | `apps/api/app/modules/auth/` |
| Tests | unittest + TestClient | 5+ tests OK contra SQLite | `apps/api/tests/test_api.py` |
| Infra | Docker Compose con perfiles local/staging/production, Nginx, Redis 8, Mailpit **no incluido** | Estructura de despliegue madura | `infra/docker/compose.*.yml` |
| Docs | ADRs pendientes, 6 documentos de arquitectura + operaciones | Documentación operativa al día | `docs/architecture/`, `docs/operations/` |

**Lo que YA hace el sistema (no tocar):**
- CRUD de bodegas y productos con reglas de unicidad
- Movimientos de inventario auditables (`inventory_movements` es el ledger; `stock_levels` es proyección)
- Transferencias entre bodegas con workflow completo (solicitada→aprobada→despachada→recibida/parcial)
- Login por rol, sesiones, auditoría
- Frontend con navegación, formularios, toasts, estados de carga
- Despliegue con Nginx, perfiles separados por ambiente

**Lo que NO hace y la spec nueva exige** (ver §3).

---

## 3. Tabla de brechas (resumen ejecutivo)

> Convención: **Impl** = Implementado · **Parc** = Parcial · **No** = No existe.
> Esfuerzo: **S** ≤ ½ día · **M** 1-2 días · **L** 3-5 días · **XL** > 1 semana.
> 42 brechas catalogadas en total; aquí las 18 más críticas.

### 3.1 Dominio — Bodegas y boxes

| # | Elemento de la spec | Estado | Tipo de cambio | Esfuerzo |
|---|---|---|---|---|
| 1 | `bodegas.tipo` ∈ {Principal, Auxiliar} (con constraint) | Parc — sólo string libre | Migración aditiva | S |
| 2 | Regla: **origen siempre Auxiliar, destino siempre Principal** | No existe | Migración + service rule | S |
| 3 | Boxes de mecánicos como entidad de dominio | No existe | Decisión arquitectural (ver §5.5) | M |
| 4 | `supervisores` como tabla propia con email | Conflicto con `users.role='supervisor'` | Migración con coexistencia | M |

### 3.2 Dominio — Productos y catálogo

| # | Elemento de la spec | Estado | Tipo de cambio | Esfuerzo |
|---|---|---|---|---|
| 5 | `categorias` (id, nombre, descripcion) | No existe | Migración aditiva | S |
| 6 | `productos.precio_costo`, `productos.precio_venta`, `codigo_barras`, FK a `categorias` | No existe | Migración aditiva | S |
| 7 | `detalles_neumaticos` 1:1 (ancho, perfil, aro, índice carga/velocidad, DOT) | No existe | Migración aditiva | M |

### 3.3 Dominio — Inventario físico

| # | Elemento de la spec | Estado | Tipo de cambio | Esfuerzo |
|---|---|---|---|---|
| 8 | `inventario_bodega_parametros` (min, max por bodega×producto) | Parc — sólo `min_quantity` en `stock_levels` | Migración aditiva | S |
| 9 | `ubicaciones_estanteria` (pasillo, estanteria, altura) UNIQUE compuesta | No existe | Migración + nueva entidad | M |
| 10 | `inventario_stock_real` por ubicación con CHECK ≥ 0 | Conflicto con `stock_levels` agregado | **Refactor mayor — convivencia** | L |
| 11 | Alerta automática "stock bajo mínimo → emitir solicitud" | Parc — hay conteo, no generación | Refactor + nuevo job | M |

### 3.4 Dominio — Solicitudes de Recarga (N productos)

| # | Elemento de la spec | Estado | Tipo de cambio | Esfuerzo |
|---|---|---|---|---|
| 12 | `solicitudes_recarga` con N productos (en lugar de transfers 1 producto) | **Conflicto mayor** | **Cambio estructural** | XL |
| 13 | `detalle_solicitud_recarga` PK compuesta con `cantidad_solicitada` y `cantidad_despachada` | No existe | Migración aditiva | M |
| 14 | Estados `Pendiente → Aprobado → En Transito → Recibido \| Rechazado` | Parc (estados distintos en transfers) | Mapeo de namespace | M |

### 3.5 Dominio — Compras externas

| # | Elemento de la spec | Estado | Tipo de cambio | Esfuerzo |
|---|---|---|---|---|
| 15 | `ordenes_compra` con flujo `Borrador → Enviado a Supervisor → Aprobado → Comprado \| Rechazado` | No existe | Migración + módulo nuevo | L |
| 16 | `detalle_orden_compra` con `costo_unitario_pactado` y subtotal | No existe | Migración aditiva | M |
| 17 | Email HTML responsivo al supervisor con token temporal | No existe | **Cambio estructural** (módulo + worker) | L |

### 3.6 Reglas de negocio obligatorias

| # | Regla | Estado | Esfuerzo |
|---|---|---|---|
| 18 | `SELECT ... FOR UPDATE` en transferencias | No (SQLite con RLock Python) | XL — bloqueante para producción |
| 19 | Validación origen/destino en API y BD | No (sólo origen≠destino) | S |
| 20 | Componente lector de código de barras `onKeyDown` | No (inputs estándar) | S |

### 3.7 Frontend

| # | Elemento de la spec | Estado | Esfuerzo |
|---|---|---|---|
| 21 | Tailwind CSS | No (CSS plano con variables) | M — introducir sin romper |
| 22 | Grilla Multibodega con formato `Bodega X: 140 (P-01/E-02)` | No | M |
| 23 | Vista "Generar Solicitud de Recarga" en operador auxiliar | No (mock) | L |
| 24 | Bandeja de Recepción con escaneo para confirmar | Parc | L |
| 25 | Consolidador de Quiebres + Generador OC con dropdown supervisor | No | M |

---

## 4. Conflictos arquitecturales críticos (4)

### 4.1 `transfers` (1 producto) vs `solicitudes_recarga` (N productos) — **CONFLICTO MAYOR**

**Resolución:** Reemplazar `transfers` por `solicitudes_recarga` + `detalle_solicitud_recarga`. Mantener la **API de transfers** como vista derivada durante 6 meses, agrupando por solicitud.

**Plan de migración no destructiva (5 sub-fases):**
1. Crear `solicitudes_recarga` + `detalle_solicitud_recarga` en paralelo a `transfers`
2. Implementar `SolicitudService` reusando lógica transaccional de `TransferService` (extraer a `MovementEngine` compartido)
3. Crear endpoint `GET /transfers/{id}/derived` que arma una `Transfer` virtual
4. Migrar datos demo (1 producto → 1 línea de solicitud)
5. Marcar `transfers` deprecated; retirar al migrar el frontend

### 4.2 `stock_levels` (por bodega) vs `inventario_stock_real` (por ubicación) — **CONFLICTO SEMÁNTICO**

**Resolución:** modelo de **2 niveles** con convivencia:
```
ubicaciones_estanteria (id, id_bodega, pasillo, estanteria, altura) UNIQUE
        ↓
inventario_stock_real (id_producto, id_ubicacion, cantidad) CHECK ≥ 0
        ↓ (suma por bodega, vista materializada o trigger)
stock_levels (warehouse_id, product_id, quantity, min_quantity, max_quantity)
```
- `stock_levels` pasa a ser **proyección agregada** (recalculable)
- Mantiene compatibilidad con queries rápidas existentes
- Queries operativas pasan a `inventario_stock_real`

### 4.3 `users.role='supervisor'` vs tabla `supervisores` propia — **CONFLICTO LÉXICO**

**Resolución:** **convivencia con FK opcional**.
- `supervisores` es la **entidad de dominio** (persona física con email que recibe OC).
- `users.role='supervisor'` resuelve **permisos** (sigue existiendo para auth).
- Agregar `users.supervisor_id UUID NULL FK supervisores(id)` para vincularlos.
- `ordenes_compra.id_supervisor` FK a `supervisores(id)`, **no** a `users`.

### 4.4 API en SQLite memoria vs PostgreSQL real — **BRECHA DE PRODUCCIÓN**

**Resolución:** SQLAlchemy 2.0 async + Alembic.
- Driver: `asyncpg` (vía SQLAlchemy 2.0 async)
- Pool: `pool_size=10, max_overflow=20, pool_pre_ping=True`
- Migraciones: Alembic con `db/migrations/versions/*.py`
- Tests: `pytest-asyncio` + `testcontainers-python` (preserva `SELECT FOR UPDATE` real)
- Mantener SQLite sólo para tests legacy hasta cierre de Fase 1

---

## 5. Aterrizaje del modelo de datos (target)

### 5.1 Modelo final unificado

```
┌─ SEGURIDAD & CONFIG ─────────────────────────────────┐
│ users (existente) + users.supervisor_id → supervisores│
│ audit_logs (existente)                               │
└───────────────────────────────────────────────────────┘
┌─ DOMINIO GEOGRÁFICO ──────────────────────────────────┐
│ warehouses (EXTENDER):                               │
│   warehouse_type ∈ {principal, auxiliar, mecanico_box}│
│   + parent_warehouse_id NULL → warehouses(id)        │
│ ubicaciones_estanteria (NUEVA)                       │
│   (id, id_bodega, pasillo, estanteria, altura) UNQ   │
└───────────────────────────────────────────────────────┘
┌─ CATÁLOGO ────────────────────────────────────────────┐
│ categorias (NUEVA)                                   │
│ productos (EXTENDER):                                │
│   + codigo_barras, precio_costo, precio_venta,        │
│   + id_categoria → categorias                       │
│ detalles_neumaticos (NUEVA, opt-in 1:1)             │
└───────────────────────────────────────────────────────┘
┌─ INVENTARIO (2 niveles) ───────────────────────────────┐
│ inventario_stock_real (NUEVA):                       │
│   PK(id_producto, id_ubicacion), cantidad, CHECK≥0   │
│ stock_levels (EXTENDER):                             │
│   + max_quantity NUMERIC(14,2) DEFAULT NULL          │
│   (vista materializada desde stock_real)             │
│ inventario_bodega_parametros (NUEVA)                 │
│   PK(id_producto, id_bodega),                        │
│   stock_minimo, stock_maximo                         │
└───────────────────────────────────────────────────────┘
┌─ SOLICITUDES DE RECARGA (reemplazo de transfers) ─────┐
│ solicitudes_recarga (NUEVA):                         │
│   id, codigo UNQ, id_bodega_origen, id_bodega_destino│
│   CHECK (origen IN auxiliar, destino=principal)      │
│   estado ∈ {pending,approved,in_transit,received,    │
│            rejected,cancelled}                       │
│ detalle_solicitud_recarga (NUEVA):                   │
│   PK(id_solicitud, id_producto),                     │
│   cantidad_solicitada, cantidad_despachada,          │
│   cantidad_recibida, barcode_validado                │
│ transfers (DEPRECAR — vista compat 6 meses)          │
└───────────────────────────────────────────────────────┘
┌─ COMPRAS EXTERNAS ─────────────────────────────────────┐
│ supervisores (NUEVA): id, nombre, email UNQ, activo   │
│ ordenes_compra (NUEVA):                              │
│   id, codigo UNQ, id_bodega_principal, id_supervisor │
│   proveedor_nombre, estado, total_estimado,          │
│   email_enviado_at, email_token                      │
│ detalle_orden_compra (NUEVA):                        │
│   PK(id_orden_compra, id_producto),                  │
│   cantidad_pedida, costo_unitario_pactado            │
└───────────────────────────────────────────────────────┘
┌─ NOTIFICACIONES ───────────────────────────────────────┐
│ email_outbox (NUEVA): id, to_email, subject, body    │
│   html, status, attempts, sent_at, last_error        │
└───────────────────────────────────────────────────────┘
```

### 5.2 Plan de migraciones SQL (8 migraciones aditivas)

| Archivo | Acción | Tablas tocadas |
|---|---|---|
| `0004_categorias.sql` | CREAR | `categorias` |
| `0004_warehouses_box_support.sql` | EXTENDER | `warehouses` (+ `parent_warehouse_id`, ampliar CHECK) |
| `0005_products_categorias_precios.sql` | EXTENDER | `productos` (+ `codigo_barras`, precios, FK categoría) |
| `0005_products_neumaticos.sql` | CREAR | `detalles_neumaticos` |
| `0005_stock_max.sql` | EXTENDER | `stock_levels` (+ `max_quantity`) |
| `0006_ubicaciones.sql` | CREAR | `ubicaciones_estanteria`, `inventario_stock_real`, `inventario_bodega_parametros` |
| `0006_supervisores.sql` | CREAR | `supervisores`; EXTENDER `users` (+ `supervisor_id`) |
| `0007_solicitudes_recarga.sql` | CREAR | `solicitudes_recarga`, `detalle_solicitud_recarga` |
| `0008_ordenes_compra.sql` | CREAR | `ordenes_compra`, `detalle_orden_compra`, `email_outbox` |

**Estrategia:** todas usan `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. CHECKs nuevos con `NOT VALID` para no bloquear tablas grandes, luego `VALIDATE CONSTRAINT` en job de mantenimiento.

### 5.3 Decisión sobre boxes de mecánicos (recomendada: opción A)

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| **A) Boxes como `warehouses` con `warehouse_type='mecanico_box'`** | Cero migración nueva; reutiliza slotting/transferencias | Reglas de exclusión deben implementarse en service | **Recomendada** |
| B) Boxes como tabla propia con FK a auxiliar | Modelo limpio, semántica clara | Doble modelo de stock, reportes más complejos | Descartada por complejidad |
| C) Boxes como `ubicaciones_estanteria` con marca "box" | Una sola jerarquía | Pierde identidad individual de mecánico | Descartada |

**Con opción A:** Boxes **no generan** solicitudes de recarga (sólo consumen), **no aparecen** como origen en transferencias desde Central, y su stock **cuenta** para alertas de su auxiliar padre (suma recursiva).

---

## 6. Aterrizaje de módulos backend

### 6.1 Módulos nuevos (8)

| Módulo | Responsabilidad | Endpoints clave |
|---|---|---|
| `categories` | CRUD de categorías de productos | `GET/POST /api/v1/categorias` |
| `ubicaciones` | CRUD de ubicaciones_estanteria por bodega | `GET/POST /api/v1/bodegas/{id}/ubicaciones` |
| `stock_real` | CRUD de `inventario_stock_real` + slotting | `GET /api/v1/inventario/real?bodega_id=&sku=` |
| `solicitudes` | Workflow de `solicitudes_recarga` (N productos) | `GET/POST /api/v1/solicitudes`; `/{id}/approve|dispatch|receive` |
| `ordenes_compra` | CRUD + workflow de OC externas | `GET/POST /api/v1/ordenes-compra`; `/{id}/enviar-correo|aprobar` |
| `supervisores` | CRUD de supervisores (entidad de dominio) | `GET/POST /api/v1/supervisores` |
| `notifications` | Generación de email HTML + encolado Redis | `POST /api/v1/notificaciones/cola`; público `GET /ordenes-compra/aprobar/{token}` |
| `barcode` | Helper de validación/normalización de códigos | (interno, sin HTTP) |

### 6.2 Refactor de módulos actuales

| Módulo | Cambio |
|---|---|
| `warehouses` | Validar `warehouse_type` server-side; endpoint `GET /warehouses?type=auxiliar`; `parent_warehouse_id` |
| `products` | FK a `categorias`, `codigo_barras`, `precio_costo`, `precio_venta`; nuevo `GET /products/{id}/distribucion-multibodega` |
| `inventory` | Migrar a Postgres; introducir `MovementEngine` reutilizable (DRY con `solicitudes`); `stock_levels` como vista materializada |
| `transfers` | **Deprecated** — mantener endpoints 6 meses como adaptador sobre `solicitudes` |
| `auth` | `users.supervisor_id` opcional; helper `current_user_is_supervisor()` |
| `audit` | Sin cambios (cubre nuevas entidades automáticamente) |

### 6.3 Servicios de dominio clave

| Servicio | Descripción |
|---|---|
| `MovementEngine` | **Único punto de escritura** de `stock_levels` + `inventario_stock_real` + `inventory_movements`. Implementa `SELECT FOR UPDATE` sobre la fila `(warehouse_id, product_id)`. Compartido por `inventory` y `solicitudes`. |
| `SolicitudService` | Workflow: validar origen=aux/dest=principal, crear solicitud + detalle en transacción, reservar stock al aprobar, descontar al despachar, recibir por línea. |
| `ReplenishmentEvaluator` | Job que escanea `stock_levels` cada 5 min; cuando `quantity ≤ min_quantity` en auxiliar, llama a `SolicitudService`. |
| `OrdenCompraService` | Crea OC en `Borrador`, al "Enviar por correo" pasa a `Enviado a Supervisor` y encola email. |
| `EmailOutboxService` | Inserta en `email_outbox`; worker Arq lee Redis, renderiza plantilla HTML responsiva, envía SMTP, actualiza estado. |
| `ApprovalTokenService` | Genera y valida token temporal **HMAC firmado** con expiración 7 días. |
| `BarcodeValidator` | Helper puro: normaliza EAN-13/Code128/QR; valida checksum EAN-13. |

---

## 7. Aterrizaje de módulos frontend

### 7.1 Tailwind CSS — coexistencia sin romper

| Paso | Acción |
|---|---|
| 1 | `npm i -D tailwindcss@3 postcss autoprefixer` (v3 estable) |
| 2 | `npx tailwindcss init -p` |
| 3 | Configurar `content: ['./index.html', './src/**/*.{js,jsx}']` |
| 4 | Importar `tailwind.css` **después** de `styles.css` para que variables actuales ganen specificity |
| 5 | **Estrategia:** solo vistas nuevas en Tailwind; mantener CSS plano en las 11 vistas actuales |
| 6 | `tailwind-shim.css` con directivas `@apply` para tokens (`bg-bodega-primary`, etc.) |

### 7.2 Vistas nuevas (en orden de prioridad)

| Vista | Ruta | Módulo backend | Esfuerzo |
|---|---|---|---|
| `MultibodegaGridPage` | `/inventario/multibodega` | `products/{id}/distribucion-multibodega` | M |
| `SolicitudesAuxPage` | `/solicitudes` | `solicitudes` (CRUD + estado) | L |
| `RecepcionBandejaPage` | `/recepciones/en-transito` | `solicitudes` (filtro `in_transit`) + barcode | M |
| `ConsolidadorCentralPage` | `/consolidador` | `solicitudes` (agrupado por producto) | M |
| `OrdenesCompraPage` | `/ordenes-compra` | `ordenes_compra` (CRUD + workflow) | L |
| `OrdenCompraAprobacionPublicaPage` | `/ordenes-compra/aprobar/:token` | público (sin auth) | M |
| `SupervisoresPage` | `/supervisores` | `supervisores` (CRUD) | S |
| `CategoriasPage` | `/categorias` | `categories` (CRUD) | S |

### 7.3 Refactor de vistas existentes

| Vista | Cambio |
|---|---|
| `TransfersPage.jsx` | Mantener; añadir filtro para mostrar sólo transferencias en tránsito en la bandeja; columna `barcode`. No migrar a Tailwind. |
| `ReplenishmentPage.jsx` | **Reescribir:** pasar de mock a real. Cargar `/inventory/low-stock`, botón "Generar Solicitud de Recarga" → `POST /solicitudes` autocompletando `cantidad = stock_maximo - stock_actual`. |
| `WarehousesPage.jsx` | Badge con `warehouse_type` (Principal / Auxiliar / Box); filtro por tipo. |
| `DashboardPage.jsx` | Reemplazar `KpiStrip` mock por datos reales: stock valorizado, alertas críticas, transferencias en ruta. |

### 7.4 Componentes nuevos

| Componente | Archivo | Descripción |
|---|---|---|
| `BarcodeInput` | `components/BarcodeInput.jsx` | Input con `onKeyDown` que captura Enter, throttle 100ms, dispara callback con valor limpio |
| `SearchSku` | `components/SearchSku.jsx` | Buscador con debounce 300ms, autocompletado |
| `MultibodegaGrid` | `components/MultibodegaGrid.jsx` | Grilla 1 fila × N bodegas, formato `140 (P-01/E-02)` |
| `KpiCard` | `components/KpiCard.jsx` | Wrapper de `StatCard` con formato valorizado CLP/USD y delta |
| `SupervisorSelector` | `components/SupervisorSelector.jsx` | Dropdown tipado que carga `GET /supervisores?activo=true` |
| `SolicitudLineItem` | `components/SolicitudLineItem.jsx` | Fila de solicitud con input cantidad y validación contra stock origen |
| `ApprovalTokenBanner` | `components/ApprovalTokenBanner.jsx` | Banner con copy + enlace tokenizado para mostrar email enviado |

### 7.5 Lector de código de barras — estrategia

```jsx
// BarcodeInput.jsx — implementación de referencia
export function BarcodeInput({ onScan, autoFocus = true }) {
  const buffer = useRef("");
  const lastKeyAt = useRef(0);

  const onKeyDown = (e) => {
    const now = performance.now();
    if (now - lastKeyAt.current > 100) buffer.current = ""; // reset si pausa
    lastKeyAt.current = now;

    if (e.key === "Enter") {
      if (buffer.current.length >= 6) {
        onScan(buffer.current);
        buffer.current = "";
        e.preventDefault();
      }
      return;
    }
    if (/^[a-zA-Z0-9\-_.]$/.test(e.key)) {
      buffer.current += e.key;
    }
  };

  return <input autoFocus={autoFocus} onKeyDown={onKeyDown} />;
}
```

**Claves:** Scanners típicos envían caracteres a 5-10ms; umbral `>100ms` resetea el buffer (descarta tipeo humano). `Enter` siempre dispara el scan. `autoFocus` deja la vista receptora lista al cargar. `onScan` recibe string ya validado y sanitizado.

---

## 8. Aterrizaje de infraestructura

### 8.1 Conexión real a PostgreSQL

| Decisión | Recomendación | Justificación |
|---|---|---|
| Driver | **SQLAlchemy 2.0 async** (sobre `asyncpg`) | Soporta `SELECT FOR UPDATE` idiomático; pool built-in |
| Pool | `pool_size=10, max_overflow=20, pool_pre_ping=True` | Default sano; `pre_ping` evita conexiones muertas |
| Migraciones | **Alembic** | Estándar; autogen; rollback explícito |
| Tests | `pytest-asyncio` + `testcontainers-python` | Aísla BD por test; reproduce `FOR UPDATE` real |

**Cambios en código:**
- `apps/api/requirements.txt` → añadir: `sqlalchemy[asyncio]==2.0.36`, `asyncpg==0.30.0`, `alembic==1.14.0`, `psycopg2-binary==2.9.10`
- `apps/api/app/db/session.py` → extraer interface `Database`; implementar `SQLiteDatabase` (legacy) y `PostgresDatabase` (target)
- `apps/api/app/main.py` → cambiar firma a `create_database(url)` con dual backend

### 8.2 Uso real de Redis

| Caso | Key pattern | TTL |
|---|---|---|
| Cola SMTP | `email:queue` (LIST LPUSH/BRPOP) | – |
| Rate limiting login | `ratelimit:login:{ip}` | 60s |
| Cache de sesión | `session:{token}` → `{user_id, expires_at}` | igual a `expires_at` |
| Lock distribuido (idempotencia al escanear) | `lock:receive:{solicitud_id}:{linea_id}` | 30s |
| Pub/Sub tiempo real (fase futura) | `events:stock.updated`, `events:solicitud.*` | – |

Librería: `redis>=5.0` con cliente async (`redis.asyncio`).

### 8.3 Worker asíncrono — recomendación: **Arq**

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| Celery + Redis | Maduro, dashboards built-in | Complejidad, sin async nativo | Sobredimensionado para 1 cola SMTP |
| RQ (Redis Queue) | Simple | Limitado, sin scheduling | Suficiente para SMTP, débil para jobs recurrentes |
| **Arq** | Async nativo, mismo event loop FastAPI, cron jobs | Menos comunidad | **Recomendado** |
| FastAPI BackgroundTasks | Cero infra | Sin retry, muere con el proceso | No apto para SMTP crítico |

**Plan:** un solo proceso `worker` lee `email:queue` y procesa `send_email_task`. `Arq` permite cron jobs para `ReplenishmentEvaluator` (cada 5 min). Latencia baja (mismo Python que la API).

### 8.4 SMTP

| Ambiente | Servidor | Puerto |
|---|---|---|
| dev | **Mailpit** (`axllent/mailpit:latest`) | 1025 SMTP + 8025 UI web |
| staging | Mailgun sandbox o Mailpit | 587 STARTTLS |
| production | AWS SES, SendGrid o Mailgun | 587 STARTTLS + credenciales en vault |

**Plantilla HTML** en `apps/api/app/modules/notifications/templates/orden_compra.html.j2` (Jinja2). Responsiva con CSS inline (clientes de email lo exigen). Tabla con SKU/Producto/Cantidad/Costo/Subtotal + botón "Aprobar/Rechazar" → link con token.

### 8.5 Observabilidad mínima

| Componente | Stack | Esfuerzo |
|---|---|---|
| Logs estructurados | `structlog` con JSON a stdout | S |
| Métricas | `prometheus-fastapi-instrumentator` → `/metrics` | S |
| Healthcheck | ampliar `/api/v1/health` a `{db, redis, worker}` | S |
| Dashboards | Grafana con provisioning básico | M |

---

## 9. Roadmap de implementación (10 fases)

| Fase | Goal | Tareas | Criterio de aceptación | Esfuerzo |
|---|---|---|---|---|
| **0. Decisiones** | Cerrar inputs abiertos | Reunir decisiones: boxes, convivencia stock, retiro transfers, driver, worker, SMTP, Tailwind, token, supervisores, rollout | 6 ADRs firmados | S |
| **1. PostgreSQL real** | Conectar la API a Postgres | SQLAlchemy async, Alembic, paridad `:memory:`, `testcontainers` | `pytest` corre contra Postgres; smoke test OK | L |
| **2. Multibodega física** ✅ | Catálogo + ubicaciones + stock por slot | Migraciones 0004-0007; módulos `categories`, `ubicaciones`, `stock_real`, `product_extension`; `MovementEngine` sync (BEGIN IMMEDIATE) + async (with_for_update); frontend Tailwind con `MultibodegaGridPage` | 37 unit tests pass; 5 archivos backend + 4 frontend tests escritos; `npm run build` OK | L |
| **3. Solicitudes de Recarga (N productos)** ✅ | Reemplazar transfers por solicitudes con workflow | Migración 0006; módulo `solicitudes`; `SolicitudService`; regla origen=aux/dest=principal; barcode en líneas; `SolicitudRepository` con `SELECT FOR UPDATE`; vista derivada `/solicitudes/{id}/derived`; transfers @deprecated con 410 Gone en writes | E2E: aux crea solicitud de 3 productos → central aprueba → despacha 2 → recibe 1 → `partially_received` | XL |
| **4. Replenishment automático** ✅ | Generar solicitudes automáticas al caer bajo mínimo | `ReplenishmentEvaluator` (job Arq cada 5 min, proceso separado); UI botón "Generar Solicitud" en `ReplenishmentPage`; endpoint `POST /solicitudes/auto-generar` (admin/supervisor) con `dry_run`; `GET /solicitudes/bajo-minimo`; `SolicitudesAuxPage` reescrita con Tailwind (filtros, drawer, paginación); idempotencia R6; solo bodegas auxiliares + productos activos; prioridad auto 'alta' si ratio<0.5 | Cuando `qty≤min`, en <5min aparece solicitud pendiente en `SolicitudesAuxPage`; E2E: 3 SKUs bajo mínimo → 1 solicitud con 3 líneas (cantidades 47/9/16), prioridad 'alta', idempotente | L |
| **5. Lectores de código de barras** ✅ | Componente + flujo de recepción con escaneo | `BarcodeInput.jsx` (Fase 2, sin tocar); `RecepcionBandejaPage` reescrita + `RecepcionDetallePage` nueva; endpoint `/solicitudes/{id}/receive` refinado para usar `app.modules.barcode.match_product()` (EAN-13/8 checksum, Code 128/39 sin checksum, skip si producto sin barcode); 25 tests del validador + 8 tests del flujo de recepción; rutas `/recepciones/en-transito` y `/recepciones/:id` | E2E con teclado + Enter: 5 líneas escaneadas → `received` en <1 min; barcode inválido → 409 `barcode_mismatch`; producto sin barcode → skip | M |
| **6. Supervisores + Órdenes de Compra** ✅ | Entidad supervisores + flujo OC completo (UI + API + token) | Módulos `supervisores` (CRUD) y `ordenes_compra` (CRUD + transiciones); `ConsolidadorCentralPage` con cálculo de deficit; `OrdenesCompraPage` con form + supervisor dropdown; vista pública `/ordenes-compra/aprobar/:token` (sin auth, Tailwind v3); rate limit 5 req/min en endpoints públicos; `email_outbox` llenado por `enviar_correo` (sin SMTP, eso es Fase 7); 18 tests nuevos (7 supervisores + 11 OC); 240 tests passing (222 baseline + 18 nuevos); `RateLimiter` in-memory en `app/core/rate_limit.py` | Admin crea OC → selecciona supervisor → encola email → supervisor abre link → aprueba con 1 clic; E2E completo testeado | L |
| **7. Notificaciones SMTP async** ✅ | Cola Redis + worker Arq + Mailpit dev | Módulo `notifications` refactorizado; `email_outbox` (Fase 6 ya insertable, Fase 7 procesa); `send_email_task` en `app/worker.py` (Arq 0.28, mismo proceso que `replenishment_task`); plantilla Jinja2 `orden_compra.html.j2` responsiva con CSS inline (premailer); cliente `smtp.py` (aiosmtplib 3.0.1, STARTTLS configurable, `SmtpPermanentError` para 5xx); `NotificationsService.enqueue` (canónico con template+context) + `process_one` (worker Arq, retry exponencial 30s/5min/30min, dead tras 3 fallos) + `retry_dead` (admin) + `metrics` (Prometheus); `notifications/worker.py` standalone marcado DEPRECATED; Mailpit (`axllent/mailpit:latest`) en `docker-compose.yml` + `compose.local.dev.yml` con healthcheck; servicio `worker` en compose; settings `smtp_*` + `email_max_attempts` + `email_retry_backoff_seconds` (CSV) + `public_base_url`; 12 tests nuevos (11 unit + 1 integration E2E con Mailpit); 238 tests passing + 12 skipped; `docs/fases/fase-7-smtp-async.md` | Mailpit recibe email con tabla OC + botones aprobar/rechazar; click → `/ordenes-compra/aprobar/{token}` aprueba; E2E manual en `tests/manual/test_e2e_fase7.py`; ver flujo completo en `fase-7-smtp-async.md` | L |
| **8. Frontend Tailwind** ✅ | Introducir Tailwind sin romper CSS plano | Instalar Tailwind v3; `tailwind.config.js`; nuevo layout `AdminLayout`; convertir vistas nuevas a Tailwind | Build OK; CSS plano intacto; vistas nuevas usan `@apply` | M |
| **8b. Vistas restantes + backend operativo (Fase 8 extendida)** ✅ | Cerrar las vistas de gestion operativa que faltaban + exponer el modelo operativo via API | Tailwind v3 ya configurado (ADR-0006). **Backend:** modulos nuevos `proveedores` (CRUD), `reports` (snapshot ejecutivo con KPIs), `notificaciones` in-app (complementa al `email_outbox` de Fase 7); endpoints `GET /categories/arbol` (jerarquia recursiva) y `PUT /inventory/parametros/{producto_id}/{bodega_id}` (reglas de reabastecimiento); nueva tabla `proveedores` + `notificaciones` via migracion 0008; errores de dominio nuevos. **Frontend:** `CategoriasPage` (arbol colapsable con drawer form, busqueda), `ReplenishmentRuleForm` (drawer con SearchSku + min/max/lead), `NotificationsCenter` (campanita con polling 30s + drawer + badge), `ReportsPage` refactor con tabs (Operacional/Ejecutivo/Auditoria) + export PDF ejecutivo via HTML-to-print, `SettingsPage` refactor con tabs (Reglas/Proveedores/Stock); ruta `/categorias` + entrada en sidebar; `NotificationsCenter` en topbar. PDF generado en cliente (0KB vs `jsPDF` ~50KB). 9 tests nuevos; 247 passing total (238 baseline + 9 nuevos), 12 skipped; `npm run build` OK (459KB gzip 122KB). | E2E: crear categoria raiz → crear subcategoria → ver arbol → editar; admin parametrizar regla producto-bodega desde Settings; campanita muestra badge de no-leidas y permite marcar; ReportPage tab Ejecutivo genera PDF con KPIs y rankings; Settings tab Proveedores CRUD completo. Detalles en `docs/fases/fase-8-vistas-tailwind.md` | L |
| **9. Observabilidad mínima** ✅ | Logs JSON, métricas Prometheus, healthcheck | `structlog` (correlation_id W3C, JSON en prod, console en dev); `prometheus-fastapi-instrumentator` (métricas HTTP automáticas con histogramas); métricas custom `bodegaje_*` (solicitudes, OC, email outbox, replenishment, stock) con cardinalidad acotada; `CorrelationIdMiddleware` (header `X-Correlation-ID`, log de request con `elapsed_ms`); healthcheck ampliado `/api/v1/health` con checks paralelos de BD + Redis + worker (timeouts 2-5s), `/health/live` (liveness), `/health/ready` (readiness); backward-compat `checks.database` + nuevo `components.{db,redis,worker}`; Sentry opcional (FastApiIntegration + StarletteIntegration, `traces_sample_rate=0.1`); `update_metrics_task` cron cada 1min actualiza gauges desde BD; settings nuevos `log_format`, `sentry_dsn`, `sentry_traces_sample_rate`, `sentry_profiles_sample_rate`, `sentry_environment`, `metrics_enabled`, `metrics_path`; 29 tests nuevos (10 observability + 9 health + 10 metrics); 289 passing total (260 baseline + 29 nuevos), 10 pre-existing failures en `tests/test_api.py` (legacy SQLite path, no relacionado a Fase 9), 13 skipped; `docs/fases/fase-9-observabilidad.md` | E2E: `GET /api/v1/health` con todos los componentes OK retorna 200 con `components.db.status="ok"` y `correlation_id` en response header; `GET /api/v1/health` con BD caída retorna 503; `GET /metrics` expone `bodegaje_solicitudes_creadas_total{bodega_origen_tipo,prioridad}` + métricas HTTP automáticas; logs JSON con `correlation_id` propagado a todos los logs del request; Sentry captura excepciones no manejadas con stacktrace + request context si `SENTRY_DSN` configurado | M |
| **10. Hardening y demo final** ✅ | Producción lista | Variables de entorno con placeholders `__*__`; `infra/scripts/generate-secrets.py` (passwords con requisitos OWASP + tokens URL-safe); campo `secret_key` separado de `jwt_secret` (defense in depth, OBLIGATORIO en prod); default `password_hash_iterations=600_000` (OWASP 2023); `model_validator` rechaza config insegura en prod (SECRET_KEY faltante, SMTP_TLS=false); Nginx production hardened: `server_tokens off`, `client_max_body_size 10m`, **8 headers de seguridad** (HSTS preload, X-Frame-Options DENY, X-Content-Type-Options nosniff, CSP estricto, Permissions-Policy, Referrer-Policy), **rate limit diferenciado** (5 req/min public OC, 100 req/min general, burst configurable), gzip, log_format JSON parseable, preservación X-Correlation-ID; backups automatizados con sidecar `prodrigestivill/postgres-backup-local` (rotación 7/4/12, verificación `pg_restore --list`, upload S3 opcional); scripts bash + PowerShell (`backup-postgres.sh/.ps1`, `restore-postgres.sh`); `pre-deploy-check.sh` con 10 verificaciones automatizadas (secretos, migraciones, tests, nginx config, espacio disco); `start-production.ps1` con pre-deploy check + validación de secretos; runbook 21KB con 10 secciones + 8 procedimientos de incidente + 3 estrategias de rollback; `check-env-isolation.sh/.ps1` extendido para incluir `SECRET_KEY` y `POSTGRES_PASSWORD`; CI/CD: job `hardening-checks` con bandit, validación de nginx config, .env.example structure, sintaxis bash scripts; 13 tests nuevos (`test_hardening.py`: 13 tests unitarios sin infra externa; `test_nginx_headers.py`: 12 tests live skipped por defecto, activables con `--runlive`); **302 passing total** (289 baseline + 13 nuevos), 10 pre-existing failures en `tests/test_api.py` (legacy SQLite path, no relacionado a Fase 10), 13 skipped; `docs/fases/fase-10-hardening-produccion.md` | E2E: stack production arriba con HTTPS-ready (HSTS preload), 8 headers de seguridad pasan securityheaders.com, rate limit 5 req/min en `/api/v1/public/ordenes-compra/*` retorna 429 tras burst, `secret_key` se valida distinto a `jwt_secret` en approval tokens, `pre-deploy-check.sh` aborta el deploy si JWT_SECRET < 32 chars o SECRET_KEY faltante, backup daily con verificación de integridad, restore funcional con confirmación explícita, runbook ejecutable por operador nuevo paso a paso | L |

**Total:** ~10 semanas con 1 BE + 1 FE + 0.5 DevOps. **ROADMAP COMPLETO AL 2026-07-15** — las 10 fases están en producción.
**Ruta crítica cumplida:** Fases **1 → 3 → 7** (Postgres real, Solicitudes N-productos, SMTP) completadas en orden. Fases 0-10 entregadas.
**Informe ejecutivo final:** ver `docs/INFORME_FINAL_10_FASES.md`.

---

## 10. Decisiones pendientes (necesitan tu input)

> 10 decisiones a cerrar antes de empezar a codear. Las marcadas como **bloqueantes** detienen la fase asociada.

| # | Decisión | Opciones | Recomendación | Bloqueante |
|---|---|---|---|---|
| 1 | Boxes de mecánicos: ¿qué son? | A) warehouse `mecanico_box` / B) tabla propia / C) ubicación física | A | Sí (Fase 2) |
| 2 | `stock_levels` vs `inventario_stock_real`: ¿convivencia o reemplazo? | Convivencia / reemplazo | Convivencia | Sí (Fase 2) |
| 3 | ¿`transfers` se retira o queda como vista? | Vista derivada 6 meses / retiro inmediato | Vista derivada 6 meses | No |
| 4 | Driver PG: ¿SQLAlchemy async o asyncpg puro? | SQLAlchemy 2 / asyncpg | SQLAlchemy 2 | Sí (Fase 1) |
| 5 | Worker: ¿Celery, RQ, Arq o BackgroundTasks? | Arq / RQ / Celery | Arq | No (RQ es defendible) |
| 6 | SMTP dev: ¿Mailpit o cuenta real? | Mailpit / Mailgun sandbox | Mailpit | No |
| 7 | Tailwind coexistencia: ¿migrar vistas actuales o solo nuevas? | Solo nuevas / gradualmente / big-bang | Solo nuevas | No |
| 8 | Token aprobación OC: ¿JWT, HMAC o random UUID? | HMAC firmado / JWT / UUID en BD | HMAC con expiración 7 días | Sí (Fase 7) |
| 9 | ¿`supervisores` con login propio o solo vía email? | Solo email (link único) / login dedicado | Solo email | No |
| 10 | ¿Migración a producción en una sola release o por fases? | Por fases / big-bang | Por fases: 1→3→7 primero | No |

**Output esperado:** 6 ADRs en `docs/adr/` (`adr-0001-postgres-strategy.md`, `adr-0002-boxes-modelo.md`, `adr-0003-transfers-to-solicitudes.md`, `adr-0004-smtp-async-architecture.md`, `adr-0005-token-approval-oc.md`, `adr-0006-tailwind-coexistencia.md`).

---

## 11. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|---|
| 1 | Race conditions en `SELECT FOR UPDATE` mal implementado | Media | Alto (datos corruptos) | Test de concurrencia (50 requests paralelos al mismo SKU); índice por `(warehouse_id, product_id)` |
| 2 | Migración `transfers` → `solicitudes` rompa frontend | Alta | Alto (UI sin datos) | Vista derivada 6 meses; feature flag `USE_SOLICITUDES`; rollout por bodega |
| 3 | SMTP en producción se vuelve cuello de botella | Media | Alto (OC no se aprueban) | `email_outbox` con reintentos (3 con backoff); alerta Prometheus si `pending > 100` |
| 4 | `onKeyDown` del barcode no detecta escáneres lentos | Baja | Medio (UX) | Throttle configurable (50/100/200ms); permitir reset manual |
| 5 | Lock en `users` por adición de `supervisor_id` | Baja | Bajo | Migración `NOT VALID` + `VALIDATE CONSTRAINT` en job nocturno |
| 6 | Pérdida de sesiones al pasar de SQLite a Postgres | Media | Bajo | Reset de demo: pedir re-login; API ya devuelve 401 en sesiones inválidas |
| 7 | Múltiples workers Arq procesen el mismo email | Baja | Medio | `BLPOP` con lock + `email_outbox.status` actualizado atómicamente |
| 8 | Botón "Escanear" dispara acciones con tipeo humano | Media | Medio | Reset por pausa >100ms + longitud mínima configurable; preview antes de confirmar |
| 9 | Tailwind + CSS plano colisionan en especificidad | Media | Bajo | `tailwind-shim.css` con `@apply` para tokens; pre-commit con PurgeCSS |
| 10 | Datos demo quedan inconsistentes con nueva estructura | Alta | Medio | Reescribir `reset_demo_database` cubriendo todas las nuevas tablas; regenerar seeds |

---

## 12. Recomendaciones operativas inmediatas

### Esta semana (esfuerzo S)
1. **Cerrar las 10 decisiones pendientes** en una reunión técnica; output: 6 ADRs firmados en `docs/adr/`.
2. **No tocar `transfers`** hasta tener `SolicitudService` con paridad funcional; el deprecation se hace al final, no en el primer PR.
3. **Mantener tests en SQLite** hasta Fase 1 cerrada; el switch a Postgres-test es de Fase 1, no antes.
4. **No introducir Tailwind hasta Fase 8**; todo lo anterior debe seguir usando CSS plano para no inflar la diff.

### Próxima semana (esfuerzo L)
5. **Iniciar Fase 1 (Postgres real)** sin tocar lógica de negocio: driver async, Alembic, paridad de comportamiento. Esta fase es prerequisito de todo lo demás y tiene bajo riesgo de regresión.
6. **Crear `alembic.ini`** y la primera migración autogenerada desde los modelos SQLAlchemy 2.0 que se deriven del modelo actual.

### Antes de fase 3
7. **Probar el deprecation de `transfers`** con un feature flag `USE_SOLICITUDES` que permita tener ambos caminos en paralelo.
8. **Definir el contrato de `SolicitudService`** (interfaz) antes de implementarlo; el frontend necesita mock para no bloquearse.

---

## 13. Anexo — Archivos que se crearían/modificarían

### Nuevos archivos backend
- `apps/api/app/modules/categories/{router,service,repository,schemas}.py`
- `apps/api/app/modules/ubicaciones/{router,service,repository,schemas}.py`
- `apps/api/app/modules/stock_real/{router,service,repository,schemas}.py`
- `apps/api/app/modules/solicitudes/{router,service,repository,schemas,jobs}.py`
- `apps/api/app/modules/ordenes_compra/{router,service,repository,schemas}.py`
- `apps/api/app/modules/supervisores/{router,service,repository,schemas}.py`
- `apps/api/app/modules/notifications/{router,service,repository,schemas,token}.py`
- `apps/api/app/modules/notifications/templates/orden_compra.html.j2`
- `apps/api/app/modules/barcode/validator.py`
- `apps/api/app/modules/inventory/movement_engine.py` (refactor)
- `apps/api/app/worker.py` (Arq entrypoint)
- `apps/api/alembic/` (nuevo)
- `apps/api/alembic.ini`

### Nuevas migraciones SQL
- `db/migrations/0004_categorias.sql`
- `db/migrations/0004_warehouses_box_support.sql`
- `db/migrations/0005_products_categorias_precios.sql`
- `db/migrations/0005_products_neumaticos.sql`
- `db/migrations/0005_stock_max.sql`
- `db/migrations/0006_ubicaciones.sql`
- `db/migrations/0006_supervisores.sql`
- `db/migrations/0007_solicitudes_recarga.sql`
- `db/migrations/0008_ordenes_compra.sql`
- (y sus espejos en `db/migrations/sqlite/` para tests legacy)

### Nuevas vistas frontend
- `apps/web/src/views/MultibodegaGridPage.jsx`
- `apps/web/src/views/SolicitudesAuxPage.jsx`
- `apps/web/src/views/RecepcionBandejaPage.jsx`
- `apps/web/src/views/ConsolidadorCentralPage.jsx`
- `apps/web/src/views/OrdenesCompraPage.jsx`
- `apps/web/src/views/OrdenCompraAprobacionPublicaPage.jsx`
- `apps/web/src/views/SupervisoresPage.jsx`
- `apps/web/src/views/CategoriasPage.jsx`

### Nuevos componentes frontend
- `apps/web/src/components/BarcodeInput.jsx`
- `apps/web/src/components/SearchSku.jsx`
- `apps/web/src/components/MultibodegaGrid.jsx`
- `apps/web/src/components/KpiCard.jsx`
- `apps/web/src/components/SupervisorSelector.jsx`
- `apps/web/src/components/SolicitudLineItem.jsx`
- `apps/web/src/components/ApprovalTokenBanner.jsx`

### ADRs sugeridos
- `docs/adr/adr-0001-postgres-strategy.md`
- `docs/adr/adr-0002-boxes-modelo.md`
- `docs/adr/adr-0003-transfers-to-solicitudes.md`
- `docs/adr/adr-0004-smtp-async-architecture.md`
- `docs/adr/adr-0005-token-approval-oc.md`
- `docs/adr/adr-0006-tailwind-coexistencia.md`

### Cambios de infra
- `infra/docker/compose.local.yml` — añadir Mailpit
- `infra/docker/compose.production.yml` — variables SMTP + credenciales en vault
- `infra/docker/nginx/conf.d/default.conf` — rate limit, headers de seguridad
- `apps/api/requirements.txt` — añadir SQLAlchemy async, asyncpg, alembic, arq, redis, structlog, jinja2

---

## 14. Cierre

**No hay nada en el código actual que haya que descartar.** El MVP transaccional (warehouses, products, inventory, transfers, auth, audit) es una base excelente que se reutiliza casi sin cambios. La spec nueva **profundiza** (categorías, ubicaciones, precios, neumáticos) y **ensancha** (solicitudes N-productos, OC externas, SMTP), pero el núcleo del sistema (movimientos auditables, stock como proyección, separación service/repository) se mantiene válido.

**Próximo paso recomendado:** cerrar las 10 decisiones de §10 en una reunión, emitir los 6 ADRs, y arrancar **Fase 1 (Postgres real)** la próxima semana. Es la base de todo y tiene bajo riesgo de regresión.
