---
title: "ADR-0004: Arquitectura de notificaciones SMTP asíncronas"
status: "Accepted"
date: "2026-07-14"
authors: "Equipo Bodegaje"
tags: ["arquitectura", "notificaciones", "smtp", "redis", "arq"]
supersedes: ""
superseded_by: ""
---

# ADR-0004: Arquitectura de notificaciones SMTP asíncronas

## Status

**Accepted** — Decisión ratificada para la Fase 7 del roadmap.

## Context

La spec exige que la Bodega Principal genere automáticamente un email HTML responsivo al Supervisor de Turno cuando se confirma una Orden de Compra externa. El email debe incluir:

- ID de la Orden de Compra
- Bodega que la originó
- Nombre del solicitante
- Tabla con SKU / Producto / Cantidad / Costo / Subtotal
- Enlace de aprobación directa con token temporal

Esta operación tiene tres restricciones críticas:

1. **No debe bloquear** la UI del bodeguero central (latencia SMTP variable)
2. **No debe perderse** si el worker muere (entrega garantizada)
3. **Debe ser reintentable** con backoff exponencial (SMTP cae, timeouts, etc.)

`FastAPI BackgroundTasks` no cumple (1) ni (2): las tareas viven en el mismo proceso y se pierden si muere. `Celery` es sobredimensionado para 1 sola cola. Se requiere un worker async nativo con persistencia de jobs.

## Decision

Adoptar **Arq** (`arq==0.26`) sobre Redis como worker asíncrono. Un único proceso `worker` consume la cola `email:queue` (LIST Redis con `BLPOP`) y procesa `send_email_task`. El encolado lo hace el `EmailOutboxService` desde la API.

### Componentes

| Componente | Tecnología | Justificación |
|---|---|---|
| Cola | Redis LIST `email:queue` | Simple, persistente, idempotente con `BLPOP` |
| Worker | Arq 0.26 | Async nativo (mismo event loop que FastAPI), cron jobs built-in |
| Persistencia | Tabla `email_outbox` | Auditoría + retry, no se pierde nada |
| Plantilla | Jinja2 → HTML inline CSS | Mails clients exigen CSS inline |
| SMTP dev | Mailpit (`axllent/mailpit:latest`) | Cero config, UI web en `:8025` |
| SMTP prod | AWS SES / SendGrid / Mailgun | Credenciales en vault, puerto 587 STARTTLS |

### Flujo

```
1. API: POST /api/v1/ordenes-compra/{id}/enviar-correo
2. OrdenCompraService:
   a. Valida estado actual (Borrador → Enviado a Supervisor)
   b. Renderiza plantilla Jinja2 con datos de la OC
   c. INSERT en email_outbox (status='pending')
   d. LPUSH 'email:queue' con el outbox_id
3. Arq worker (proceso aparte):
   a. BLPOP 'email:queue'
   b. SELECT FOR UPDATE email_outbox WHERE id=? AND status='pending'
   c. Conecta SMTP, envía email
   d. UPDATE email_outbox SET status='sent', sent_at=now()
   e. Si falla: attempts++, status='pending' con backoff (3 reintentos)
   f. Si 3 fallos: status='failed', last_error=<msg>
```

## Consequences

### Positive

- **POS-001**: API responde en <100ms al bodeguero (no espera SMTP).
- **POS-002**: Garantía de entrega: `email_outbox` persiste hasta `status='sent'`.
- **POS-003**: Reintentos con backoff (3 intentos: 30s, 5min, 30min) absorben caídas transitorias.
- **POS-004**: Cron jobs Arq (mismo worker) soportan `ReplenishmentEvaluator` cada 5 min.
- **POS-005**: Logs JSON estructurados trazan cada email (entregado/fallido).
- **POS-006**: Métricas Prometheus de cola (`email_pending`, `email_sent_total`, `email_failed_total`).

### Negative

- **NEG-001**: Worker es un proceso adicional a monitorear (Docker compose añade `worker` service).
- **NEG-002**: Arq tiene comunidad más pequeña que Celery; menor cantidad de integraciones.
- **NEG-003**: Latencia SMTP de hasta 30s se ve reflejada en la métrica `email_send_duration_seconds`.
- **NEG-004**: Requiere Redis activo (ya provisionado en compose).

## Alternatives Considered

### Celery + Redis

- **ALT-001**: **Description**: Stack maduro, dashboards built-in (Flower).
- **ALT-002**: **Rejection Reason**: Sin async nativo, complejidad operacional alta, overkill para 1 cola SMTP.

### RQ (Redis Queue)

- **ALT-003**: **Description**: Más simple que Celery, integrable con FastAPI.
- **ALT-004**: **Rejection Reason**: Sin scheduling nativo para jobs recurrentes (replenishment).

### FastAPI BackgroundTasks

- **ALT-005**: **Description**: Cero infra adicional.
- **ALT-006**: **Rejection Reason**: Tareas mueren con el proceso, sin retry, sin persistencia — no apto para SMTP crítico.

### SMTP síncrono en la API

- **ALT-007**: **Description**: `smtplib` directo en el endpoint.
- **ALT-008**: **Rejection Reason**: Bloquea la UI, latencia 5-30s, sin retry, pierde emails en restart.

## Implementation Notes

- **IMP-001**: Migración `0008_email_outbox.sql` con tabla `email_outbox (id, to_email, subject, body_html, status, attempts, last_error, sent_at, created_at)`.
- **IMP-002**: Nuevo módulo `apps/api/app/modules/notifications/` con:
  - `service.py` — `EmailOutboxService.enqueue()`
  - `worker.py` — Arq settings + funciones de tarea
  - `templates/orden_compra.html.j2` — plantilla Jinja2 responsiva
  - `smtp.py` — cliente SMTP async (aiosmtplib)
- **IMP-003**: Nuevo proceso `worker` en `infra/docker/docker-compose.yml`.
- **IMP-004**: Mailpit añadido a `compose.local.yml` y `compose.staging.yml`; NO en `production`.
- **IMP-005**: Variables de entorno nuevas: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS=true|false`.
- **IMP-006**: Healthcheck `/api/v1/health` verifica también Redis ping y worker liveness.
- **IMP-007**: Tests: 2 workers Arq contra la misma cola → verificar que ningún email se duplica (lock atómico en `email_outbox`).

## References

- **REF-001**: `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md` §8.3, §8.4
- **REF-002**: Spec del usuario (mensaje 2026-07-14) — sección 4.3 y regla de email
- **REF-003**: Arq docs — https://arq-docs.helpmanual.io/
- **REF-004**: aiosmtplib — https://aiosmtplib.readthedocs.io/
