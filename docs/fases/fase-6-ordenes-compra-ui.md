---
title: "Fase 6 — Frontend de Ordenes de Compra + Catalogo de Supervisores"
date: "2026-07-15"
status: "Completada"
predecesores: ["Fase 0", "Fase 1", "Fase 2", "Fase 3", "Fase 4", "Fase 5"]
sucesores: ["Fase 7 (SMTP async)"]
---

# Fase 6 — Frontend de Ordenes de Compra + Catalogo de Supervisores

## Resumen ejecutivo

La Fase 6 entrega el **CRUD de Supervisores** y la **UI completa de Ordenes
de Compra externas** con aprobacion publica por token HMAC. El bodeguero
central puede ahora consolidar quiebres, crear OCs, seleccionar supervisor
y enviar el detalle por email; el supervisor recibe el link y aprueba
o rechaza con un clic desde una vista Tailwind v3 sin requerir login.

Esta fase implementa **el frontend completo** del flujo de OC (vistas
Tailwind v3) y **el esqueleto del outbox** para envio asincrono de email
(Fase 7 conectara el worker Arq al outbox que esta fase llena).

---

## Cambios realizados

### Backend

| Archivo | Estado | Descripcion |
|---|---|---|
| `apps/api/app/modules/supervisores/router.py` | modificado | GET (con ?activo), POST, GET id, PATCH, DELETE (soft). 5 endpoints. |
| `apps/api/app/modules/supervisores/service.py` | modificado | `list_supervisores(activo=None)`, `create_supervisor`, `update_supervisor`, `deactivate_supervisor`. Excepciones de dominio. |
| `apps/api/app/modules/supervisores/schemas.py` | **nuevo** | `SupervisorCreate/Update/Response`. |
| `apps/api/app/modules/ordenes_compra/router.py` | reescrito | 9 endpoints internos (CRUD + transiciones). Schemas separados. |
| `apps/api/app/modules/ordenes_compra/service.py` | reescrito | `create_orden`, `update_orden`, `enviar_correo`, `aprobar_orden`, `rechazar_orden`, `marcar_comprada`, `aprobar_con_token`, `get_orden_por_token`, `list_ordenes` con filtros. |
| `apps/api/app/modules/ordenes_compra/schemas.py` | **nuevo** | `OCCreate/Update/Response`, `DetalleOCCreate/Response`, `EnviarCorreoResponse`, `RechazoPayload`, `CompraRequest`. |
| `apps/api/app/modules/ordenes_compra/public_router.py` | **nuevo** | Router publico (sin auth) con 3 endpoints + rate limit 5 req/min. |
| `apps/api/app/core/rate_limit.py` | **nuevo** | Rate limiter in-memory sliding-window por (ip, scope). Sin dependencias externas. |
| `apps/api/app/api/router.py` | modificado | Incluye `ordenes_public_router` con prefijo `/public/ordenes-compra`. |
| `apps/api/tests/unit/test_supervisores.py` | **nuevo** | 7 tests (crear, duplicado, email invalido, listar con filtro, update, soft delete, permisos). |
| `apps/api/tests/unit/test_ordenes_compra.py` | **nuevo** | 11 tests (crear, update solo en borrador, enviar correo + outbox, enviar solo borrador, aprobar/rechazar via token, token invalido, token expirado, rate limit). |

### Frontend

