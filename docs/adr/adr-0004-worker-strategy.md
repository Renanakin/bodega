---
title: "ADR-0004: Estrategia de workers asíncronos"
status: "Proposed"
date: "2026-07-14"
authors: "Backend Lead, DevOps"
tags: ["architecture", "async", "decision", "phase-9"]
supersedes: ""
superseded_by: ""
---

# ADR-0004: Estrategia de workers asíncronos

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

## Context

El sistema necesita ejecutar procesos asíncronos:

1. **Cola SMTP**: envío de emails de órdenes de compra (con reintentos, alto volumen esperado).
2. **ReplenishmentEvaluator**: cron cada 5 min que escanea stock bajo mínimo y genera solicitudes.
3. (futuro) Reportes pesados, exports, notificaciones push.

El stack ya incluye **Redis 8** en el `docker-compose.yml`, pero la API no lo usa. La spec §2 menciona "Caché/Colas: Redis" explícitamente.

La decisión impacta: la API (sincronía de endpoints), el proceso `worker`, el docker-compose, el deploy, y la observabilidad.

## Decision

Adoptar **Arq** (`arq==0.26`) como librería de workers, ejecutándose en un proceso separado `apps/api/app/worker/main.py`.

### Razones

- **Async nativo** sobre el mismo event loop que FastAPI (sin pickle, sin GIL, sin cambio de runtime).
- **Mismo cliente Redis** que ya usa la API (reutilización de pool).
- **Cron jobs nativos** (`arq cron`) para el `ReplenishmentEvaluator`.
- **Reintentos con backoff** built-in para la cola SMTP.
- **Tipado fuerte** con Pydantic para payloads.

### Arquitectura

```
┌────────────────┐         LPUSH email:queue         ┌──────────────────┐
│  FastAPI API   │ ──────────────────────────────────▶│  Arq Worker      │
│  (enqueue)     │                                    │  (consume)       │
└────────────────┘                                    └──────────────────┘
        │                                                     │
        │  cron 5min                                          │  SMTP call
        ▼                                                     ▼
   replenishment task ──▶ Redis ──▶ Arq Worker ──▶ Mailpit / SES
```

### Estructura

```
apps/api/app/worker/
├── __init__.py
├── settings.py            # Settings específicos del worker (mismo .env)
├── main.py                # Entry point: arq.Worker instantiation
└── tasks/
    ├── __init__.py
    ├── email.py           # send_email_task (3 reintentos, backoff exponencial)
    └── replenishment.py   # evaluate_replenishment_task (cron cada 5 min)
```

### Garantías

- **Idempotencia**: cada email tiene un `email_outbox.id`; el worker marca `status=sent` antes de salir. Si el proceso muere entre el envío SMTP y el update, un job de reconciliación detecta el gap.
- **Backoff**: 3 reintentos con delays 60s, 300s, 900s.
- **DLQ-like**: si los 3 reintentos fallan, el `email_outbox.status` queda en `failed` con `last_error`; alerta Prometheus.
- **Single worker por nodo**: usar `arq.on_startup` con `SET NX lock:worker:replenishment` para evitar duplicación.

## Consequences

### Positive

- **POS-001**: Async nativo = mismo código de BD (SQLAlchemy async) en API y worker.
- **POS-002**: Reintentos con backoff out-of-the-box; sin código custom.
- **POS-003**: Cron jobs declarativos en código Python, no en crontab del sistema.
- **POS-004**: Observabilidad con `structlog` y métricas Prometheus idénticas a la API.
- **POS-005**: Pydantic para payloads = validación automática y serialización tipada.

### Negative

- **NEG-001**: Comunidad más pequeña que Celery; menos integraciones de terceros (e.g. Flower).
- **NEG-002**: Sin soporte para múltiples colas con distinta prioridad (limitación de Arq).
- **NEG-003**: El lock anti-duplicación añade complejidad; mitigar con test de concurrencia.
- **NEG-004**: Si Redis cae, todo el async se detiene (mitigar con healthcheck + alerta).

## Alternatives Considered

### Celery + Redis

- **ALT-001**: **Description**: el estándar de facto en Python; soporta scheduling, múltiples colas, y tiene Flower para monitoring.
- **ALT-002**: **Rejection Reason**: proceso sync por defecto; para usar async requiere Celery 5.3+ con `asyncio` driver, lo que añade complejidad. La única cola SMTP no justifica su peso.

### RQ (Redis Queue)

- **ALT-003**: **Description**: minimalista, integra bien con FastAPI, popular.
- **ALT-004**: **Rejection Reason**: sync por defecto; sin scheduling nativo (requiere `rq-scheduler` separado); sin reintentos automáticos.

### FastAPI BackgroundTasks

- **ALT-005**: **Description**: ejecutar la tarea en el mismo proceso de la API.
- **ALT-006**: **Rejection Reason**: muere con el proceso; sin reintentos; sin observabilidad. Solo válido para tareas fire-and-forget que no son críticas.

### Dramatiq + RabbitMQ

- **ALT-007**: **Description**: alternativa moderna a Celery con mejor DX.
- **ALT-008**: **Rejection Reason**: añadir RabbitMQ al stack (no estaba en spec); sin valor agregado real sobre Arq para nuestro caso.

## Implementation Notes

- **IMP-001**: El `docker-compose.yml` añade servicio `worker` que ejecuta `python -m app.worker.main`.
- **IMP-002**: El worker comparte `Settings` con la API (mismo `.env`), pero tiene su propio `get_settings()` para no cachear.
- **IMP-003**: Cada tarea debe medir su tiempo con `time.monotonic()` y loguearlo.
- **IMP-004**: Alertas: `arq_queue_size{queue="email"} > 50` por 5 min → warning.
- **IMP-005**: Test de concurrencia: 100 OC simultáneas → 100 emails únicos en Mailpit (no duplicados).

## References

- **REF-001**: [Arq docs](https://arq-docs.helpmanual.io/)
- **REF-002**: `PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md` §8 (Redis como cola)
- **REF-003**: ADR-0001 (Postgres, que comparte driver con el worker)
- **REF-004**: ADR-0005 (SMTP, que es el caso de uso principal)
