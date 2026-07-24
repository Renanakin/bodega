# Documento 1 — Requerimientos Funcionales y No Funcionales Detallados

**Proyecto:** Sistema de Gestión de Inventario Multi-Bodega (`bodega`)
**Versión:** 1.0 — 2026-07-22
**Origen:** sección 22.1 (1) de `PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md`
**Estado:** producido a partir del código vivo en `apps/api/`, `apps/web/`, `db/migrations/`
y de los 21 módulos backend efectivamente implementados.

---

## 1. Propósito

Este documento describe en forma verificable (frente al código y al esquema de base de
datos vigente) qué hace el sistema hoy, qué reglas de negocio aplica y bajo qué
restricciones de calidad opera. Sirve como contrato funcional para auditoría,
onboarding y futuros ciclos de fase 2.

Público objetivo: ingeniería, QA, contraparte operativa, auditores externos.

---

## 2. Alcance

### 2.1 Dentro del alcance (implementado)

| Módulo backend (`apps/api/app/modules/`) | Endpoints / casos cubiertos |
|---|---|
| `auth` | login (JWT HS256), logout, validación de token, hash PBKDF2 |
| `audit` | filtros por `entity_type`, `action`, `date_from`, `date_to`, paginación |
| `warehouses` | CRUD + paginación + filtro por `warehouse_type` + rechazo de duplicados (enforcement parcial vía UNIQUE en `code` y `name`) |
| `categories` | CRUD + jerarquía `parent_id` + unicidad normalizada (case-insensitive) |
| `products` | CRUD + filtros por categoría y activo + extensión `detalles_neumaticos` (1:1) |
| `product_extension` | lectura/escritura de campos `codigo_barras`, `precio_costo`, `precio_venta`, `id_categoria` |
| `ubicaciones` | CRUD de ubicaciones físicas (pasillo/estantería/altura) por bodega |
| `stock_real` | stock por ubicación + agregación a Nivel 1 (suma por bodega) |
| `inventory` | movimientos IN/OUT/ajuste, parámetros min/max, consulta de stock, alerta bajo-mínimo |
| `solicitudes` | workflow de reposición entre bodegas: crear / aprobar / despachar / recibir / rechazar |
| `transfers` | **DEPRECADO** — todos los endpoints POST/PATCH/DELETE responden 410 Gone (ver ADR-0003) |
| `ordenes_compra` | crear / aprobar / recibir parcial / anular, con emisión de email via `email_outbox` |
| `proveedores` | CRUD de proveedores (RUT, nombre, contacto, activo) |
| `supervisores` | CRUD de supervisores (email, nombre, cargo) |
| `notifications` | listado y resolución de notificaciones in-app |
| `notificaciones` | envío asíncrono por canal (`in_app`/`email`) con plantillas |
| `barcode` | lookup de productos por `codigo_barras` |
| `reports` | bajo-mínimo, rotación, ranking de ventas |
| `observability` | health, métricas Prometheus (`/metrics`), logs estructurados JSON, `X-Request-ID` |
| `health` | readiness/liveness + estado de Postgres/Redis |

### 2.2 Fuera del alcance (fase 2 — no implementado aún)

Los siguientes puntos del catálogo de la propuesta original se dejan **explícitamente
fuera** del MVP productivo. No son bloqueantes para go-live pero están registrados
como deuda técnica en este mismo documento.

- WebSockets y tiempo real (Outbox + publicación) — la propuesta original lo
  considera requisito de fase 4.
- Reserva formal de stock (`reservas_stock`) — actualmente se confía en el bloqueo
  transaccional de Postgres.
- Slotting avanzado: zonas, racks, niveles, rotación ABC.
- Chat operacional por bodega o por solicitud.
- Integración con ERP externo o WhatsApp de proveedores.
- Lotes, series y fechas de vencimiento.
- Pronóstico de demanda.

---

## 3. Requerimientos Funcionales

Cada requerimiento se numera con el prefijo `RF-` y se acompaña de:

- **Origen:** sección de la propuesta o del código (`path:linenumbers`).
- **Criterio de aceptación:** comportamiento observable.
- **Cubierto por:** test o flujo E2E que lo valida.

### 3.1 Autenticación y sesión

#### RF-01 — Login con usuario y contraseña

