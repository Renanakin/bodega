---
title: "Roadmap ejecutable — Fases 3 a 10"
date: 2026-07-14
status: "Borrador listo para ejecutar"
predecesores: ["Fase 0", "Fase 1", "Fase 2 (completadas)"]
---

# Roadmap ejecutable — Fases 3 a 10

> Este documento es la **puerta de entrada** para retomar el trabajo de implementación. Las Fases 0, 1 y 2 ya están completas (ver `docs/fases/fase-1-postgres-real.md` y `docs/fases/fase-2-multibodega-fisica.md`). Las Fases 3 a 10 están **estructuradas con prompts optimizados** para que un subagente `coder` las ejecute de forma autónoma.

---

## Estado actual al cierre de Fase 2

### Lo que YA está construido (no rehacer)

**Backend (`apps/api/app/modules/`):**
- `warehouses`, `products`, `inventory`, `transfers`, `auth`, `audit`, `health`
- `categories` (Fase 2) ✅
- `ubicaciones` (Fase 2) ✅
- `stock_real` (Fase 2) ✅
- `product_extension` (Fase 2) ✅
- `solicitudes` (estructura) — refinar
- `ordenes_compra` (estructura) — refinar
- `supervisores` (estructura) — refinar
- `proveedores` (estructura) — refinar
- `notifications` (estructura) — refinar
- `observability` (estructura) — refinar
- `reports` (estructura) — refinar
- `inventory/movement_engine.py` (Fase 2) ✅

**Frontend (`apps/web/src/`):**
- 11 vistas legacy (CSS plano, **NO TOCAR** — ADR-0006)
- `BarcodeInput.jsx` (Fase 2) ✅
- `SearchSku.jsx` (Fase 2) ✅
- `MultibodegaGrid.jsx` (Fase 2) ✅
- `MultibodegaGridPage.jsx` (Fase 2) ✅
- Tailwind v3 configurado ✅

**Migraciones SQL (`db/migrations/`):**
- 0001 MVP, 0002 transfers, 0003 auth/audit
- 0004 categories, 0005 products extension, 0006 ubicaciones, 0007 stock_real

**ADRs (`docs/adr/`):**
- 0001 postgres, 0002 boxes, 0003 transfers, 0004 smtp/worker, 0005 token OC, 0006 tailwind

### Lo que FALTA

| Fase | Trabajo restante | Subagente | Skills recomendadas |
|---|---|---|---|
| **3** | SolicitudService + reemplazo de transfers + tests E2E | `coder` | `software-architecture`, `saga-orchestration`, `production-code-audit`, `e2e-testing-patterns` |
| **4** | ReplenishmentEvaluator (cron Arq) + UI SolicitudesAuxPage | `coder` | `workflow-orchestration-patterns`, `production-code-audit`, `testing-patterns` |
| **5** | RecepcionBandejaPage + flujo escaneo + endpoint receive | `coder` | `testing-patterns`, `e2e-testing-patterns` |
| **6** | Generador OC UI + Consolidador + dropdown supervisor | `coder` | `production-code-audit`, `tailwind-patterns` |
| **7** | EmailOutboxService + ArqWorker + plantilla HTML + Mailpit en compose | `coder` | `workflow-orchestration-patterns`, `production-code-audit`, `testing-patterns` |
| **8** | Resto vistas nuevas con Tailwind (8 vistas) | `coder` | `tailwind-design-system`, `product-design`, `ui-pattern` |
| **9** | /metrics Prometheus + structlog + healthcheck ampliado | `coder` | `production-code-audit`, `error-handling-patterns` |
| **10** | Hardening producción (vault, rate limit, backup, runbook) | `coder` | `cloudformation-best-practices`, `production-code-audit` |

**Estimación:** 5-7 semanas con 1 BE + 1 FE dedicados.

---

## Prompt optimizado — FASE 3: Solicitudes N-productos (XL)

