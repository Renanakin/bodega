# Guía de migración: `/transfers` → `/solicitudes`

> **Estado:** Esta guía documenta la migración del módulo `transfers`
> (1 producto por transferencia) a `solicitudes_recarga` (N productos
> por solicitud) según [ADR-0003](../adr/adr-0003-transfers-to-solicitudes.md).
>
> **C1.2 (cierre de producción):** todos los endpoints POST/PATCH/DELETE
> de `/api/v1/transfers` retornan **HTTP 410 Gone**. Solo los GETs
> históricos siguen funcionando para consulta, pero el frontend ya no
> los usa en flujos de escritura.

---

## 1. ¿Por qué migramos?

El modelo `transfers` (migración `0002_transfers_workflow.sql`) tenía una
limitación operacional: **una transferencia por producto**. Esto significaba
que para mover 3 productos entre dos bodegas había que crear 3 transfers
separadas. El nuevo modelo `solicitudes_recarga` permite **N productos por
solicitud**, con tabla hija `detalle_solicitud_recarga` con PK compuesta
`(id_solicitud, id_producto)`.

Adicionalmente, las reglas de negocio cambiaron:

- `transfers`: bidireccional entre cualquier bodega.
- `solicitudes_recarga`: **origen = auxiliar, destino = principal**
  (ADR-0002, "modelo de boxes").

---

## 2. Equivalencia de endpoints

| Acción | Endpoint viejo (deprecado) | Endpoint nuevo |
|---|---|---|
| Listar | `GET /api/v1/transfers` | `GET /api/v1/solicitudes` |
| Crear | `POST /api/v1/transfers` (410) | `POST /api/v1/solicitudes` |
| Aprobar | `POST /api/v1/transfers/{id}/approve` (410) | `POST /api/v1/solicitudes/{id}/approve` |
| Despachar | `POST /api/v1/transfers/{id}/dispatch` (410) | `POST /api/v1/solicitudes/{id}/dispatch` |
| Recibir | `POST /api/v1/transfers/{id}/receive` (410) | `POST /api/v1/solicitudes/{id}/receive` |
| Editar | `PATCH /api/v1/transfers/{id}` (410) | `PATCH /api/v1/solicitudes/{id}` (no soportado; cancelar + crear nueva) |
| Cancelar | `POST /api/v1/transfers/{id}/cancel` (410) | `POST /api/v1/solicitudes/{id}/cancel` |
| Eliminar | `DELETE /api/v1/transfers/{id}` (410) | No soportado; usar `cancel` |

---

## 3. Equivalencia de estados

| Estado `transfers` | Estado `solicitudes` | Notas |
|---|---|---|
| `requested` | `pending` | Renombrado |
| `approved` | `approved` | Mismo |
| `dispatched` | `in_transit` | Renombrado |
| `partially_received` | `partially_received` | Mismo |
| `received` | `received` | Mismo |
| `cancelled` | `cancelled` | Mismo; semántica de cancelación, no rechazo |
| – | `rejected` | **Nuevo**: rechazo del aprobador (no cancelación) |

---

## 4. Ejemplo: de transfer a solicitud

### Antes (1 producto)

```json
POST /api/v1/transfers
{
  "from_warehouse_id": "uuid-aux",
  "to_warehouse_id": "uuid-princ",
  "product_id": "uuid-aceite",
  "quantity": 50
}
```

### Ahora (N productos)

```json
POST /api/v1/solicitudes
{
  "id_bodega_origen": "uuid-aux",
  "id_bodega_destino": "uuid-princ",
  "prioridad": "normal",
  "lineas": [
    { "id_producto": "uuid-aceite",   "cantidad_solicitada": 50 },
    { "id_producto": "uuid-filtro",   "cantidad_solicitada": 12 },
    { "id_producto": "uuid-kit",      "cantidad_solicitada": 4 }
  ]
}
```

---

## 5. ¿Qué pasa con los datos existentes?

Los registros en la tabla `transfers` **se conservan** sin modificación.
Solo el router deja de aceptarlos para escritura. Esto significa:

- Los reportes históricos (CSV, dashboards viejos) siguen mostrando los
  transfers con sus códigos originales (`TRF-...`).
- Los nuevos movimientos se crean únicamente vía `solicitudes_recarga`.
- La batería E2E (`auditoria-fase5/bateria_e2e_demo.py`) valida 50/51
  pasos usando solo el flujo de solicitudes.

---

## 6. Plan de retiro del módulo

| Hito | Fecha objetivo | Acción |
|---|---|---|
| Soft-deprecate (warning header) | ya cerrado | Banner en `TransfersPage.jsx`, router retorna 410 |
| Frontend solo con `/solicitudes` | Q3 2026 | Ocultar `TransfersPage.jsx` del menú principal; mover a `/admin/historical` |
| Retiro de la tabla `transfers` | Q1 2027 (post go-live + 6 meses) | Migración que mueve datos a `solicitudes_recarga` históricas, drop table, drop módulo |

---

## 7. Verificación rápida

Para confirmar que tu entorno está actualizado:

```bash
# 1. Backend rechaza escritura
curl -X POST http://localhost:8000/api/v1/transfers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"from_warehouse_id":"x","to_warehouse_id":"y","product_id":"z","quantity":1}'
# → 410 Gone
# → body: {"detail": {"code": "transfers_deprecated", "migration_guide": "/api/v1/solicitudes"}}

# 2. Frontend muestra banner
# Abrir /transfers → debe verse el callout amarillo "DEPRECATED"

# 3. Batería E2E sigue verde
python auditoria-fase5/bateria_e2e_demo.py
# → 50/51 PASS
```

---

## 8. Referencias

- **ADR-0003**: [Migración de transfers a solicitudes_recarga](../adr/adr-0003-transfers-to-solicitudes.md)
- **ADR-0002**: [Modelo de boxes de mecánicos](../adr/adr-0002-boxes-modelo.md)
- **Fase 3 doc**: [`docs/fases/fase-3-solicitudes-n-productos.md`](../fases/fase-3-solicitudes-n-productos.md)
- **Tests E2E**: `apps/api/tests/integration/test_solicitudes.py`
