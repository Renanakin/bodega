---
title: "ADR-0002: Modelo de boxes de mecánicos"
status: "Accepted"
date: "2026-07-14"
authors: "Equipo Bodegaje"
tags: ["arquitectura", "dominio", "boxes", "multi-bodega"]
supersedes: ""
superseded_by: ""
---

# ADR-0002: Modelo de boxes de mecánicos

## Status

**Accepted** — Decisión ratificada para la Fase 2 del roadmap.

## Context

La spec del usuario (sección 1, diagrama) muestra tres capas físicas:

1. **Bodega Principal** (Central) — habla con proveedores externos
2. **3 Bodegas Auxiliares** (Taller 1, 2, 3) — se reabastecen de la Principal
3. **Boxes de mecánicos** — picking local desde cada Auxiliar para Órdenes de Trabajo (OTs)

El modelo de datos actual (`warehouses`) sólo tiene un `warehouse_type` libre (string). No existe ninguna entidad "box" ni se distingue entre bodegas que compran al exterior y las que no. La spec exige reglas de validación:

- Boxes **no generan** solicitudes de recarga
- Boxes **no aparecen** como origen en transferencias desde Central
- Stock por box **cuenta** para alertas de su auxiliar padre (suma recursiva)

Esto requiere extender el modelo de `warehouses` con semántica explícita.

## Decision

Adoptar la **Opción A**: los boxes de mecánicos se modelan como `warehouses` con `warehouse_type='mecanico_box'`, con `parent_warehouse_id` que apunta a la bodega auxiliar padre. Se amplía el CHECK constraint actual para incluir el nuevo tipo.

```sql
ALTER TABLE warehouses
    ADD COLUMN parent_warehouse_id UUID NULL REFERENCES warehouses(id);

ALTER TABLE warehouses
    DROP CONSTRAINT chk_warehouses_type_not_blank,
    ADD CONSTRAINT chk_warehouses_type_valid
    CHECK (warehouse_type IN ('principal', 'auxiliar', 'mecanico_box'));
```

### Reglas de validación

| Regla | Capa | Implementación |
|---|---|---|
| Boxes no generan solicitudes | API | `SolicitudService.create` rechaza si `id_bodega_origen` es box |
| Boxes no aparecen como destino desde Central | API + BD | BD: CHECK en `solicitudes_recarga`; API: validar antes de insertar |
| Stock box cuenta para alertas del auxiliar | Job | `ReplenishmentEvaluator` agrega recursivamente `parent_warehouse_id` |

## Consequences

### Positive

- **POS-001**: Cero migración nueva de entidades — se reutiliza `warehouses` y todo su slotting/transferencias.
- **POS-002**: Reglas de exclusión se concentran en el service, no en el modelo.
- **POS-003**: Slots físicos (`ubicaciones_estanteria`) se asignan a boxes sin modelo nuevo.
- **POS-004**: Queries de stock siguen funcionando con la misma cardinalidad.

### Negative

- **NEG-001**: `warehouses` se sobrecarga semánticamente (3 tipos en 1 tabla).
- **NEG-002**: Las reglas de exclusión deben repetirse en cada operación (no hay FK con lógica condicional).
- **NEG-003**: El agregado recursivo para alertas añade un JOIN extra en el job de replenishment.

## Alternatives Considered

### Opción B: Tabla propia `mecanico_boxes` con FK a `warehouses.id`

- **ALT-001**: **Description**: Crear tabla paralela con identidad propia.
- **ALT-002**: **Rejection Reason**: Doble modelo de stock, cardinalidad duplicada, queries de "stock multibodega" se duplican. Sólo útil si boxes tuvieran comportamiento muy distinto (no es el caso).

### Opción C: Boxes como `ubicaciones_estanteria` con marca "box"

- **ALT-003**: **Description**: Reutilizar la tabla de ubicaciones.
- **ALT-004**: **Rejection Reason**: Pierde identidad individual de mecánico, no permite picking por persona.

## Implementation Notes

- **IMP-001**: Migración `0004_warehouses_box_support.sql` (aditiva, `ADD COLUMN IF NOT EXISTS`).
- **IMP-002**: Validar `warehouse_type` server-side en `apps/api/app/modules/warehouses/service.py` con enum explícito.
- **IMP-003**: Endpoint `GET /api/v1/warehouses?type=mecanico_box` para que el frontend pueda listarlos.
- **IMP-004**: Seed inicial: 1 Principal, 3 Auxiliares, 6 Boxes (2 por auxiliar).
- **IMP-005**: `ReplenishmentEvaluator` en Fase 4 agrega stock recursivo: `parent_warehouse_id IS NULL` → principal; `parent_warehouse_id IS NOT NULL AND warehouse_type='mecanico_box'` → sumar al padre.

## References

- **REF-001**: `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md` §5.3
- **REF-002**: Spec del usuario (mensaje 2026-07-14) — diagrama de tres capas