```markdown
# FASE 3 — Solicitudes de Recarga N-productos

ROL: Backend Engineer Senior Python + FastAPI + SQLAlchemy 2.0 async.

LEE PRIMERO:
- docs/adr/adr-0003-transfers-to-solicitudes.md
- docs/adr/adr-0001-postgres-strategy.md
- docs/adr/adr-0002-boxes-modelo.md
- apps/api/app/modules/solicitudes/ (estructura ya creada)
- apps/api/app/modules/transfers/ (lógica existente a refactorizar)
- apps/api/app/modules/inventory/movement_engine.py (motor transaccional)

TAREA:
1. Implementar `SolicitudService` con métodos:
   - `create(bodega_origen_id, productos: list[(producto_id, cantidad)], prioridad, notas)` 
     → valida origen=Auxiliar, destino=Principal (regla ADR-0002)
     → crea solicitud + detalle en transacción atómica
   - `approve(solicitud_id)` → valida estado, pasa a Aprobado, NO descuenta stock aún
   - `dispatch(solicitud_id, lineas_despachadas: list[(producto_id, cantidad)])` 
     → descuenta stock de Principal (no de Origen) usando MovementEngine
     → valida stock suficiente
     → estado pasa a En Transito
   - `receive(solicitud_id, lineas_recibidas: list[(producto_id, cantidad, barcode)])` 
     → incrementa stock de Origen usando MovementEngine
     → estado pasa a Recibido o Parcial
   - `reject(solicitud_id, motivo)` → estado pasa a Rechazado
   - `cancel(solicitud_id, motivo)` → estado pasa a Cancelado (solo si Pendiente)
   
2. Implementar `SolicitudRepository` con:
   - `get_by_id` con `joinedload` de `detalle_solicitud_recarga` y `bodegas`
   - `get_by_estado` con filtros
   - `get_by_bodega_origen` y `get_by_bodega_destino`
   - `lock_solicitud(solicitud_id)` con `SELECT FOR UPDATE`
   
3. Refactor de `TransferService`:
   - Marcar como `@deprecated` con docstring apuntando a `SolicitudService`
   - Mantener endpoints como adaptador sobre `solicitudes_recarga` durante 6 meses
   - Endpoint `GET /api/v1/transfers/{id}/derived` que arma la vista virtual

4. Endpoints nuevos:
   - `POST /api/v1/solicitudes`
   - `GET /api/v1/solicitudes` con filtros
   - `GET /api/v1/solicitudes/{id}`
   - `POST /api/v1/solicitudes/{id}/approve`
   - `POST /api/v1/solicitudes/{id}/dispatch`
   - `POST /api/v1/solicitudes/{id}/receive`
   - `POST /api/v1/solicitudes/{id}/reject`
   - `POST /api/v1/solicitudes/{id}/cancel`

5. Validación de origen/destino en BD:
   - CHECK constraint en migración 0006_solicitudes_recarga.sql (ya existe)
   - Service: validar ANTES de INSERT

6. Tests (mínimo 20):
   - Crear solicitud con 3 productos OK
   - Rechazar solicitud con origen=Principal
   - Rechazar solicitud con destino≠Principal
   - Aprobar no descuenta stock
   - Despachar descuenta de Principal
   - Despachar con stock insuficiente → error
   - Recibir total cierra solicitud
   - Recibir parcial deja en Parcial
   - Cancelar antes de aprobar OK
   - Cancelar después de aprobar → error
   - Concurrencia: 2 dispatch simultáneos del mismo producto
   - E2E completo: crear → aprobar → despachar → recibir

7. Doc: `docs/fases/fase-3-solicitudes-n-productos.md`

RESTRICCIONES: no romper tests existentes, no cambiar API actual de transfers, no usar `print()`.
```

---

## Prompt optimizado — FASE 4: Replenishment automático (L)

