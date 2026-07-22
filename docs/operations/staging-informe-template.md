# Informe de Staging — Plantilla (C4.7)

> **Uso:** copiar este archivo a `staging-<FECHA>.md` (ej: `staging-2026-08-15.md`)
> y llenar las secciones después del período de prueba con el cliente piloto.

---

**Período de staging:** [FECHA_INICIO] → [FECHA_FIN]
**Cliente:** [NOMBRE_CLIENTE]
**Versión desplegada:** [vX.Y.Z-rcN]
**Stack:** Postgres 17 + Redis 8 + API FastAPI + React web

---

## TL;DR

| Métrica | Valor |
|---|---|
| Días de prueba | [N] |
| Usuarios invitados | [N] |
| Usuarios activos (>1 sesión) | [N] |
| Sesiones totales | [N] |
| Solicitudes creadas | [N] |
| Órdenes de compra creadas | [N] |
| Movimientos de stock | [N] |
| Bugs reportados | [N] |
| Bugs críticos (bloqueantes) | [N] |
| Bugs menores | [N] |
| Ideas de mejora | [N] |
| Decisión del cliente | [Continuar / Pausar / Abandonar] |

---

## Cobertura de los flujos críticos

| Flujo | Probado por el cliente | Comentarios |
|---|---|---|
| Login + dashboard | ✅ / ⚠️ / ❌ | |
| Crear bodega | | |
| Crear producto | | |
| Crear categoría | | |
| Movimientos de stock (in/out) | | |
| Solicitud de reposición (origen → principal) | | |
| Aprobar / despachar / recibir | | |
| Orden de compra | | |
| Aprobación de OC por email/token | | |
| Notificaciones in-app | | |
| Búsqueda por código de barras | | |
| Reportes / KPIs | | |
| Bajo-mínimo | | |

---

## Bugs encontrados

### 🔴 Críticos (bloqueantes)

| # | Título | Pasos para reproducir | Severidad | Estado |
|---|---|---|---|---|
| 1 | | | | |

### ⚠️ Menores (workaround existe)

| # | Título | Workaround | Estado |
|---|---|---|---|
| 1 | | | |

### 💡 Sugerencias de mejora

| # | Título | Impacto percibido | Dificultad estimada |
|---|---|---|---|
| 1 | | | |

---

## Métricas de sistema

### Disponibilidad

- **Uptime medido:** [N días, M horas]
- **Caídas no planeadas:** [N]
- **Caídas planeadas (deploys):** [N]

### Performance (vía Prometheus)

- **Latencia p50:** [X] ms
- **Latencia p95:** [X] ms
- **Latencia p99:** [X] ms
- **RPS máximo observado:** [X]
- **Tasa de error (5xx):** [X]%

### Alertas disparadas

| Alerta | Cuántas veces | Acción tomada |
|---|---|---|
| HighErrorRate | | |
| HighLatencyP95 | | |
| OutboxBacklog | | |
| DiskSpaceLow | | |
| MemoryHigh | | |
| PostgresConnectionsHigh | | |

---

## Feedback cualitativo del cliente

### Lo que más le gustó

> [Cita textual del cliente]

### Lo que más le molestó

> [Cita textual del cliente]

### Funcionalidades que pidió para fase 2

1. [Feature]
2. [Feature]
3. [Feature]

---

## Decisiones de producto post-staging

| Decisión | Responsable | Fecha límite |
|---|---|---|
| [Go / No-go a producción] | [nano] | [fecha] |
| [Fix de bug crítico #N] | [nano] | [fecha] |
| [Implementar feature X] | [nano] | [fecha] |

---

## Lecciones aprendidas

- [Lo que aprendimos sobre el sistema]
- [Lo que aprendimos sobre el cliente]
- [Lo que haríamos distinto la próxima vez]

---

## Anexo: logs relevantes

- Healthcheck: [link a Grafana]
- Logs de staging: [comando docker logs]
- Reporte de load test: [adjuntar]

---

**Aprobado por:** [nombre]
**Fecha:** [fecha]
