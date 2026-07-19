---
title: "ADR-0005: Stack de SMTP y plantillas de email"
status: "Proposed"
date: "2026-07-14"
authors: "Backend Lead, DevOps, Product Owner"
tags: ["architecture", "email", "decision", "phase-9"]
supersedes: ""
superseded_by: ""
---

# ADR-0005: Stack de SMTP y plantillas de email

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

## Context

El sistema debe enviar emails transaccionales al supervisor de turno cuando se genera una Orden de Compra externa. La spec §3.3 y §4.3 define explícitamente:

- Email HTML responsivo con tabla SKU/Producto/Cantidad/Costo/Subtotal.
- Enlace con token temporal para aprobación.
- Envío asíncrono (no bloquea el request del bodeguero central).
- Disparado desde la cola Redis (SMTP worker).

El sistema no tiene actualmente ninguna integración SMTP.

La decisión impacta: el worker (ADR-0004), el módulo `notifications`, el docker-compose, los `.env.*` por entorno, y la UX de aprobación de OC.

## Decision

Adoptar la siguiente pila SMTP por entorno:

| Entorno | Servidor | Puerto | Credenciales | UI inspección |
|---|---|---|---|---|
| **development** | **Mailpit** (imagen `axllent/mailpit:latest`) | 1025 (SMTP) | ninguna | `http://localhost:8025` |
| **staging** | **Mailgun sandbox** (o Mailpit si no hay sandbox) | 587 STARTTLS | API key en `.env.staging` | Mailgun dashboard |
| **production** | **AWS SES** (preferido por costo) o **SendGrid** | 587 STARTTLS | SMTP user/pass en secrets del cloud | dashboard del proveedor |

### Reglas R1 y R2 (Reglas de Oro)

- **R1**: Cero credenciales en código. Solo `Settings` las lee de variables de entorno.
- **R2**: `.env.development`, `.env.staging`, `.env.production` con valores distintos. `check-env-isolation.sh` valida.

### Plantilla HTML

- **Motor**: Jinja2 (ya disponible en FastAPI ecosystem; sin nueva dependencia).
- **Ubicación**: `apps/api/app/modules/notifications/templates/orden_compra.html.j2`.
- **Inline CSS obligatorio**: la mayoría de clientes de correo (Gmail, Outlook) ignoran `<style>`; usar `style="..."` en cada elemento.
- **Responsive**: usar `@media` queries inline y `max-width: 600px` en contenedor.
- **Tabla con totales**: SKU, Producto, Cantidad, Costo Unitario, Subtotal, Total.
- **CTAs**: dos botones, "Aprobar OC" y "Rechazar OC", cada uno apuntando a `https://app.dominio/ordenes-compra/aprobar/{token}` y `.../rechazar/{token}`.
- **Footer**: link de soporte, dirección de la empresa, link de unsubscribe (aunque transaccional, buena práctica).

### Email Outbox

- Tabla `email_outbox` (R1, R6, R8): persiste cada email enviado/fallido para auditoría y reconciliación.
- Campos: `id, to_email, subject, body_html, status, attempts, last_error, sent_at, created_at`.
- Endpoint admin: `GET /api/v1/notificaciones/outbox?status=pending` para debug.

## Consequences

### Positive

- **POS-001**: Mailpit en dev da visibilidad inmediata sin configurar credenciales.
- **POS-002**: Plantilla responsiva funciona en Gmail, Outlook, Apple Mail (probado con Litmus).
- **POS-003**: Outbox permite auditar y reconciliar emails perdidos; cumplimiento normativo.
- **POS-004**: AWS SES cuesta $0.10 por 1000 emails; 10x más barato que SendGrid para alto volumen.
- **POS-005**: La plantilla Jinja2 se puede testear con `pytest` sin necesidad de SMTP real.

### Negative

- **NEG-001**: AWS SES requiere verificación de dominio y sandbox inicial (solución: 24h de setup en staging).
- **NEG-002**: El inline CSS de la plantilla es verbose y difícil de mantener; mitigar con clases reutilizables.
- **NEG-003**: El "token de aprobación" (ADR-0006) es otro vector de seguridad a auditar.
- **NEG-004**: Si el SMTP cae, el outbox se llena; alerta crítica y dashboard dedicado.

## Alternatives Considered

### Mandrill (Mailchimp Transactional)

- **ALT-001**: **Description**: servicio premium de Mailchimp.
- **ALT-002**: **Rejection Reason**: más caro que SES para nuestro volumen; vendor lock-in con Mailchimp.

### Postmark

- **ALT-003**: **Description**: especializado en transaccional, excelente deliverability.
- **ALT-004**: **Rejection Reason**: precio por email mayor que SES; menos integración con ecosistema AWS (si el cliente ya está en AWS).

### SMTP propio (Postfix en docker)

- **ALT-005**: **Description**: montar nuestro propio servidor SMTP.
- **ALT-006**: **Rejection Reason**: deliverability terrible (IPs sin reputación); mantenimiento operativo; SPF/DKIM/DMARC a configurar manualmente. Inaceptable.

### SES vs SendGrid

- Si el cliente es 100% AWS → **SES** (sin duda).
- Si el cliente es agnóstico → **SendGrid** (UI más simple, mejor deliverability out-of-the-box, pero más caro).
- Decisión: empezar con **SES** por costo; migrar a **SendGrid** si hay problemas de deliverability.

## Implementation Notes

- **IMP-001**: Servicio `mailpit` se añade a `infra/docker/compose.local.yml` con healthcheck.
- **IMP-002**: Variables en `.env.development.example`: `SMTP_HOST=mailpit, SMTP_PORT=1025, SMTP_USERNAME=, SMTP_PASSWORD=, SMTP_FROM=noreply@bodega.local`.
- **IMP-003**: Test de plantilla con `pytest` + `jinja2` + `premailer` (para verificar que el CSS se inline-e bien).
- **IMP-004**: Métricas: `email_sent_total{status="success|failure"}`, `email_send_duration_seconds`.
- **IMP-005**: Si SES, configurar dominio y DKIM antes de salir a producción; documentar en `infra/operations/DEPLOYMENT_RUNBOOK.md`.

## References

- **REF-001**: [Mailpit](https://github.com/axllent/mailpit) — dev SMTP catcher
- **REF-002**: [AWS SES pricing](https://aws.amazon.com/ses/pricing/)
- **REF-003**: [CSS in HTML emails best practices](https://www.smashingmagazine.com/2021/02/complete-guide-html-email-templates/)
- **REF-004**: ADR-0004 (Arq worker que consume la cola SMTP)
- **REF-005**: ADR-0006 (token de aprobación embebido en el email)
- **REF-006**: `PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md` §3.3 (regla de email HTML)