```markdown
# FASE 4 — Replenishment automático

LEE PRIMERO: docs/adr/adr-0003-transfers-to-solicitudes.md, Fase 3 ya completa

TAREA:
1. Implementar `ReplenishmentEvaluator` (`apps/api/app/modules/solicitudes/jobs.py`):
   - Job Arq que corre cada 5 minutos
   - Query: `SELECT id_bodega, id_producto FROM stock_levels WHERE quantity <= min_quantity`
   - Filtra: solo bodegas tipo `auxiliar` o `mecanico_box` (con `parent_warehouse_id` nulo)
   - Para cada (bodega, producto) bajo mínimo:
     - Calcula `cantidad = max_quantity - quantity` (cap por max_quantity)
     - Llama a `SolicitudService.create(origen=bodega_aux, productos=[(producto, cantidad)])`
   - Idempotente: si ya hay solicitud `pending` para esa combinación, skip

2. Configuración Arq (`apps/api/app/worker.py`):
   - Carga `Settings`
   - Define `WorkerSettings` con `functions=[replenishment_task]` y `cron_jobs=[cron(replenishment_task, minute={0,5,10,15,20,25,30,35,40,45,50,55})]`
   - Redis URL desde env var `REDIS_URL`

3. Endpoint UI trigger manual:
   - `POST /api/v1/solicitudes/auto-generar` (admin only)
   - Dispara `ReplenishmentEvaluator.run_now()` sin esperar cron

4. Frontend:
   - Reescribir `apps/web/src/views/ReplenishmentPage.jsx`:
     - Cargar `GET /api/v1/inventario/real/bajo-minimo`
     - Mostrar tabla con columnas: Bodega, Producto, Stock actual, Mínimo, Sugerido
     - Botón "Generar Solicitud" por fila (individual)
     - Botón "Generar Solicitudes Masivas" arriba (todas las bajo mínimo)
   - Ruta actual `/replenishment` mantenida

5. Vista nueva `SolicitudesAuxPage` (`apps/web/src/views/SolicitudesAuxPage.jsx`):
   - Ruta `/solicitudes`
   - Filtros: estado, bodega origen, rango fechas
   - Tabla con: código, estado, bodega origen, # productos, total unidades
   - Click en fila → drawer con detalle + acciones (aprobar/rechazar si aplica)
   - Badge de estado con color
   - Botón "Nueva Solicitud Manual" (abre formulario con lista de productos bajo mínimo)

6. Tests:
   - Unit: 5 tests del evaluador (mock del repository)
   - Integration: 1 test que crea BD con 3 productos bajo mínimo y verifica que se generen 3 solicitudes
   - E2E: simular cron → verificar solicitudes creadas

7. Doc: `docs/fases/fase-4-replenishment-automatico.md`
```

---

## Prompt optimizado — FASE 5: Lectores de código de barras en recepción (M)

```markdown
# FASE 5 — Recepción con escaneo de código de barras

LEE: ADR-0003 (solicitudes), apps/web/src/components/BarcodeInput.jsx (ya existe)

TAREA:
1. Vista nueva `RecepcionBandejaPage` (`apps/web/src/views/RecepcionBandejaPage.jsx`):
   - Ruta `/recepciones/en-transito`
   - Carga `GET /api/v1/solicitudes?estado=en_transit&bodega_destino_id={user.bodega}`
   - Tabla con: código, bodega origen, # productos, total, fecha despacho
   - Click en solicitud → vista de recepción con BarcodeInput por línea

2. Vista `RecepcionDetallePage` (`apps/web/src/views/RecepcionDetallePage.jsx`):
   - Ruta `/recepciones/:id`
   - Header con datos de la solicitud
   - Lista de líneas con:
     - Producto (SKU + nombre)
     - Cantidad solicitada
     - Cantidad despachada
     - Cantidad recibida (editable, default=despachada)
     - Input de escaneo con BarcodeInput
     - Botón "Recibir esta línea"
   - Sección "Incidencias" por línea (faltante, daño, problema documental)
   - Botón "Confirmar Recepción Total" al final
   - Estado visual: pendiente / parcial / completo

3. Endpoint backend:
   - `POST /api/v1/solicitudes/{id}/receive-line` con payload:
     ```json
     {
       "lineas": [
         {"producto_id": "...", "cantidad_recibida": 5, "barcode": "7891234567890", "incidencia": null},
         {"producto_id": "...", "cantidad_recibida": 3, "barcode": "7891234567891", "incidencia": "faltante_2"}
       ],
       "notas": "Recepción parcial por faltante"
     }
     ```
   - Valida cada barcode contra `productos.codigo_barras`
   - Si barcode no coincide, rechaza con `barcode_mismatch`
   - Si todas las líneas OK, marca solicitud como Recibido o Parcial
   - Genera movimiento `in` en `inventory_movements` por línea recibida

4. Validación de barcode:
   - EAN-13: validar checksum
   - Code128: solo normalizar (sin checksum)
   - Helper `BarcodeValidator` en `apps/api/app/modules/barcode/validator.py`

5. Tests E2E:
   - 5 líneas escaneadas → solicitud Recibida
   - 3 de 5 líneas escaneadas → solicitud Parcial
   - 1 línea con barcode inválido → error
   - 0 líneas escaneadas (solo confirmación) → no permitido (debe escanear al menos 1)

6. Doc: `docs/fases/fase-5-recepcion-escaneo.md`
```

