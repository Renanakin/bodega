---
title: "ADR-0003: Migración de transfers (1 producto) a solicitudes_recarga (N productos)"
status: "Accepted"
date: "2026-07-14"
authors: "Equipo Bodegaje"
tags: ["arquitectura", "migracion", "transferencias", "solicitudes"]
supersedes: ""
superseded_by: ""
---

# ADR-0003: Migración de transfers (1 producto) a solicitudes_recarga (N productos)

## Status

**Accepted** — Decisión ratificada para la Fase 3 del roadmap.

## Context

El modelo actual `transfers` (migración `0002_transfers_workflow.sql`) modela **una transferencia por producto** (`transfers.product_id`). La nueva spec exige `solicitudes_recarga` con **N productos** vía tabla hija `detalle_solicitud_recarga` con PK compuesta `(id_solicitud, id_producto)`.

Hay además cambios de namespace en los estados:

- Actual: `requested, approved, dispatched, partially_received, received, cancelled`
- Spec: `Pendiente, Aprobado, En Transito, Recibido, Rechazado`

Y una regla de validación asimétrica: **origen siempre Auxiliar, destino siempre Principal** (no bidireccional como hoy).

Estos cambios rompen el modelo de datos y la API actual. Se requiere una estrategia de migración **no destructiva** que no rompa el frontend existente mientras se adopta el nuevo modelo.

## Decision

Adoptar la estrategia de **convivencia con vista derivada durante 6 meses**:

1. **Crear** `solicitudes_recarga` + `detalle_solicitud_recarga` en paralelo a `transfers`.
2. **Implementar** `SolicitudService` reusando la lógica transaccional de `TransferService` (refactor previo: extraer a `MovementEngine` compartido).
3. **Crear** endpoint `GET /api/v1/transfers/{id}/derived` que arma una `Transfer` virtual agrupando por `solicitud_recarga` y leyendo el detalle.
4. **Migrar** datos demo (1 producto → 1 línea de solicitud).
5. **Feature flag** `USE_SOLICITUDES=true|false` (default `false` en Fase 3, `true` desde Fase 4).
6. **Marcar** `transfers` deprecated en doc; retirar a los 6 meses o cuando el frontend haya migrado (lo que ocurra primero).

### Namespace unificado de estados

| Estado actual | Estado nuevo | Mapeo |
|---|---|---|
| `requested` | `pending` | Renombrar |
| `approved` | `approved` | Mantener |
| `dispatched` | `in_transit` | Renombrar |
| `partially_received` | (parcial) `received` | Mantener semántica con flag |
| `received` | `received` | Mantener |
| `cancelled` | `rejected` | Renombrar semántica |
| – | `cancelled` | Nuevo: cancelación por el solicitante antes de aprobar |

## Consequences

### Positive

- **POS-001**: Frontend existente sigue funcionando durante la transición (vista derivada).
- **POS-002**: `MovementEngine` centraliza la lógica transaccional, evitando duplicación.
- **POS-003**: Reglas de validación se centralizan en un único service.
- **POS-004**: Tests E2E pueden ejercitar ambos caminos vía feature flag.
- **POS-005**: `inventory_movements` queda como ledger auditable único (no se duplica).

### Negative

- **NEG-001**: Mantener `transfers` durante 6 meses suma complejidad temporal.
- **NEG-002**: El mapeo de estados requiere cuidado para no romper reportes históricos.
- **NEG-003**: Seed debe generar ambos modelos hasta que `transfers` se retire.
- **NEG-004**: El job de replenishment debe operar contra `solicitudes`, no `transfers`.

## Alternatives Considered

### Retiro inmediato de `transfers`

- **ALT-001**: **Description**: Migrar de golpe, sin convivencia.
- **ALT-002**: **Rejection Reason**: Riesgo alto de romper frontend y reportes en producción; sin red de seguridad.

### Mantener `transfers` y agregar `solicitudes` como capa superior (sin deprecar)

- **ALT-003**: **Description**: Ambos modelos conviven indefinidamente.
- **ALT-004**: **Rejection Reason**: Costo de mantenimiento permanente, deuda técnica, dos mentalidades de modelo.

## Implementation Notes

- **IMP-001**: Migración `0007_solicitudes_recarga.sql` (crear tablas) + `0007_solicitudes_recarga_seed_migration.sql` (mover datos demo).
- **IMP-002**: `apps/api/app/modules/inventory/movement_engine.py` — extraer lógica transaccional común (DRY).
- **IMP-003**: `apps/api/app/modules/transfers/router.py` añade endpoint `/derived` que arma la vista.
- **IMP-004**: Feature flag `USE_SOLICITUDES` en `apps/api/app/core/config.py`; `SolicitudService` se activa cuando `true`.
- **IMP-005**: Docstring en `apps/api/app/modules/transfers/__init__.py` marca el módulo como `@deprecated` con plan de retiro.
- **IMP-006**: Cron mensual que alerte si quedan `transfers` no migrados a `solicitudes_recarga`.

## References

- **REF-001**: `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md` §4.1, §5
- **REF-002**: `db/migrations/0002_transfers_workflow.sql` (esquema actual a deprecar)
- **REF-003**: Spec del usuario (mensaje 2026-07-14) — sección 3 modelo de datos
