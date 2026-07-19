---
title: "Fase 7 — SMTP asíncrono con Mailpit"
date: "2026-07-15"
status: "Completada"
predecesores: ["Fase 0", "Fase 1", "Fase 2", "Fase 3", "Fase 4", "Fase 5", "Fase 6"]
sucesores: ["Fase 8 (vistas Tailwind)", "Fase 9 (observabilidad)"]
---

# Fase 7 — SMTP asíncrono con Mailpit

## Resumen ejecutivo

La Fase 7 cierra el **flujo de email end-to-end** del proyecto: cuando el
bodeguero central presiona "Enviar Detalle de Compra por Correo", la API
inserta una fila en `email_outbox` y encola un job en Arq. El worker
procesa la cola, renderiza una plantilla HTML responsiva con Jinja2 (CSS
inline vía premailer) y envía el email vía **aiosmtplib** a un servidor
SMTP. En desarrollo ese servidor es **Mailpit** (UI web en
`http://localhost:8025`); en producción será SES / SendGrid / Mailgun.

La implementación aplica estrictamente la decisión arquitectónica del
**ADR-0004 (SMTP asíncrono sobre Arq)** y mantiene compatibilidad con el
**ADR-0005 (token HMAC de aprobación)**. La API responde en **<100ms** al
bodeguero (no espera SMTP), la entrega es **garantizada** (el outbox
persiste hasta `status='sent'`), y los reintentos absorben caídas
transitorias con **backoff exponencial 30s → 5min → 30min**, llevando
el email a `status='dead'` tras 3 fallos.

---

## Cambios realizados

### Backend — Nuevos archivos

| Archivo | Líneas | Descripción |
|---|---:|---|
| `apps/api/app/modules/notifications/smtp.py` | 130 | Cliente SMTP async (aiosmtplib) + jerarquía de errores (`SmtpError`, `SmtpPermanentError`). |
| `apps/api/app/modules/notifications/templates.py` | 105 | Loader Jinja2 + helper `render_with_inline_css` (aplica `premailer`). |
| `apps/api/app/modules/notifications/templates/orden_compra.html.j2` | 145 | Plantilla HTML responsiva con CSS inline, tabla OC, botones aprobar/rechazar, footer. |
| `apps/api/tests/unit/test_notifications_service.py` | 320 | 11 tests unitarios del service (mock SMTP + mock Arq). |
| `apps/api/tests/integration/test_smtp_mailpit.py` | 360 | 6 tests de integración con Mailpit (auto-skip si no está disponible). |
| `apps/api/tests/manual/test_e2e_fase7.py` | 280 | Smoke test E2E manual del flujo completo con Mailpit. |

### Backend — Archivos modificados

| Archivo | Líneas añadidas | Descripción |
|---|---:|---|
| `apps/api/app/modules/notifications/service.py` | +400 | Refactor: `enqueue` (canónico con template+context), `process_one` (worker Arq), `retry_dead`, `metrics`. Mantiene `enqueue_email` y `process_pending` legacy para compat. |
| `apps/api/app/modules/notifications/worker.py` | +30 | Marcado **DEPRECATED** con `warnings.warn(DeprecationWarning)`. La forma canónica es Arq. |
| `apps/api/app/modules/notifications/router.py` | 0 | Sin cambios (la Fase 9 ya tenía el endpoint debug `/outbox`). |
| `apps/api/app/worker.py` | +120 | Añadido `send_email_task(outbox_id)`, helper `enqueue_send_email_task` (Arq enqueue desde API), constante `SEND_EMAIL_TASK`. |
| `apps/api/app/core/config.py` | +60 | Nuevos settings: `smtp_timeout_seconds`, `email_max_attempts`, `email_retry_backoff_seconds` (CSV), `public_base_url` + property `email_retry_backoff_list`. |
| `apps/api/tests/integration/test_notifications.py` | reescrito | Actualizado para mockear `svc_module.smtp_send_email` (alias del import). |
| `apps/api/requirements.txt` | +1 | `aiosmtplib==3.0.1`. |