| Archivo | Estado | Descripcion |
|---|---|---|
| `apps/web/src/views/SupervisoresPage.jsx` | **nuevo** | CRUD completo con drawer, filtro activo/inactivo, busqueda, soft delete con confirmacion. |
| `apps/web/src/views/OrdenCompraAprobacionPublicaPage.jsx` | **nuevo** | Vista PUBLICA sin auth. Tabla de lineas, total, botones Aprobar/Rechazar, manejo de errores 401/410/429. |
| `apps/web/src/views/OrdenesCompraPage.jsx` | reescrito | Tabla con filtros (estado, proveedor, fechas), drawer "Nueva OC" con form completo (lineas + supervisor dropdown), drawer detalle con timeline + acciones (enviar, aprobar, rechazar, marcar comprada). |
| `apps/web/src/views/ConsolidadorCentralPage.jsx` | reescrito | Calculo de deficit (demanda - stock) desde solicitudes en estados que consumen + stock real de Principal. Boton "Crear OC desde este deficit" navega a /ordenes-compra con prefill. |
| `apps/web/src/router.jsx` | modificado | 4 rutas nuevas: `/supervisores`, `/ordenes-compra` (refinada), `/consolidador` (refinada), `/ordenes-compra/aprobar/:token` (PÚBLICA, fuera de ProtectedLayout). |
| `apps/web/src/lib/api.js` | modificado | Agregado `deleteJson`. |
| `apps/web/src/shell/AppShell.jsx` | modificado | Sidebar: nuevo link "Supervisores". |

---

## Decisiones de implementacion

### 1. Token HMAC y rate limiting (ADR-0005)

- **Sin cambios en `ApprovalTokenService`**: la API publica usa tal cual
  el servicio existente (`issue_approval_token`, `verify_approval_token`).
- **Token one-shot**: despues de aprobar/rechazar, `email_token_jti` se
  setea a `NULL` para invalidar el token inmediatamente.
- **Rate limit sin `slowapi`**: implementamos un sliding-window in-memory
  en `app/core/rate_limit.py`. Suficiente para MVP (single-process).
  Cuando se requiera Redis-backed, sera trivial reemplazar la clase
  `RateLimiter` por una que use Redis con INCR + EXPIRE.

### 2. Outbox pattern (ADR-0004)

- **Esta fase SOLO encola**. El endpoint `POST /api/v1/ordenes-compra/{id}/enviar-correo`
  inserta una fila en `email_outbox` con `status='pending'` y NO envia
  el email.
- **Fase 7 conectara el worker Arq** que consume la cola, renderiza la
  plantilla Jinja2 `orden_compra.html.j2` y envia via SMTP.
- La plantilla HTML se incluye inline minima (`<h1>OC {codigo}</h1>...`)
  para que el worker en Fase 7 solo tenga que renderizar con Jinja2.

### 3. UI Tailwind v3 sin CSS plano

- Las 3 vistas (`SupervisoresPage`, `OrdenesCompraPage`, `ConsolidadorCentralPage`)
  y la vista publica (`OrdenCompraAprobacionPublicaPage`) usan 100%
  Tailwind v3 utility-first.
- ADR-0006: las 11 vistas legacy NO se tocan.
- `AppShell` sigue con CSS plano (legacy), solo agregamos un link
  adicional al sidebar.

### 4. Soft delete de Supervisores

- La FK en `ordenes_compra.id_supervisor` es `ON DELETE RESTRICT`.
- Eliminar fisicamente un supervisor con OCs asociadas falla.
- Soft delete (`activo=False`) preserva el historial y mantiene la
  validacion "no se puede asignar OC a supervisor inactivo".

### 5. Flush explicito antes de commit

- En `OrdenCompraService.create_orden` se hace `await self._session.flush()`
  entre `add(oc)` y `add(detalles)` porque la PK compuesta de
  `detalle_orden_compra` referencia `id_orden_compra`. Sin flush, el
  INSERT del detalle intenta usar `oc.id` que aun no esta materializado
  en la BD, y la FK falla con `FOREIGN KEY constraint failed`.

### 6. Comportamiento de `enviar_a_supervisor` (alias)

- La firma previa (Fase 8) era `enviar_a_supervisor(oc_id) -> (view, token)`.
- La nueva firma canonica es `enviar_correo(oc_id) -> (view, token, outbox_id)`.
- `enviar_a_supervisor` se mantiene como **alias** que devuelve solo
  `(view, token)` para preservar la API del test
  `tests/integration/test_ordenes_compra.py` (Fase 8) y la regla R6
  "no romper tests existentes".