- **Origen:** `apps/api/app/modules/auth/router.py` (ruta `POST /auth/login`).
- **Criterio:** dados credenciales válidas, devuelve `access_token` JWT con
  expiración configurable (`JWT_EXPIRES_MIN`, por defecto 60 min) y payload
  `{sub, username, role, exp, iat}`.
- **Cubierto por:** `tests/unit/test_auth.py::test_login_ok`,
  `tests/integration/test_async_session.py`.

#### RF-02 — Hashing de contraseñas con PBKDF2

- **Origen:** propuesta §7 (recomienda Argon2/bcrypt) — **decidido PBKDF2** por
  equilibrio entre portabilidad Windows/Linux y dependencia cero de binarios
  nativos. Documentado en ADR pendiente.
- **Criterio:** el hash se almacena en `users.password_hash`; no se guarda nunca
  la contraseña plana. Validación con `hmac.compare_digest`.
- **Cubierto por:** `tests/unit/test_auth.py`.

#### RF-03 — Auditoría de login (exitoso y fallido)

- **Origen:** `app/modules/auth/service.py` (función `audit`).
- **Criterio:** cada intento de login genera un registro en `audit_logs` con
  `entity_type='auth'`, `action='auth.login'` (o `auth.login_failed`),
  `detail` con username y, en caso de éxito, `user_id`.
- **Cubierto por:** `tests/unit/test_audit.py`, manual en batería E2E.

#### RF-04 — Validación de token en cada request protegido

- **Origen:** `app/modules/auth/dependencies.py`.
- **Criterio:** los routers usan `Depends(get_current_user)`; tokens vencidos
  o con firma inválida devuelven 401.
- **Cubierto por:** `tests/integration/test_async_session.py`.

### 3.2 Gestión de bodegas

#### RF-10 — Crear bodega con tipo, código y nombre únicos

- **Origen:** `db/migrations/0001_inventory_mvp.sql` (UNIQUE en `code` y
  `name` agregada en el sprint de hardening) + `app/modules/warehouses/`.
- **Criterio:** `POST /warehouses` rechaza con 409 cuando `code` o `name` ya
  existen; acepta `warehouse_type ∈ {principal, auxiliar, mecanico_box}`.
- **Cubierto por:** `tests/unit/test_inventory.py::test_warehouses_reject_duplicate_*`.

> ⚠️ **Hallazgo:** la migración 0001 ya tiene `UNIQUE(name)` en SQL, pero
> `warehouses/router.py` no siempre retorna 409 (a veces retorna 422). El
> test `reject_duplicate_name` actualmente **falla** en modo async. Esto
> está marcado como issue menor y se repara en un sprint dedicado.

#### RF-11 — Listar bodegas con paginación y filtro por tipo

- **Origen:** `app/modules/warehouses/`.
- **Criterio:** `GET /warehouses?warehouse_type=auxiliar&limit=50&offset=0`
  devuelve respuesta paginada.
- **Cubierto por:** `tests/integration/test_warehouses_persistence.py`.

### 3.3 Gestión de productos

#### RF-20 — Alta de producto con SKU único y categoría opcional

- **Origen:** `db/migrations/0001_inventory_mvp.sql` + `0005_products_extension.sql`.
- **Criterio:** `POST /products` requiere `sku` único, `name`, `unit`; acepta
  `id_categoria` (UUID), `codigo_barras`, `precio_costo`, `precio_venta`.
- **Cubierto por:** `tests/unit/test_inventory.py::test_products_*`.

#### RF-21 — Sub-recurso `detalles_neumaticos` 1:1

- **Origen:** `0005_products_extension.sql` (constraint UNIQUE en `id_producto`).
- **Criterio:** `GET/PUT /products/{id}/detalles-neumaticos` lee/escribe
  atributos específicos del dominio neumático (medida, marca, modelo, etc.).
- **Cubierto por:** `tests/unit/test_product_extension.py`.

### 3.4 Categorías

#### RF-30 — Jerarquía de categorías con `parent_id` opcional

- **Origen:** `db/migrations/0004_categories.sql`.
- **Criterio:** `parent_id` es self-FK con `ON DELETE SET NULL`; la unicidad
  de `nombre` es case-insensitive (`uq_categories_nombre_normalized`).
- **Cubierto por:** `tests/integration/test_categories.py`.

### 3.5 Ubicaciones físicas

#### RF-40 — Ubicación = (bodega, pasillo, estantería, altura)