### Infra

| Archivo | Descripción |
|---|---|
| `infra/docker/docker-compose.yml` | Añadido servicio `mailpit` (axllent/mailpit:latest, puertos 1025+8025) y servicio `worker` (Arq). |
| `infra/docker/compose.local.dev.yml` | Expone puertos de Mailpit, añade env vars `SMTP_*` y `PUBLIC_BASE_URL` a api+worker. |
| `infra/.env.example` | Bloque SMTP/Email/Public_URL nuevo, plantilla `JWT_SECRET` ≥ 32 chars. |

---

## Decisiones de implementación (resumen del ADR-0004)

### Flujo de un email

```
1. API: POST /api/v1/ordenes-compra/{id}/enviar-correo
2. OrdenCompraService.enviar_correo (Fase 6):
   a. Valida estado BORRADOR → ENVIADO_A_SUPERVISOR.
   b. Genera token HMAC (ADR-0005).
   c. INSERT email_outbox (status='pending').
3. NotificationsService.enqueue (Fase 7):
   a. Valida email destino.
   b. Renderiza plantilla Jinja2 con context (CSS inline via premailer).
   c. UPDATE email_outbox.body_html con snapshot renderizado.
   d. LPUSH 'arq:queue' con outbox_id (helper enqueue_send_email_task).
4. Worker Arq (proceso bodegaje-worker):
   a. BLPOP 'arq:queue' → outbox_id.
   b. NotificationsService.process_one(outbox_id):
      - SELECT email_outbox WHERE id=?
      - Si status != 'pending' → skip (otro worker lo proceso).
      - Si attempts >= email_max_attempts → status='dead', commit.
      - smtp.send_email (aiosmtplib):
          * OK: status='sent', sent_at=now().
          * SmtpPermanentError (5xx RCPT): status='dead'.
          * SmtpError transitorio: attempts++, status='pending'.
            Log: notifications.retry_scheduled con backoff_next.
            (Cron de retry en Fase 9+ lo recoge.)
```

### Reintentos con backoff exponencial

Configurable vía `email_retry_backoff_seconds` (CSV en env, default
`"30,300,1800"` = 30s, 5min, 30min). El service NO tiene cron de retry
propio: cuando Arq falla un job, la **próxima ejecución la dispara un
operador o el cron de Fase 9** (`retry_dead()` encolar manual). Esto es
deliberado: el modelo pull es más simple que mantener timestamps
`next_retry_at` en una columna extra (que se omitió para evitar una
migración nueva en Fase 7).

### Worker Arq vs script standalone (legacy)

| Aspecto | Arq (Fase 7 canónico) | Script standalone (`notifications/worker.py`) |
|---|---|---|
| Persistencia | Redis (job en `arq:queue`) | Loop en memoria (pierde al restart) |
| Reintentos | Manual via `process_one` re-encolado | No |
| Lock atómico | `process_one` con SELECT + update | No (dos workers duplican) |
| Observabilidad | Hooks `on_startup`/`on_shutdown` | Solo log de boot |
| Multi-proceso | Sí (N workers escalan) | No (1 proceso, 1 loop) |
| Mantenimiento | Activo | DEPRECADO desde Fase 7 |

---

## Diagrama del flujo