---

## Diagrama de flujo

```
   [Bodeguero Central]                            [Sistema]                    [Supervisor]
        |                                              |                              |
   1. Crear OC borrador                             |                              |
   POST /ordenes-compra --> Service.create_orden ---->                               |
                                                  [estado: borrador]                |
        |                                          |                                 |
   2. Enviar correo                               |                                 |
   POST .../enviar-correo --> Service.enviar_correo                                  |
        |                                          |                                 |
        |                                     genera token HMAC                       |
        |                                     INSERT email_outbox (pending)            |
        |                                     [estado: enviado_a_supervisor]            |
        |                                          |                                 |
        |                                          +----- Arq worker (Fase 7) ------->|
        |                                                                        [email + link]
        |                                                                              |
        |                                                                        3. Click link
        |                                                                              |
        |                                                                        GET /ordenes-compra/
        |                                                                        aprobar/{token}
        |                                                                              |
        |                                                                        4. Aprueba/Rechaza
        |                                                                        POST /public/.../
        |                                                                        aprobar|rechazar/{token}
        |                                                                              |
        |                                          <----- Service.aprobar_con_token ---+
        |                                          cambia estado (aprobado/rechazado)
        |                                          invalida token (one-shot)
        v
   5. Refresca UI; ve OC aprobada
```

---

## Ejemplo de sesion E2E (mock)

1. **Admin crea supervisor "Juan Perez"** (`/supervisores`):
   ```
   POST /api/v1/supervisores
   { "nombre": "Juan Perez", "email": "juan@bodega.example" }
   → 201 { "id": "...", "activo": true, ... }
   ```

2. **Bodeguero consolida quiebres** (`/consolidador`):
   - Tabla muestra `Producto A: demanda 30, stock 10, deficit 20`
   - Click en "Crear OC desde este deficit"
   - Navega a `/ordenes-compra` con el drawer de "Nueva OC" pre-llenado:
     ```
     lineas: [{ id_producto: "A", cantidad_pedida: 20, costo_unitario_pactado: 0 }]
     notas: "Generada desde Consolidador (deficit 20)."
     ```

3. **Bodeguero completa la OC** (modal de Nueva OC):
   - Proveedor: "Repuestos Chile"
   - Bodega principal: PRINCIPAL (auto-seleccionada)
   - Supervisor: Juan Perez (dropdown)
   - Costo unitario linea A: 1500 CLP
   - Click "Crear borrador"
   - Backend retorna `OC-0001` con `estado: borrador`

4. **Bodeguero envia por correo** (drawer de detalle):
   - Click "Enviar correo al supervisor"
   - Backend:
     - Genera token HMAC
     - INSERT en `email_outbox` (status=pending, to_email=juan@bodega.example, body_html con link al token)
     - OC pasa a `enviado_a_supervisor`
   - Respuesta: `{ oc: {...}, approval_token: "abc.def.ghi" }` (solo devuelto en testing)
   - En Fase 7, el worker Arq enviara el email real a `juan@bodega.example`

5. **Supervisor abre el email** (link apunta a `/ordenes-compra/aprobar/<token>`):
   - La vista publica (sin auth) llama a `GET /api/v1/public/ordenes-compra/aprobar/<token>`
   - Muestra: OC-0001, Repuestos Chile, tabla con Producto A x20 a 1500, total 30000 CLP
   - Botones "Aprobar orden" (verde) y "Rechazar" (rojo)

6. **Supervisor aprueba**:
   - Click "Aprobar orden"
   - Backend: `POST /api/v1/public/ordenes-compra/aprobar/<token>` (sin auth)
   - Service valida token, valida estado, cambia a `aprobado`, graba `aprobado_at`
   - UI muestra confirmacion: "Aprobacion registrada"

7. **Bodeguero ve la OC aprobada** (refresca `/ordenes-compra`):
   - Badge "Aprobado"
   - Click en OC ve timeline completo