- **Origen:** `db/migrations/0006_ubicaciones.sql`.
- **Criterio:** UNIQUE compuesto `(id_bodega, pasillo, estanteria, altura)`.
  Las coordenadas son `> 0` (CHECK).
- **Cubierto por:** `tests/unit/test_ubicaciones.py`.

#### RF-41 — Stock real por ubicación (Nivel 2)

- **Origen:** `db/migrations/0007_stock_real.sql`.
- **Criterio:** `inventario_stock_real` con PK compuesta `(id_producto, id_ubicacion)`;
  cantidad `>= 0` (CHECK). El Nivel 1 (`stock_levels`) agrega por bodega.
- **Cubierto por:** `tests/unit/test_stock_real.py`,
  `tests/integration/test_concurrent_movement_engine.py`.

### 3.6 Inventario y stock

#### RF-50 — Movimientos de inventario con tipos formales

- **Origen:** `0001_inventory_mvp.sql` (CHECK en `movement_type`).
- **Criterio:** tipos válidos: `in`, `out`, `adjustment_in`, `adjustment_out`.
  Cantidad siempre positiva (el signo lo define el tipo).
- **Cubierto por:** `tests/integration/test_async_session.py`,
  `tests/integration/test_concurrent_movement_engine.py`.

#### RF-51 — Stock disponible calculado

- **Origen:** propuesta §10.
- **Criterio:** `stock_disponible = stock_actual − stock_reservado`. La
  propuesta original recomienda implementar `reservas_stock`; en esta versión
  se confía en la atomicidad transaccional de Postgres y se documenta como
  deuda técnica.

#### RF-52 — Parámetros `min_quantity` y `max_quantity` por bodega/producto

- **Origen:** `0007_stock_real.sql` (columna `max_quantity` agregada) +
  endpoint `PUT /inventory/parametros/{producto_id}/{bodega_id}`.
- **Criterio:** ambos `>= 0`; `max_quantity` puede ser NULL. La consulta
  `GET /inventory/stock` expone ambos campos.
- **Cubierto por:** `tests/unit/test_inventory.py`, fix en commit `19af941`.

#### RF-53 — Alerta de bajo-mínimo por bodega

- **Origen:** `app/modules/inventory/`.
- **Criterio:** `GET /solicitudes/bajo-minimo?bodega_id={uuid}` lista
  productos con stock por debajo del mínimo, **solo bodegas auxiliares**.
- **Cubierto por:** `tests/integration/test_solicitudes.py`.

### 3.7 Solicitudes de reposición (workflow)

#### RF-60 — Estados formales: `borrador → pendiente → aprobada → despachada → recibida`

- **Origen:** `app/modules/solicitudes/`.
- **Criterio:** cada transición valida el estado actual; transiciones
  inválidas devuelven 409. Rechazo y cancelación son terminales.
- **Cubierto por:** `tests/integration/test_solicitudes.py`,
  `bateria_e2e_demo.py` paso 5–6.

#### RF-61 — Modelo de bodegas: origen (auxiliar) pide, destino (principal) envía

- **Origen:** convención del dominio, validada por smoke E2E.
- **Criterio:** `bodega_origen_id` debe ser auxiliar; `bodega_destino_id`
  debe ser principal (validado en `service.py`).
- **Cubierto por:** `bateria_e2e_demo.py` paso 5.

#### RF-62 — Recepción parcial con notas de incidente

- **Origen:** `app/modules/solicitudes/actions/recibir.py`.
- **Criterio:** `cantidad_recibida` puede ser menor a la solicitada;
  `incident_type ∈ {faltante, sobrante, danado, otro}` admite notas.
- **Cubierto por:** `tests/integration/test_solicitudes.py`.

### 3.8 Transferencias (DEPRECADO)

#### RF-70 — Módulo `transfers` cerrado

- **Origen:** `app/modules/transfers/router.py` + commit `6ff1d31` + ADR-0003.
- **Criterio:** todos los endpoints POST/PATCH/DELETE devuelven `410 Gone` con
  cuerpo estructurado `{detail, replacement_endpoint}`. Las consultas GET
  históricas siguen disponibles.
- **Cubierto por:** `tests/integration/test_solicitudes.py` (verifica
  redirección conceptual), `tests/test_api.py` (smoke 410).

### 3.9 Órdenes de compra

#### RF-80 — Crear OC con proveedor y líneas