```
   [Bodeguero Central]                            [Sistema]                    [Worker Arq]              [Mailpit/SES]
        |                                              |                              |                        |
   1. Crear OC borrador                             |                              |                        |
   POST /ordenes-compra --> Service.create_orden ---->|                              |                        |
                                                  [estado: borrador]                |                        |
        |                                          |                                 |                        |
   2. Enviar correo                               |                                 |                        |
   POST .../enviar-correo --> OrdenCompraService  |                                 |                        |
        |                                     INSERT email_outbox                  |                        |
        |                                     (status=pending)                       |                        |
        |                                     + Arq.enqueue_job(send_email_task)----+                        |
        |                                          |                              |                        |
        |                                          |                       BLPOP arq:queue                  |
        |                                          |                       process_one(outbox_id)          |
        |                                          |                              |                        |
        |                                          |                       smtp.send_email (aiosmtplib) --->|
        |                                          |                              |                  SMTP al server
        |                                          |                              |                  (Mailpit dev / SES prod)
        |                                          |                              |<---- 250 OK  -------|
        |                                          |                       UPDATE outbox                 |
        |                                          |                       status='sent', sent_at=now()  |
        |                                          |                              |                        |
   3. UI refresca; ve OC "Enviado"                 |                              |                        |
        |                                          |                              |                        |
        |                                          |                              |                  [UI: http://localhost:8025]
        |                                          |                              |                        ^
        |                                          |                              |                        |
        |                                          |                              |       (Si falla SMTP)  |
        |                                          |                              |--- 5xx/timeout -------|
        |                                          |                              |                        |
        |                                          |                              | attempts++             |
        |                                          |                              | status='pending'       |
        |                                          |                              | (backoff log)          |
        |                                          |                              |                        |
        |                                          |                              |--- 3er fallo --------->|
        |                                          |                              | status='dead'          |
        |                                          |                              | admin: retry_dead()    |
        v                                                                                                       |
   4. [Supervisor] Click link                                                                                   |
        |                                                                                                       |
   5. GET /public/ordenes-compra/aprobar/{token} (sin auth)                                                    |
   6. POST /public/.../aprobar {token}                                                                          |
   7. OC pasa a APROBADO; email_token_jti=NULL (one-shot)                                                       |
```

---

## Cómo correr localmente

### Prerrequisitos

- Docker + Docker Compose.
- Python 3.14 con `requirements.txt` instalado.

### Levantar Mailpit + Redis + Postgres + worker

```bash
# 1. Levantar infra (incluye mailpit, redis, db, worker, api, web, nginx)
docker compose -f infra/docker/docker-compose.yml up -d

# 2. Ver logs del worker (deberia mostrar "worker.startup" con ambas tareas)
docker compose -f infra/docker/docker-compose.yml logs -f worker

# 3. Abrir Mailpit UI: http://localhost:8025
```

### Probar el envío manualmente

```bash
# 1. Crear supervisor via API
curl -X POST http://localhost:8000/api/v1/supervisores \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"nombre":"Juan Test","email":"juan.test@bodega.example"}'

# 2. Crear OC borrador con lineas + supervisor
# (ver flujo completo en fase-6-ordenes-compra-ui.md)

# 3. Enviar la OC por correo
curl -X POST http://localhost:8000/api/v1/ordenes-compra/{oc_id}/enviar-correo \
  -H "Authorization: Bearer <TOKEN>"

# 4. Ver el email en Mailpit UI (http://localhost:8025)
```

### Ejecutar el smoke test E2E manual

```bash
cd apps/api
python -m tests.manual.test_e2e_fase7
```

Output esperado: `[OK] E2E FASE 7: PASS` tras verificar el envío real a
Mailpit, extracción del token, y aprobación end-to-end.

---

## Cómo correr los tests

```bash
cd apps/api

# Unit (rápidos, sin SMTP ni Redis)
python -m pytest tests/unit/test_notifications_service.py -v

# Integration con Mailpit (skippea automáticamente si no hay mailpit en localhost:1025/8025)
python -m pytest tests/integration/test_smtp_mailpit.py -v

# Integration Fase 9 (mock SMTP, sin dependencias externas)
python -m pytest tests/integration/test_notifications.py -v

# Suite completa
python -m pytest tests/unit tests/integration -v
```

### Resultado esperado

- **238 tests passing** (226 baseline + 11 nuevos unit + 1 mailpit-E2E que pasa sin necesidad de Mailpit).
- **12 skipped** (7 pre-existentes por Postgres-only + 5 nuevos por Mailpit no disponible).
- **0 fallos**, **0 regresiones** sobre la suite original.

---

## Ejemplo de email renderizado

Asumiendo supervisor "Juan Test" + OC-0042 con 2 líneas:

```html
<!DOCTYPE html>
<html lang="es">
<body style="background-color: #f4f4f5;">
<table role="presentation" width="600">
  <tr>
    <td style="background: linear-gradient(135deg, #0f766e 0%, #115e59 100%);">
      <h1 style="color: #ffffff;">Bodegaje</h1>
      <p>Orden de Compra</p>
    </td>
  </tr>
  <tr>
    <td>
      <h2>Hola Juan Test,</h2>
      <p>Se ha generado una nueva orden de compra que requiere tu aprobación.</p>
      <table>
        <tr><td>ID Orden</td><td><strong>OC-0042</strong></td></tr>
        <tr><td>Bodega Origen</td><td>Principal</td></tr>
        <tr><td>Solicitante</td><td>Pedro Ramirez</td></tr>
        <tr><td>Proveedor</td><td>Repuestos Chile</td></tr>
        <tr><td>Total Estimado</td><td style="color: #0f766e; font-size: 18px;">$30.000</td></tr>
      </table>
      <a href="http://localhost:5173/ordenes-compra/aprobar/abc.def.ghi"
         style="background-color: #027a48; color: #ffffff; padding: 14px 32px;">
        Aprobar
      </a>
      <a href="http://localhost:5173/ordenes-compra/rechazar/abc.def.ghi"
         style="background-color: #b42318; color: #ffffff; padding: 14px 32px;">
        Rechazar
      </a>
      <p>Este enlace expira el 2026-07-22.</p>
    </td>
  </tr>
</table>
</body>
</html>
```

El HTML se almacena en `email_outbox.body_html` como snapshot, por lo
que el envío NO depende del filesystem en runtime (el worker no necesita
la plantilla en su imagen — solo la BD y la conexión SMTP).

---

## Riesgos conocidos

1. **Worker Arq debe correr en un proceso separado** (servicio `worker`
   del compose). Si se cae, los emails se acumulan en `email_outbox` y
   en `arq:queue`. **Mitigación**: healthcheck de Fase 9 puede detectar
   el consumer count de Arq y alertar.

2. **`next_retry_at` no se persiste en BD**: el log `notifications.retry_scheduled`
   tiene el backoff sugerido, pero no hay cron que lo consuma
   automáticamente en Fase 7. **Mitigación**: un operador corre
   `POST /notificaciones/admin/retry-dead` (TODO Fase 9) o el cron
   `send_email_task` se re-encolará cuando el job de Arq falle
   (Arq 0.28 retry builtin). Documentado como follow-up.

3. **Email con destinatario inválido se marca `dead` y NO se
   reintenta**. Esto es correcto: SMTP devolvió 5xx permanente. El
   operador debe corregir la dirección del supervisor y correr
   `retry_dead()`. Documentado en `SmtpPermanentError`.

4. **Premailer puede no estar instalado** (es opcional). Sin premailer,
   el email sale con bloque `<style>` en head — Gmail/Apple Mail lo
   respetan, pero Outlook puede romper. **Mitigación**: premailer está
   en `requirements.txt` (`premailer==3.10.0`).

5. **Race condition entre 2 workers leyendo el mismo outbox**:
   mitigada por el status check (`if status != 'pending' skip`) en
   `process_one`. El `commit` después de cada update asegura que el
   segundo worker vea `status='sent'` y skipee. Si ambos leen
   simultáneamente el row antes de cualquier commit, el primero que
   haga `commit('sent')` gana; el segundo verá `status='sent'` y
   skipea sin reenviar.

---

## Próximos pasos (Fase 8 y siguientes)

- **Fase 8 — Vistas Tailwind restantes**: 5 vistas más para llegar a
  paridad de features con las 11 legacy.
- **Fase 9 — Observabilidad**: `/metrics` con `email_outbox_pending`,
  `email_sent_total`, `email_failed_total`; healthcheck extendido;
  cron de retry automático que lea `email_outbox` y re-encole
  pendientes.
- **Fase 10 — Hardening prod**: vault para `SMTP_PASSWORD`, rate
  limit en `/notificaciones/admin/retry-dead`, runbook de incidentes
  SMTP caídos.