8. **Bodeguero marca como comprada** (cuando llega la mercaderia):
   - Click "Marcar como comprada" en drawer detalle
   - OC pasa a `comprado`, `comprado_at = now()`

---

## Como correr los tests

```bash
# Backend (unit + integration + e2e)
cd apps/api
python -m pytest tests/unit tests/integration tests/e2e -v

# Solo los nuevos tests de Fase 6
python -m pytest tests/unit/test_supervisores.py tests/unit/test_ordenes_compra.py -v

# Frontend (build + lint)
cd apps/web
npx vite build
npx eslint src/views/SupervisoresPage.jsx \
           src/views/OrdenesCompraPage.jsx \
           src/views/ConsolidadorCentralPage.jsx \
           src/views/OrdenCompraAprobacionPublicaPage.jsx
```

### Resultado esperado

- **226 tests passing** (208 baseline Fase 0-5 + 18 nuevos Fase 6)
- **7 skipped** (tests Postgres-only no aplicables)
- **10 pre-existing failures** en `tests/test_api.py` (legacy, sin cambios)
- **0 errores** de lint, 0 errores de build Vite

---

## Riesgos conocidos

1. **Rate limit in-memory NO escala multi-proceso**: si el API se
   ejecuta con `--workers > 1` (uvicorn workers), cada worker tiene su
   propio rate limiter. Para produccion multi-worker, se debe migrar
   a Redis-backed. **Mitigacion**: documentar como follow-up en Fase 7.

2. **Email no se envia en esta fase**: el `email_outbox` queda en
   `status='pending'` hasta que Fase 7 levante el worker Arq. **Mitigacion**:
   la UI claramente muestra "Email encolado" (no "Email enviado") para
   evitar expectativas falsas.

3. **Token en URL de aprobacion viaja en claro en logs del navegador**:
   por ADR-0005 NEG-002, el supervisor podria reenviar el email.
   **Mitigacion aceptada**: el riesgo esta firmado en el ADR.

4. **El campo `updated_at` del modelo `ordenes_compra` reusa
   `created_at_column()`** (no tiene onupdate). Esto significa que el
   `updated_at` que devolvemos al frontend es igual a `created_at`. **Mitigacion**:
   en una migracion futura (Fase 7+), cambiar a `updated_at_column()`.

5. **Flush explicito en `create_orden`**: una decision de implementacion
   para resolver el orden de inserts con FK compuesta. Tests validan
   el comportamiento.

---

## Proximos pasos (Fase 7 — SMTP async)

- Implementar `EmailOutboxService.enqueue()` (esta fase ya hace el INSERT;
  Fase 7 agrega la API publica de encolar emails no-OC).
- Implementar worker Arq que lea de Redis, renderice plantilla Jinja2,
  envie via SMTP (aiosmtplib) y actualice `email_outbox.status='sent'`.
- Levantar Mailpit en `compose.local.dev.yml` y `compose.staging.yml`.
- Implementar reintentos con backoff exponencial (3 intentos: 30s/5min/30min).
- Tests E2E: 2 workers Arq contra la misma cola, verificar que ningun
  email se duplica (lock atomico en `email_outbox`).

---

## Diagrama de estado de la OC

```
   borrador
   ─┬────────────────────────────────┐
   │                                │
   │ POST /enviar-correo            │
   │ (genera token, encola email)   │
   v                                │
   enviado_a_supervisor             │
   ─┬─────────────┬─────────────────┤
   │             │                 │
   │ POST        │ POST            │
   │ .../aprobar │ .../rechazar    │
   │ (interno)   │ { motivo }      │
   v             v                 │
   aprobado    rechazado           │
   ─┬──────┐                        │
   │      │                        │
   │ POST │ .../comprar            │ NO SE PUEDE
   v      │                        │ modificar
   comprado v                       │ desde enviado
          (estado terminal)         │
                                   │
   cualquier otro transicion ──> 409 invalid_orden_compra_status
```
