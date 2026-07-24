# Documento 2 — Modelo de Base de Datos en Tercera Forma Normal (3FN)

**Proyecto:** Sistema de Gestión de Inventario Multi-Bodega (`bodega`)
**Versión:** 1.0 — 2026-07-22
**Origen:** sección 22.1 (2) de `PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md`
**Fuente:** modelos SQLAlchemy en `apps/api/app/db/models/`, migraciones en
`db/migrations/0001..0008` y `db/migrations/sqlite/0009`.

---

## 1. Propósito

Documentar el modelo relacional vigente, justificar las decisiones de
normalización, e identificar dónde se introducen **desnormalizaciones
controladas** necesarias para rendimiento o dominio. El modelo cumple 3FN
globalmente; las excepciones se justifican tabla por tabla.

---

## 2. Convenciones globales

- **Identificadores:** `UUID` v4 en todas las PK (`uuid_generate_v4` en
  Postgres, generado en Python para SQLite).
- **Timestamps:** `timestamptz` con `default now()`. Tablas de auditoría
  (`audit_logs`, `notificaciones`, `email_outbox`) registran `created_at`
  con granularidad de milisegundos.
- **Cantidades:** `numeric(14, 2)`. Dos decimales; nunca negativo donde la
  regla de negocio lo prohíba (CHECK en BD).
- **Codificación:** UTF-8. Todos los `varchar` con `btrim(...) <> ''` CHECK
  cuando el campo es obligatorio y de texto.
- **Nombres en singular:** `warehouses`, `products`, `solicitudes_recarga`,
  `detalle_solicitud_recarga`, etc. La migración histórica a plural
  convivió con la normalización posterior.
- **Borrado lógico vs físico:** casi todo es `RESTRICT`; las dependencias
  1:N con ciclo de vida propio son `CASCADE` (ej: `detalle_solicitud_recarga`
  se borra con la solicitud padre).

---

## 3. Diagrama lógico de alto nivel

```
┌────────────┐      ┌──────────────────┐      ┌────────────┐
│  users     │──┐   │  warehouses      │◀─┐   │ categories │
└────────────┘  │   └──────────────────┘  │   └─────┬──────┘
       │        │           │              │         │
       │        │           │              │         │ 1:N
       │        │           │              │         ▼
       ▼        │           ▼              │   ┌────────────┐
┌────────────┐  │   ┌──────────────────┐  │   │  products  │
│ audit_logs │  │   │  stock_levels    │  │   └─────┬──────┘
└────────────┘  │   └──────────────────┘  │         │ 1:1
                │           │              │         ▼
                │           │              │   ┌────────────────────┐
                │           ▼              │   │detalles_neumaticos │
                │   ┌──────────────────┐  │   └────────────────────┘
                │   │inventory_movements│ │         │
                │   └──────────────────┘  │         │
                │                          │         │
                │   ┌────────────────────┐ │         │
                │   │ubicaciones_est.    │◀┘         │
                │   └────────────────────┘ │         │
                │           │              │         │
                │           ▼              │         │
                │   ┌────────────────────┐ │         │
                │   │inventario_stock_   │ │         │
                │   │   real (Nivel 2)   │ │         │
                │   └────────────────────┘ │         │
                │                          │         │
                │   ┌────────────────────┐ │         │
                │   │solicitudes_recarga │─┼─────────┘
                │   └────────────────────┘ │
                │           │              │
                │           ▼              │
                │   ┌────────────────────┐ │
                │   │detalle_solicitud_  │─┘
                │   │   recarga          │
                │   └────────────────────┘
                │
                │   ┌────────────────────┐
                │   │  proveedores       │
                │   └────────────────────┘
                │           │
                │           ▼
                │   ┌────────────────────┐
                │   │ ordenes_compra     │
                │   └────────────────────┘
                │           │
                │           ▼
                │   ┌────────────────────┐
                │   │detalle_orden_      │
                │   │   compra           │
                │   └────────────────────┘
                │
                │   ┌────────────────────┐
                │   │  supervisores      │
                │   └────────────────────┘
                │
                └──► notificaciones / email_outbox / audit_logs
```