---

## Prompt optimizado — FASE 6: Supervisores + Órdenes de Compra UI (L)

```markdown
# FASE 6 — Frontend de Supervisores y Órdenes de Compra

LEE: ADR-0004 (smtp), ADR-0005 (token OC), apps/api/app/modules/{supervisores,ordenes_compra}/

TAREA:
1. Vista `SupervisoresPage` (`apps/web/src/views/SupervisoresPage.jsx`):
   - Ruta `/supervisores`
   - Tabla CRUD: nombre, email, activo
   - Botón "Nuevo supervisor" → drawer con form
   - Toggle activo/inactivo inline

2. Vista `ConsolidadorCentralPage` (`apps/web/src/views/ConsolidadorCentralPage.jsx`):
   - Ruta `/consolidador`
   - Carga `GET /api/v1/solicitudes?estado=en_transit&bodega_origen_id=principal` (placeholder, ajustar endpoint)
   - Agrupa líneas por producto: SKU + nombre + cantidad total solicitada (suma de N solicitudes)
   - Calcula "stock disponible en Principal" - "demanda consolidada" = "déficit"
   - Si déficit > 0: marca como "Requiere compra"
   - Botón "Crear Orden de Compra desde este déficit" → abre OC pre-llenada

3. Vista `OrdenesCompraPage` (`apps/web/src/views/OrdenesCompraPage.jsx`):
   - Ruta `/ordenes-compra`
   - Tabla con: código, estado, proveedor, total, supervisor asignado, fecha
   - Filtros: estado, rango fechas
   - Click en OC → drawer con detalle + timeline de estados
   - Botón "Nueva OC" → drawer con form:
     - Proveedor (input libre por ahora, o select de catálogo si hay)
     - Líneas: agregar productos con cantidad + costo unitario
     - Dropdown "Supervisor Autorizador" (carga `GET /api/v1/supervisores?activo=true`)
     - Botón "Enviar Detalle de Compra por Correo" → llama endpoint

4. Vista `OrdenCompraAprobacionPublicaPage` (`apps/web/src/views/OrdenCompraAprobacionPublicaPage.jsx`):
   - Ruta `/ordenes-compra/aprobar/:token` (PÚBLICA, sin auth)
   - Lee el token, llama a `GET /api/v1/ordenes-compra/aprobar/{token}` (valida token, devuelve OC)
   - Muestra: ID OC, bodega origen, solicitante, tabla SKU/Producto/Cantidad/Costo/Subtotal, total
   - 2 botones: "Aprobar" y "Rechazar" (con motivo opcional)
   - Después de aprobar/rechazar: muestra confirmación y oculta los botones
   - Rate limiting visual: si el token es inválido/expirado, mensaje claro

5. Endpoint público (Fase 7 backend, pero registrar ruta frontend):
   - `GET /api/v1/ordenes-compra/aprobar/{token}` (sin auth, rate limited)
   - `POST /api/v1/ordenes-compra/aprobar/{token}` con `{accion: 'aprobar'|'rechazar', motivo?: str}`
   - `POST /api/v1/ordenes-compra/rechazar/{token}` (alias)

6. Tests frontend (5): render de cada vista, formulario OC, dropdown supervisor, vista pública con token válido/inválido.

7. Doc: `docs/fases/fase-6-ordenes-compra-ui.md`
```

---

## Prompt optimizado — FASE 7: Notificaciones SMTP async + Mailpit (L)