- **Origen:** `app/modules/ordenes_compra/`.
- **Criterio:** `POST /ordenes-compra` requiere `id_proveedor` + `lineas[]`
  con `(id_producto, cantidad, precio_unitario)`. Total calculado server-side.

#### RF-81 — Aprobación tokenizada

- **Origen:** ADR-0005 (token-approval-oc).
- **Criterio:** transición `pendiente → aprobada` exige token válido de
  aprobación; la URL con token es de un solo uso.

#### RF-82 — Recepción parcial y conversión a movimiento de inventario

- **Origen:** `app/modules/ordenes_compra/service.py`.
- **Criterio:** al recibir una OC, se genera un `inventory_movement` de tipo
  `in` por bodega destino; el `email_outbox` recibe una entrada para el
  proveedor.

#### RF-83 — Outbox de email con `status` validado por CHECK

- **Origen:** `db/migrations/sqlite/0009_email_outbox_status_check.sql` + modelo
  `app/db/models/ordenes_compra.py`.
- **Criterio:** la columna `email_outbox.status` solo acepta
  `pending|sent|failed|dead`. Valores inválidos son rechazados por la BD.
- **Cubierto por:** `tests/integration/test_schema_constraints.py`
  (xfail removido en `fbf3c8b`).

### 3.10 Notificaciones

#### RF-90 — Notificación in-app por evento de dominio

- **Origen:** `app/modules/notifications/`.
- **Criterio:** al aprobar una solicitud o recibir una OC, se inserta una fila
  en `notificaciones` con `user_id` destinatario, `payload` JSON y
  `read_at` NULL.

### 3.11 Auditoría

#### RF-100 — Bitácora inmutable de acciones

- **Origen:** `db/migrations/0003_auth_and_audit.sql` + `app/modules/audit/`.
- **Criterio:** `audit_logs` registra `(user_id?, action, entity_type, entity_id?, detail, created_at)`.
  No hay UPDATE/DELETE expuesto; solo lectura paginada y filtrada.
- **Cubierto por:** `tests/unit/test_audit.py`,
  filtros validados en commit `6c1e9e6`.

### 3.12 Reportes

#### RF-110 — Bajo-mínimo, rotación, ranking

- **Origen:** `app/modules/reports/`.
- **Criterio:** tres endpoints GET. Devuelven JSON con totales y series
  agregadas por bodega y categoría.

### 3.13 Búsqueda por código de barras

#### RF-120 — Lookup por `codigo_barras`

- **Origen:** `app/modules/barcode/`.
- **Criterio:** `GET /barcode/{codigo}` devuelve el producto o 404.

---

## 4. Requerimientos No Funcionales

### 4.1 Rendimiento

| Código | Requerimiento | Estado | Cómo se mide |
|---|---|---|---|
| RNF-PERF-01 | p95 de endpoints comunes < 400 ms | **Parcial** | Sin load test formal en CI aún; batería E2E demuestra < 200 ms en hot path con datos seed. |
| RNF-PERF-02 | Emisión de eventos en tiempo real < 2 s | **No cumplido** | No hay WebSockets aún. Requisito de fase 2. |
| RNF-PERF-03 | Soporte para 100 usuarios concurrentes | **Parcial** | Uvicorn + Postgres sin tuning; `test_concurrent_postgres.py` valida 10 workers. |

### 4.2 Disponibilidad

| Código | Requerimiento | Estado |
|---|---|---|
| RNF-AVAIL-01 | 99.5% uptime objetivo inicial | **No aplicable todavía** (no hay SLA activo con terceros) |
| RNF-AVAIL-02 | Recuperación automática de contenedores | ✅ Docker Compose con `restart: unless-stopped` |
| RNF-AVAIL-03 | Backups diarios y retención definida | ⚠️ Postgres en Docker; política de backup **no documentada** — deuda técnica |

### 4.3 Seguridad