---

## 4. Tablas — vista por tabla

### 4.1 `warehouses`

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id` | UUID PK | | |
| `code` | varchar(50) | UNIQUE, NOT BLANK | Identificador humano |
| `name` | varchar(150) | UNIQUE (agregado Fase 0 hardening), NOT BLANK | |
| `warehouse_type` | varchar(30) | CHECK ∈ `{principal, auxiliar, mecanico_box}` | Ver RB-08 |
| `is_active` | bool | default `true` | Borrado lógico |
| `created_at`, `updated_at` | timestamptz | default `now()` | |

**3FN:** la tabla está en BCNF. `code` y `name` son candidatos únicos; no
hay dependencias transitivas. La unicidad de `name` (no presente en la
propuesta original) se agregó para soportar rechazo de duplicados a nivel
HTTP.

**Índices:**

- `idx_warehouses_type_active (warehouse_type, is_active)` para filtros de
  listado.

---

### 4.2 `products`

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id` | UUID PK | | |
| `sku` | varchar(80) | UNIQUE, NOT BLANK | |
| `name` | varchar(150) | NOT BLANK | |
| `unit` | varchar(20) | NOT BLANK | "unidad", "caja", "kg", etc. |
| `codigo_barras` | varchar(100) | UNIQUE nullable | |
| `id_categoria` | UUID FK → `categories(id)` ON DELETE SET NULL | nullable | |
| `precio_costo` | numeric(14,2) | default 0, `>= 0` | |
| `precio_venta` | numeric(14,2) | default 0, `>= 0` | |
| `is_active` | bool | default `true` | |
| `created_at`, `updated_at` | timestamptz | | |

**3FN:** cumple. La separación entre `products` y `detalles_neumaticos`
responde a 3FN: atributos que no aplican a todos los productos van a
sub-recurso 1:1.

**Índices:**

- `uq_products_codigo_barras` (UNIQUE)
- `idx_products_id_categoria`
- `idx_products_active (is_active)` (búsqueda por catálogo)

---

### 4.3 `detalles_neumaticos` (1:1 con `products`)

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `producto_id` | UUID PK FK → `products(id)` | ON DELETE CASCADE | |
| `ancho` | int | `> 0` | |
| `perfil` | int | `> 0` | |
| `aro` | int | `> 0` | |
| `indice_carga` | int | nullable | |
| `indice_velocidad` | varchar(5) | nullable | |
| `dot` | varchar(20) | nullable | DOT tire code |

**3FN:** PK es FK, relación 1:1. Pertinente solo para neumáticos; el
resto de los productos no tienen fila aquí.

---

### 4.4 `categories`

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id` | UUID PK | | |
| `nombre` | varchar(100) | UNIQUE, NOT BLANK | |
| `descripcion` | varchar(500) | nullable | |
| `parent_id` | UUID FK self | ON DELETE SET NULL | |
| `is_active` | bool | default `true` | |
| `created_at`, `updated_at` | timestamptz | | |

**3FN:** cumple. La jerarquía se modela con self-FK, no requiere tabla
de closure.

**Índices:**

- `uq_categories_nombre_normalized` (índice único sobre `lower(btrim(nombre))`).
  Esto es **desnormalización funcional controlada** que evita una vista
  materializada para búsquedas case-insensitive.

---

### 4.5 `ubicaciones_estanteria`

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id` | UUID PK | | |
| `id_bodega` | UUID FK → `warehouses(id)` | ON DELETE CASCADE | |
| `pasillo`, `estanteria`, `altura` | int | `> 0` | |
| `descripcion` | varchar(200) | nullable | |
| `is_active` | bool | default `true` | |
| `created_at`, `updated_at` | timestamptz | | |