```markdown
# FASE 7 — Notificaciones SMTP asíncronas

LEE: ADR-0004 (smtp), ADR-0005 (token OC), apps/api/app/modules/notifications/ (estructura ya existe)

TAREA:
1. Implementar `EmailOutboxService` (`apps/api/app/modules/notifications/service.py`):
   - `enqueue(to_email, subject, body_html, template_name, context)` 
     → INSERT en `email_outbox` (status='pending')
     → LPUSH 'email:queue' con `outbox_id`
   - `get_pending(limit=100)` con `SELECT FOR UPDATE SKIP LOCKED`
   - `mark_sent(outbox_id)` 
   - `mark_failed(outbox_id, error, attempts++)` con backoff exponencial (30s, 5min, 30min)
   - `mark_dead(outbox_id, error)` después de 3 intentos fallidos

2. Plantilla Jinja2 (`apps/api/app/modules/notifications/templates/orden_compra.html.j2`):
   - HTML responsivo con CSS inline
   - Tabla: SKU / Producto / Cantidad / Costo Unitario / Subtotal
   - Total estimado destacado
   - 2 botones HTML (mailto con approve_url y reject_url pre-llenos)
   - Firma con datos de la empresa

3. Arq worker (`apps/api/app/worker.py`):
   - `async def send_email_task(ctx, outbox_id)`: lee de Redis, envía SMTP, actualiza BD
   - Cron `replenishment_task` cada 5 min
   - Cron `retry_failed_emails_task` cada 30 min (reintentos pendientes)

4. SMTP client (`apps/api/app/modules/notifications/smtp.py`):
   - Usa `aiosmtplib` 
   - Lee config de `Settings.smtp_*`
   - Soporta TLS/STARTTLS
   - Timeout 30s, retries 3

5. ApprovalTokenService (`apps/api/app/modules/notifications/token.py`):
   - `generate(orden_compra_id)` → HMAC firmado con `SECRET_KEY`, exp 7 días
   - `validate(token)` → tuple(bool, orden_id | None, error | None)
   - `invalidate(orden_compra_id)` → marca `email_token_hash = NULL` en la OC

6. Mailpit en `infra/docker/compose.local.dev.yml` y `compose.staging.yml`:
   - Servicio `mailpit` con imagen `axllent/mailpit:latest`
   - Puertos 1025 (SMTP) y 8025 (UI web)
   - Variables SMTP del API: `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, `SMTP_TLS=false`

7. Variables nuevas en `.env.example`:
   ```
   SMTP_HOST=mailpit
   SMTP_PORT=1025
   SMTP_USER=
   SMTP_PASSWORD=
   SMTP_FROM=noreply@bodegaje.local
   SMTP_TLS=false
   SECRET_KEY=change-me-in-production-32-chars-min
   TOKEN_EXPIRATION_DAYS=7
   ```

8. Tests:
   - 5 unit tests del EmailOutboxService (mock SMTP)
   - 3 tests del ApprovalTokenService (generar, validar, expirar, invalidar)
   - 2 integration tests con Mailpit en Docker (enviar email real, leer via API mailpit)
   - 1 E2E: crear OC → enviar → leer en Mailpit → click en link → aprobar

9. Doc: `docs/fases/fase-7-smtp-async.md`
```

---

## Prompt optimizado — FASE 8: Resto de vistas nuevas con Tailwind (M)

```markdown
# FASE 8 — Resto de vistas nuevas con Tailwind

CONTEXTO: Tailwind v3 ya está configurado (ADR-0006). Las vistas legacy NO se tocan.

TAREA — implementar 5 vistas restantes con Tailwind:
1. `CategoriasPage` (`apps/web/src/views/CategoriasPage.jsx`):
   - CRUD de categorías con jerarquía opcional
   - Drawer para crear/editar
   - Vista árbol colapsable

2. `ReplenishmentRuleForm` (componente):
   - Form para parametrizar reglas de reabastecimiento por producto-bodega
   - min, max, lead_time, supplier_preferred_id

3. `NotificationsCenter` (componente):
   - Lista de notificaciones del usuario
   - Marcar como leída
   - Integrar con WebSocket cuando esté disponible (Fase futura)

4. `ReportsExports` (extensión de `ReportsPage.jsx`):
   - Añadir exportación PDF ejecutiva (vía jsPDF o @react-pdf/renderer)
   - Botón "Exportar Reporte Ejecutivo" genera snapshot para gerencia