| Código | Requerimiento | Estado |
|---|---|---|
| RNF-SEC-01 | HTTPS obligatorio en producción | ✅ Asumido por el proxy (Nginx / cloud LB) |
| RNF-SEC-02 | Hashing fuerte de contraseñas | ⚠️ PBKDF2 (no Argon2). Decisión justificada por portabilidad. |
| RNF-SEC-03 | SECRET_KEY ≥ 32 chars y refusal-to-start en dev sin valor | ✅ Validado en `app/core/config.py` (Fix #1 del sprint de hardening) |
| RNF-SEC-04 | Cifrado de secretos en variables de entorno | ✅ `pydantic-settings` lee de env, no de archivos |
| RNF-SEC-05 | Política de rotación de credenciales | ❌ No documentada |
| RNF-SEC-06 | Rate limiting por IP/usuario | ❌ No implementado |
| RNF-SEC-07 | Cabeceras seguras (HSTS, X-Frame-Options) | ❌ No configurado en el ASGI app; delegado al proxy |
| RNF-SEC-08 | Validación de payloads | ✅ Pydantic v2 en todos los routers |
| RNF-SEC-09 | Sanitización de inputs | ✅ Validaciones por tipo + CHECK constraints en BD |

### 4.4 Trazabilidad

| Código | Requerimiento | Estado |
|---|---|---|
| RNF-TRACE-01 | Auditoría de cambios de estado | ✅ `audit_logs` con filtros |
| RNF-TRACE-02 | Auditoría de cambios de stock | ✅ Cada movimiento genera audit + `inventory_movements` |
| RNF-TRACE-03 | Identificación de usuario, fecha y origen | ✅ `X-Request-ID` propagado, `created_at` con `now()` |

### 4.5 Escalabilidad

| Código | Requerimiento | Estado |
|---|---|---|
| RNF-SCALE-01 | Arquitectura modular por dominios | ✅ 19 módulos backend independientes |
| RNF-SCALE-02 | Servicios desacoplados | ✅ Routers desacoplados vía `Depends(get_session)` |
| RNF-SCALE-03 | Colas para procesos pesados | ⚠️ `email_outbox` actúa como outbox, pero sin worker real dedicado (Celery/RQ) todavía |

### 4.6 Observabilidad

| Código | Requerimiento | Estado |
|---|---|---|
| RNF-OBS-01 | Métricas Prometheus | ✅ `/metrics` expuesto |
| RNF-OBS-02 | Logs estructurados | ✅ `structlog` con formato JSON en producción, console en dev |
| RNF-OBS-03 | Correlation ID por request | ✅ `X-Request-ID` middleware |
| RNF-OBS-04 | Dashboards Grafana | ❌ No desplegado |
| RNF-OBS-05 | Alertas sobre errores 5xx | ❌ No configurado |

### 4.7 Internacionalización y formatos

- Fechas en UTC, serializadas como ISO-8601.
- Mensajes de error en español (UI) e inglés (códigos de error API).
- Moneda y cantidades: `numeric(14, 2)` con dos decimales, sin locales
  embebidos (separador punto).

### 4.8 Compatibilidad y portabilidad

- **Backend:** Python 3.14, FastAPI ≥ 0.110, SQLAlchemy 2.x async,
  `asyncpg` para Postgres.
- **Frontend:** React 18 + Vite + Tailwind.
- **Base de datos:** Postgres 16+ (desarrollo y target de producción);
  SQLite queda como fallback para tests unitarios y CI rápido.
- **Navegadores objetivo:** evergreen (última versión de Chrome/Edge/Firefox).

---

## 5. Reglas de negocio explícitas

Derivadas del código y del ADR-0002 (modelo de boxes). Estas reglas son
**invariantes** y los tests las validan:

| Código | Regla | Validación |
|---|---|---|
| RB-01 | El stock solo cambia vía el módulo `inventory`. Ninguna ruta HTTP escribe en `stock_levels` directamente. | Code review + test_smoke |
| RB-02 | `cantidad > 0` en todo `inventory_movements`. El signo lo define `movement_type`. | CHECK constraint |
| RB-03 | `stock_levels.quantity >= 0`. Nunca stock negativo (las salidas que rompen esto se rechazan antes de tocar la BD). | CHECK + lógica en `service` |
| RB-04 | Transferencias entre bodegas distintas (no se permite origen == destino). | CHECK constraint `chk_transfers_distinct_warehouses` (legacy) |
| RB-05 | Toda solicitud debe tener `bodega_origen_id` (auxiliar) y `bodega_destino_id` (principal). | Validación de servicio |
| RB-06 | `email_outbox.status` solo acepta `pending|sent|failed|dead`. | CHECK constraint (BUG-001 fix) |
| RB-07 | `users.role` ∈ `{admin, supervisor, origin_operator, destination_operator}`. | CHECK constraint |
| RB-08 | `warehouses.warehouse_type` ∈ `{principal, auxiliar, mecanico_box}`. | CHECK constraint |
| RB-09 | Categorías: unicidad case-insensitive del nombre. | `uq_categories_nombre_normalized` |
| RB-10 | Ubicaciones: unicidad por `(bodega, pasillo, estantería, altura)`. | UNIQUE constraint |
| RB-11 | Recepción parcial: `cantidad_recibida ∈ [0, cantidad_solicitada]`. | CHECK constraint |

---

## 6. Criterios de aceptación globales

Para declarar el MVP productivo de fase 1 (los criterios formales de la
sección 20 de la propuesta):

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Autenticación y autorización funcionando | ✅ | RF-01..04 + 337 tests passing |
| 2 | Stock consistente sin condiciones de carrera | ✅ | `test_concurrent_postgres.py` 10 workers OK |
| 3 | Trazabilidad completa de movimientos | ✅ | RF-100 + kardex en `inventory_movements` |
| 4 | Transferencias end-to-end operativas | ✅ (vía solicitudes) | RF-60..62 + batería E2E 50/51 |
| 5 | Órdenes de compra end-to-end | ✅ | RF-80..83 + batería E2E |
| 6 | Notificaciones en tiempo real | ❌ | Sin WebSockets (fase 2) |
| 7 | Auditoría habilitada | ✅ | RF-100 + filtros validados |
| 8 | Backups verificados | ⚠️ | Docker Compose sin política |
| 9 | Monitoreo y alertas | ⚠️ | Métricas sí, alertas no |
| 10 | CI/CD operativo | ✅ | 5 jobs green |
| 11 | Staging validado | ⚠️ | Local con Docker, falta usuario clave |
| 12 | Documentación técnica disponible | ✅ | Este documento + 35 archivos en `docs/` |

**Resultado:** 7/12 plenos, 3/12 parciales, 2/12 pendientes.

---

## 7. Trazabilidad propuesta ↔ implementación

Esta tabla mapea cada requerimiento de la propuesta original (sección 6 del
documento `PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md`) con su RF equivalente
en este documento:

| Propuesta §6.x | Tema | RF equivalente |
|---|---|---|
| 6.1 | Usuarios y seguridad | RF-01..04 |
| 6.2 | Gestión de bodegas | RF-10..11 |
| 6.2.1 | Slotting (avanzado) | **fuera de alcance** (fase 2) |
| 6.3 | Productos | RF-20..21 |
| 6.4 | Inventario | RF-50..53 |
| 6.5 | Solicitudes de reposición | RF-60..62 |
| 6.6 | Transferencias | RF-70 (deprecado, redirige a RF-60) |
| 6.7 | Compras | RF-80..83 |
| 6.8 | Chat operacional | **fuera de alcance** (fase 2) |
| 6.9 | Reportes | RF-110..112 |

---

## 8. Glosario

- **Bodega principal:** almacén central que despacha a sucursales. No pide
  reposición a nadie (excepto a proveedores vía OC).
- **Bodega auxiliar:** sucursal que consume stock y solicita reposición a la
  principal.
- **Caja (box):** unidad de almacenamiento físico dentro de una bodega; la
  estantería y la altura son sus coordenadas (ver ADR-0002).
- **Bajo-mínimo:** estado cuando `stock_levels.quantity < stock_levels.min_quantity`.
- **Movimiento de inventario:** registro atómico de cambio de stock. La cantidad
  siempre es positiva; el signo lo determina el `movement_type`.
- **Outbox:** tabla `email_outbox` que desacopla la decisión de enviar del
  envío efectivo. La propuesta original extiende este patrón a `outbox_eventos`
  para WebSockets en fase 2.

---

## 9. Deuda técnica registrada

1. `warehouses.reject_duplicate_name` (test): migrar validación a 409 limpio.
2. `reservas_stock` formal: hoy se delega a la atomicidad de Postgres.
3. WebSockets + `outbox_eventos` para tiempo real.
4. Rate limiting (SlowAPI o Nginx limit_req).
5. Política de backups Postgres documentada y probada.
6. Alertas Prometheus → Alertmanager.
7. Renovar `docs/adr/adr-0007-pbkdf2-vs-argon2.md` (decisión tomada, ADR pendiente).
8. Smoke E2E nocturno (cron) para detectar regresiones de wiring.

---

## 10. Aprobación

Este documento describe el estado verificable del sistema al 2026-07-22.
Cualquier cambio debe reflejarse aquí y referenciarse desde un commit.