**UNIQUE compuesto:** `(id_bodega, pasillo, estanteria, altura)`.

**3FN:** la clave de negocio es la tupla `(bodega, pasillo, estantería,
altura)`. El `id` UUID es surrogate. No hay atributos derivados.

---

### 4.6 `stock_levels` (Nivel 1: agregado por bodega)

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id` | UUID PK | | |
| `warehouse_id` | UUID FK → `warehouses(id)` | | |
| `product_id` | UUID FK → `products(id)` | | |
| `quantity` | numeric(14,2) | default 0, `>= 0` | CHECK |
| `min_quantity` | numeric(14,2) | default 0, `>= 0` | CHECK |
| `max_quantity` | numeric(14,2) | nullable, `>= 0` (si presente) | CHECK |
| `updated_at` | timestamptz | | |

**UNIQUE compuesto:** `(warehouse_id, product_id)`.

**3FN:** cumple. `min_quantity` y `max_quantity` son atributos del par
bodega-producto (no del producto solo), por lo tanto pertenecen aquí y
no en `products`.

**Desnormalización controlada:** `max_quantity` se mantiene aquí aunque
conceptualmente sea un parámetro de reabastecimiento. Esto evita JOIN
adicional en la ruta crítica de alertas.

---

### 4.7 `inventario_stock_real` (Nivel 2: por ubicación)

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id_producto` | UUID FK → `products(id)` | ON DELETE CASCADE | parte de PK |
| `id_ubicacion` | UUID FK → `ubicaciones_estanteria(id)` | ON DELETE CASCADE | parte de PK |
| `cantidad` | numeric(14,2) | `>= 0` | CHECK |
| `updated_at` | timestamptz | | |

**PK compuesta:** `(id_producto, id_ubicacion)`.

**3FN:** la PK es la clave de negocio; no hay surrogate. Esto es 3FN
estricto y permite upserts `ON CONFLICT (id_producto, id_ubicacion)`.

**Vista materializada equivalente:** el Nivel 1 (`stock_levels`) se puede
calcular como `SUM(inventario_stock_real.cantidad) WHERE id_bodega = ?`. En
esta versión, ambos se mantienen por aplicación (no hay triggers).

---

### 4.8 `inventory_movements`

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id` | UUID PK | | |
| `warehouse_id` | UUID FK → `warehouses(id)` | | |
| `product_id` | UUID FK → `products(id)` | | |
| `movement_type` | varchar(30) | CHECK ∈ `{in, out, adjustment_in, adjustment_out}` | |
| `quantity` | numeric(14,2) | `> 0` | el signo lo da el tipo |
| `reference_type` | varchar(50) | nullable | ej: `solicitud`, `orden_compra` |
| `reference_id` | varchar(100) | nullable | UUID de la fuente |
| `notes` | text | nullable | |
| `created_at` | timestamptz | | |

**3FN:** cumple. `reference_*` es polimórfico, lo cual es una
desnormalización deliberada: una sola tabla cubre todas las fuentes de
movimiento sin JOINs a N tablas.

**Índices:**

- `idx_inventory_movements_warehouse_product_created_at`
- `idx_inventory_movements_product_created_at`

---

### 4.9 `solicitudes_recarga` + `detalle_solicitud_recarga`

`solicitudes_recarga` es la cabecera de la solicitud de reposición entre
bodegas (ver ADR-0003). Reemplaza al antiguo módulo `transfers`.

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id` | UUID PK | | |
| `codigo` | varchar(50) | UNIQUE | |
| `id_bodega_origen` | UUID FK | RESTRICT | debe ser auxiliar |
| `id_bodega_destino` | UUID FK | RESTRICT | debe ser principal |
| `estado` | enum | CHECK vía `SolicitudEstado` | |
| `prioridad` | varchar(30) | nullable | |
| `notas`, `motivo_rechazo` | varchar(500) | nullable | |
| `created_at` | timestamptz | | |
| `approved_at`, `dispatched_at`, `received_at` | timestamptz | nullable | timestamps de transición |