5. `SystemSettingsPage` (refactor de `SettingsPage.jsx`):
   - Tab: Reglas de Reabastecimiento
   - Tab: Proveedores (CRUD)
   - Tab: Parámetros de Stock (min/max por bodega-producto)

RESTRICCIONES:
- Solo Tailwind en estas vistas, NO en las 11 legacy
- Componentes reutilizables en `apps/web/src/components/`
- a11y: aria-labels, roles, navegación por teclado
- Responsive: tablet (768px) y desktop (1024px+)

Doc: `docs/fases/fase-8-vistas-tailwind.md`
```

---

## Prompt optimizado — FASE 9: Observabilidad mínima (M)

```markdown
# FASE 9 — Observabilidad mínima

TAREA:
1. Logs estructurados con `structlog`:
   - Configurar en `apps/api/app/core/logging.py`
   - JSON output a stdout
   - Correlation ID por request (middleware)
   - Logger por módulo

2. Métricas Prometheus:
   - `prometheus-fastapi-instrumentator` 
   - `/metrics` endpoint
   - Métricas custom: `email_outbox_pending`, `email_sent_total`, `email_failed_total`, `solicitudes_por_estado{estado="..."}`

3. Healthcheck ampliado:
   - `GET /api/v1/health` devuelve:
     ```json
     {
       "status": "ok",
       "components": {
         "db": "ok|latency_ms",
         "redis": "ok|down",
         "worker": "ok|down"
       }
     }
     ```
   - HTTP 200 si todo OK, 503 si algo crítico cae

4. Tracing (opcional, M adicional):
   - OpenTelemetry + FastAPI instrumentation
   - Export a OTLP (Jaeger o Tempo)

5. Tests:
   - `/metrics` devuelve datos
   - `/health` con BD caída → 503
   - Logs en formato JSON con `correlation_id`

Doc: `docs/fases/fase-9-observabilidad.md`
```

---

## Prompt optimizado — FASE 10: Hardening producción (L)

```markdown
# FASE 10 — Hardening para producción

TAREA:
1. Secretos en vault:
   - Migrar `.env` a vault (Doppler / HashiCorp Vault / AWS Secrets Manager)
   - Generador de `SECRET_KEY` con `secrets.token_urlsafe(32)`
   - Documentar procedimiento de rotación

2. Nginx hardening (`infra/docker/nginx/conf.d/production.conf`):
   - Rate limiting: 100 req/min por IP, 10 req/s burst
   - Headers: `Strict-Transport-Security`, `X-Frame-Options DENY`, `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin`, `Content-Security-Policy`
   - SSL/TLS: certbot o Caddy con Let's Encrypt
   - Ocultar versión de Nginx: `server_tokens off`
   - Limitar body size: `client_max_body_size 10m`

3. Backup automatizado:
   - Script `infra/scripts/backup-postgres.sh` con `pg_dump` + rotación 7/30/365 días
   - Cron diario en compose.production.yml
   - Verificación mensual: restaurar en staging y validar

4. Runbook de producción:
   - Actualizar `infra/operations/DEPLOYMENT_RUNBOOK.md`
   - Procedimientos de rollback (git tag, docker rollback, db migration down)
   - Procedimientos de incidentes (BD caída, Redis caído, SMTP caído)

5. CI/CD (opcional):
   - GitHub Actions: lint + test + build + push image
   - Despliegue automatizado a staging
   - Despliegue manual a producción (con approval)

6. Tests de carga:
   - `locust` o `k6` con 100 usuarios concurrentes
   - Verificar p95 < 400ms en endpoints comunes
   - Verificar que la cola SMTP no se desborda

7. Doc: `docs/fases/fase-10-hardening-produccion.md` + actualizar `infra/operations/DEPLOYMENT_RUNBOOK.md`
```

---

## Próximo paso recomendado

1. **Auditar el código de Fases 1 y 2** con un subagente `verifier` (lanzar en background).
2. **Ejecutar Fase 3** (Solicitudes N-productos) — es la más crítica del roadmap.
3. **Si la sesión se acaba**, retomar con Fase 4 y siguientes usando estos prompts.
4. **Validar** que cada fase se entrega con: tests passing + doc en `docs/fases/` + ADR actualizado si hay cambio arquitectural.