**CHECK constraints del modelo:**

- `ck_solicitudes_origen_distinto_destino` (origen ≠ destino).

**Reglas que viven en el service (no en CHECK):**

- REG-001/002/003 (ADR-0002): origen = auxiliar, destino = principal,
  `mecanico_box` no participa. SQL portable no permite subqueries en
  CHECK, por eso se validan en `SolicitudService._validate_direction`.

`detalle_solicitud_recarga`:

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id_solicitud` | UUID FK → `solicitudes_recarga(id)` | CASCADE | parte de PK |
| `id_producto` | UUID FK → `products(id)` | RESTRICT | parte de PK |
| `cantidad_solicitada` | numeric(14,2) | `> 0` | CHECK |
| `cantidad_despachada` | numeric(14,2) | `>= 0 AND <= cantidad_solicitada` | CHECK |
| `cantidad_recibida` | numeric(14,2) | `>= 0 AND <= cantidad_despachada` | CHECK |
| `barcode_validado` | varchar(100) | nullable | para auditoría de recepción |
| `notas` | varchar(500) | nullable | |

**3FN:** la cabecera tiene los atributos de la transición (estado,
timestamps); el detalle tiene las líneas. Sin atributos derivados.

**Estados** (enum `SolicitudEstado`):

- `pending` → `approved` | `rejected`
- `approved` → `in_transit` | `cancelled`
- `in_transit` → `partially_received` | `received`
- `partially_received` → `received` | `cancelled`

(terminales: `received`, `rejected`, `cancelled`)

---

### 4.10 `transfers` (DEPRECADO — solo lectura)

Modelo preservado por compatibilidad histórica (commit `6ff1d31`). El
router expone solo `GET`; cualquier `POST/PATCH/DELETE` retorna 410.

Estructura física intacta en BD:

- `id`, `code` (UNIQUE)
- `from_warehouse_id`, `to_warehouse_id`, `product_id` (FKs)
- `quantity`, `received_quantity`
- `status` (CHECK legacy)
- `dispatch_notes`, `receive_notes`, `incident_type`, `incident_notes`
- `created_at`, `approved_at`, `dispatched_at`, `received_at`

No se borra la tabla porque hay datos históricos que pueden consultarse.
Las inserciones nuevas van a `solicitudes_recarga`.

---

### 4.11 `ordenes_compra` + `detalle_orden_compra`

`ordenes_compra` (cabecera):

| Atributo | Tipo | Restricciones | Notas |
|---|---|---|---|
| `id` | UUID PK | | |
| `codigo` | varchar(50) | UNIQUE | |
| `id_bodega_principal` | UUID FK | RESTRICT | |
| `id_supervisor` | UUID FK → `supervisores(id)` | RESTRICT | aprobador |
| `proveedor_nombre` | varchar(200) | NOT NULL | snapshot al crear |
| `proveedor_contacto` | varchar(200) | nullable | |
| `estado` | enum `OrdenCompraEstado` | default `BORRADOR` | |
| `total_estimado` | numeric(14,2) | `>= 0` | CHECK |
| `notas`, `motivo_rechazo` | text/varchar(500) | nullable | |
| `email_token_jti` | varchar(64) | nullable | jti del JWT de aprobación |
| `email_enviado_at`, `aprobado_at`, `comprado_at` | timestamptz | nullable | |
| `created_at`, `updated_at` | timestamptz | | |

**Estados** (`OrdenCompraEstado`):

- `borrador` → `enviado_a_supervisor`
- `enviado_a_supervisor` → `aprobado` | `rechazado`
- `aprobado` → `comprado`

`detalle_orden_compra`:

| Atributo | Tipo | Restricciones |
|---|---|---|
| `id_orden_compra` | UUID FK CASCADE | parte de PK |
| `id_producto` | UUID FK RESTRICT | parte de PK |
| `cantidad_pedida` | numeric(14,2) | `> 0` CHECK |
| `costo_unitario_pactado` | numeric(14,2) | `>= 0` CHECK |

**3FN:** la separación cabecera/detalle cumple 3FN. Los totales
agregados (`total_estimado`) son **desnormalización controlada** —
se recalculan server-side en cada `PUT` y persisten para reporting.

---

### 4.12 `proveedores`

| Atributo | Tipo | Restricciones |
|---|---|---|
| `id` | UUID PK (TEXT en SQLite) | |
| `nombre` | TEXT | UNIQUE, NOT BLANK |
| `rut` | TEXT | UNIQUE nullable (cuando se conoce) |
| `email`, `telefono`, `direccion`, `contacto_nombre` | TEXT | nullable |
| `lead_time_dias` | int | default 7, `>= 0` (CHECK en service) |
| `activo` | int (bool) | default 1 |
| `created_at`, `updated_at` | TEXT | |

**3FN:** cumple. No hay atributos derivados.

**Nota:** la unicidad de `rut` es nullable: proveedores internacionales
pueden no tener RUT chileno.

---

### 4.13 `supervisores`

| Atributo | Tipo | Restricciones |
|---|---|---|
| `id` | UUID PK | |
| `email` | varchar(200) | UNIQUE |
| `nombre` | varchar(200) | NOT NULL |
| `cargo` | varchar(100) | nullable |
| `activo` | bool | default true |
| `created_at`, `updated_at` | timestamptz | |

**3FN:** cumple. A diferencia de `users`, los supervisores no tienen
contraseña (autenticación por token de email).

---

### 4.14 `users`, `user_sessions`

`users`:

| Atributo | Tipo | Restricciones |
|---|---|---|
| `id` | UUID PK | |
| `username` | varchar(60) | UNIQUE, NOT BLANK |
| `full_name` | varchar(150) | NOT BLANK |
| `role` | varchar(40) | CHECK ∈ `{admin, supervisor, origin_operator, destination_operator}` |
| `password_hash` | text | NOT NULL |
| `is_active` | bool | default true |
| `created_at` | timestamptz | |

`user_sessions` (sesiones persistentes para auditoría/revocación):

| Atributo | Tipo | Restricciones |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → `users(id)` | |
| `token` | text | UNIQUE |
| `expires_at` | timestamptz | |
| `created_at` | timestamptz | |

**3FN:** la tabla `user_sessions` está en 3FN; el token es la clave de
negocio (con `id` surrogate por compatibilidad).

**Nota de seguridad:** los JWT se validan por firma criptográfica;
`user_sessions` se usa para revocación y para alinear expiración
con `JWT_EXPIRES_MIN`.

---

### 4.15 `audit_logs`

| Atributo | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → `users(id)` | nullable (login fallido) |
| `action` | varchar(80) | `auth.login`, `warehouse.create`, etc. |
| `entity_type` | varchar(80) | `auth`, `warehouse`, `product` |
| `entity_id` | varchar(80) | nullable, UUID o code |
| `detail` | text | JSON con payload libre |
| `created_at` | timestamptz | |

**3FN:** bitácora append-only. No tiene UPDATE/DELETE expuesto.
`user_id` es nullable porque eventos anónimos (login fallido) deben
quedar registrados.

**Índices:**

- `idx_audit_logs_created_at` (búsqueda por fecha)
- (recomendado en fase 2) `idx_audit_logs_user_created (user_id, created_at)`
- (recomendado) `idx_audit_logs_entity (entity_type, entity_id)`

---

### 4.16 `notificaciones` (in-app)

| Atributo | Tipo | Notas |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK → `users(id)` | ON DELETE CASCADE |
| `tipo` | varchar(80) | `solicitud_aprobada`, `oc_recibida`, etc. |
| `titulo` | varchar(200) | NOT NULL |
| `mensaje` | text | nullable |
| `payload` | text (JSON) | datos adicionales para la UI |
| `leida` | int (bool) | default 0 |
| `created_at` | timestamptz | |
| `read_at` | timestamptz | nullable |

**Índices:**

- `idx_notificaciones_user_leida (user_id, leida, created_at DESC)`
- `idx_notificaciones_tipo (tipo)`

**3FN:** cumple. `payload` es JSON libre (desnormalización controlada
para evitar JOINs en UI).

---

### 4.17 `email_outbox`

| Atributo | Tipo | Restricciones |
|---|---|---|
| `id` | UUID PK (TEXT en SQLite) | |
| `to_email` | varchar(255) | NOT NULL |
| `subject` | varchar(500) | NOT NULL |
| `body_html` | text | NOT NULL |
| `template_name` | varchar(100) | nullable |
| `template_context` | text (JSON) | nullable |
| `status` | varchar(20) | **CHECK ∈ {pending, sent, failed, dead}** |
| `attempts` | int | `>= 0` CHECK |
| `last_error` | text | nullable |
| `sent_at` | timestamptz | nullable |
| `created_at` | timestamptz | default `now()` |

**3FN:** cumple. El CHECK de `status` (BUG-001) fue agregado en la
migración `0009_email_outbox_status_check.sql` (ver también
`docs/informe_integracion_fase5.md`).

**Índices:**

- `ix_email_outbox_status (status, created_at)` — soporta el worker Arq
  que toma batches `WHERE status = 'pending'`.

---

## 5. Resumen de claves foráneas

| Tabla hija | Columna | Tabla padre | ON DELETE |
|---|---|---|---|
| `products.id_categoria` | | `categories.id` | SET NULL |
| `detalles_neumaticos.producto_id` | | `products.id` | CASCADE |
| `ubicaciones_estanteria.id_bodega` | | `warehouses.id` | CASCADE |
| `inventario_stock_real.id_producto` | | `products.id` | CASCADE |
| `inventario_stock_real.id_ubicacion` | | `ubicaciones_estanteria.id` | CASCADE |
| `stock_levels.warehouse_id` | | `warehouses.id` | (default RESTRICT) |
| `stock_levels.product_id` | | `products.id` | (default RESTRICT) |
| `inventory_movements.warehouse_id` | | `warehouses.id` | (default RESTRICT) |
| `inventory_movements.product_id` | | `products.id` | (default RESTRICT) |
| `solicitudes_recarga.id_bodega_origen` | | `warehouses.id` | RESTRICT |
| `solicitudes_recarga.id_bodega_destino` | | `warehouses.id` | RESTRICT |
| `detalle_solicitud_recarga.id_solicitud` | | `solicitudes_recarga.id` | CASCADE |
| `detalle_solicitud_recarga.id_producto` | | `products.id` | RESTRICT |
| `ordenes_compra.id_bodega_principal` | | `warehouses.id` | RESTRICT |
| `ordenes_compra.id_supervisor` | | `supervisores.id` | RESTRICT |
| `detalle_orden_compra.id_orden_compra` | | `ordenes_compra.id` | CASCADE |
| `detalle_orden_compra.id_producto` | | `products.id` | RESTRICT |
| `notificaciones.user_id` | | `users.id` | CASCADE |
| `audit_logs.user_id` | | `users.id` | (default RESTRICT) |
| `user_sessions.user_id` | | `users.id` | (default RESTRICT) |

---

## 6. Desnormalizaciones controladas (justificación)

| Tabla | Atributo desnormalizado | Razón | Mitigación |
|---|---|---|---|
| `categories` | `uq_categories_nombre_normalized` (índice funcional) | Unicidad case-insensitive sin app-layer check | El índice se mantiene por la BD; escritura via servicio |
| `inventory_movements` | `reference_type` + `reference_id` (polimórfico) | Una sola tabla kardex para N fuentes | Validación en service de tipos aceptados |
| `ordenes_compra` | `proveedor_nombre` (denormalizado del catálogo) | Snapshot inmutable al momento de emitir | Si el proveedor cambia, la OC no se altera |
| `ordenes_compra` | `total_estimado` (agregado del detalle) | Reportes sin JOIN + recálculo server-side | Recalculado en cada `PUT` |
| `notificaciones` | `payload` (JSON libre) | UI sin JOINs adicionales | Validación de keys en service |
| `email_outbox` | `template_context` (JSON) | Reconstruir el email sin reconsultar la OC original | Si el template cambia, se respeta el snapshot |

---

## 7. Índices por tabla — resumen

| Tabla | Índices |
|---|---|
| `warehouses` | `code` UNIQUE, `name` UNIQUE, `(warehouse_type, is_active)` |
| `products` | `sku` UNIQUE, `codigo_barras` UNIQUE, `(id_categoria)`, `(is_active)` |
| `categories` | `nombre` UNIQUE + `lower(btrim(nombre))` UNIQUE, `(parent_id)` |
| `detalles_neumaticos` | PK = `producto_id` |
| `ubicaciones_estanteria` | `(id_bodega, pasillo, estanteria, altura)` UNIQUE, `(id_bodega)`, `(id_bodega, is_active)` |
| `stock_levels` | `(warehouse_id, product_id)` UNIQUE, `(product_id)` |
| `inventario_stock_real` | PK `(id_producto, id_ubicacion)`, `(id_ubicacion)` |
| `inventory_movements` | `(warehouse_id, product_id, created_at desc)`, `(product_id, created_at desc)` |
| `solicitudes_recarga` | `codigo` UNIQUE, `(estado, created_at)` |
| `detalle_solicitud_recarga` | PK compuesta |
| `ordenes_compra` | `codigo` UNIQUE, `(estado, created_at)`, `(id_supervisor)`, `(id_bodega_principal)` |
| `detalle_orden_compra` | PK compuesta |
| `proveedores` | `nombre` UNIQUE, `rut` UNIQUE, `(activo)` |
| `supervisores` | `email` UNIQUE |
| `users` | `username` UNIQUE, `role` filter (recomendado `(role, is_active)`) |
| `user_sessions` | `token` UNIQUE |
| `audit_logs` | `(created_at desc)` |
| `notificaciones` | `(user_id, leida, created_at desc)`, `(tipo)` |
| `email_outbox` | `(status, created_at)` |

---

## 8. Comparación con el modelo propuesto (sección 9 de la propuesta)

| Propuesta | Implementación | Notas |
|---|---|---|
| `empresas` | (no aplica) | Single-tenant por ahora |
| `usuarios` | `users` | con `user_sessions` |
| `roles`, `permisos`, `usuario_roles`, `usuario_bodegas` | `users.role` enum (sin permisos granulares) | RBAC simplificado |
| `bodegas` | `warehouses` | ✅ |
| `ubicaciones_bodega` | `ubicaciones_estanteria` | solo nivel pasillo/estantería/altura |
| `slots_bodega`, `sugerencias_slotting` | — | **fase 2** |
| `categorias_producto` | `categories` | ✅ |
| `unidades_medida` | `products.unit` (varchar) | simplificado a un campo libre |
| `productos` | `products` | ✅ |
| `producto_proveedores` | — | proveedor se snapshot en OC |
| `proveedores` | `proveedores` | ✅ |
| `stock` | `stock_levels` (Nivel 1) | ✅ |
| `reservas_stock` | — | **fase 2**, hoy se confía en atomicidad TX |
| `movimientos_inventario` | `inventory_movements` | ✅ |
| `kardex_inventario` | (mismo que `movimientos`) | simplificado: una sola tabla |
| `ajustes_inventario` | `inventory_movements` con `movement_type = adjustment_*` | ✅ |
| `lotes`, `series` | — | **fase 2** |
| `reglas_reabastecimiento` | parcial: `stock_levels.min_quantity` + `max_quantity` | la generación automática se delega al `ReplenishmentService` en memoria |
| `solicitudes_reposicion` + `detalle_solicitud_reposicion` | `solicitudes_recarga` + `detalle_solicitud_recarga` | ✅ (N productos) |
| `transferencias` + `detalle_transferencia` | `transfers` (DEPRECADO) | se conserva solo histórico |
| `ordenes_compra` + `detalle_orden_compra` | `ordenes_compra` + `detalle_orden_compra` | ✅ |
| `recepciones_compra` | (mismo que OC, con `cantidad_recibida`) | simplificado |
| `canales_chat`, `mensajes_chat`, `adjuntos` | — | **fase 2** |
| `notificaciones` | `notificaciones` | ✅ (in-app) |
| `auditoria_eventos` | `audit_logs` | ✅ |
| `outbox_eventos` | `email_outbox` (parcial) | falta extender a WebSockets |
| `ventas_producto_diaria`, `ranking_productos_periodo`, `clasificacion_abc_producto`, `sugerencias_slotting` | — | **fase 2** |

**Resumen de cobertura del modelo propuesto:** 16/24 tablas implementadas;
8 diferidas a fase 2. Lo que está implementado cubre el ciclo transaccional
básico end-to-end (auth → catálogo → stock → solicitud → OC → auditoría).

---

## 9. Decisiones de diseño explícitas

1. **UUIDs en todas las PKs.** Sobreviven a fusiones de BD, permiten
   generar IDs offline, y son la convención del proyecto desde el MVP.
2. **Snapshot en OC.** El nombre y contacto del proveedor se copian a la
   cabecera de la OC. Si el proveedor se renombra o cambia contacto, las
   OC históricas siguen mostrando el valor al momento de emisión.
3. **CHECK constraints portables.** Todo lo que se puede expresar en
   CHECK estándar vive en CHECK; lo que requiere leer otra fila
   (subqueries) vive en service. Esto preserva la capacidad de cambiar
   de SQLite a Postgres sin reescribir reglas de dominio.
4. **No hay `DELETE` físico de catálogo.** `is_active` es la convención
   para warehouses, products, categories, proveedores, supervisores.
5. **`detalle_*` siempre con PK compuesta.** Refuerza la atomicidad: no
   se puede tener un detalle huérfano y la consulta de cabecera es un
   solo JOIN.
6. **Estados como ENUM, no strings libres.** Postgres los implementa con
   `CREATE TYPE`; SQLite los simula con `VARCHAR(30)` + `CHECK` en el
   service. Ambos lados coinciden por convención de código.

---

## 10. Pendientes y riesgos

1. **Índices faltantes en `audit_logs`.** Las consultas por `user_id` y
   `entity_type` son full-scan a partir de cierto volumen. Recomendado
   en sprint de performance.
2. **`reservas_stock`** no modelado. Hoy se cubre con `SELECT FOR UPDATE`
   en transacciones de solicitud. Documentar formalmente en fase 2.
3. **Falta `kardex_inventario` separado de `movimientos_inventario`** como
   proponía la sección 9 de la propuesta. En este modelo una sola tabla
   cumple ambos roles. Si en el futuro se requiere doble entrada
   contable, se debe partir.
4. **Triggers de auditoría de BD.** Toda la auditoría actual es a nivel
   aplicación (`audit_logs`). Si se necesita bitácora de cambios de
   esquema o deletes directos, considerar triggers.
5. **Particionado de `inventory_movements` por fecha.** A partir de ~10M
   de filas, los índices compuestos empiezan a sufrir. Recomiendo
   partición por rango mensual en fase de escala.
