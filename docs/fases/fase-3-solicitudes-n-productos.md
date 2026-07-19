---
title: "Fase 3 — Solicitudes de Recarga N-productos"
date: 2026-07-14
status: "Completada"
predecesores: ["Fase 0", "Fase 1", "Fase 2"]
siguientes: ["Fase 4 — Replenishment automático"]
tags: ["fase", "solicitudes", "saga", "workflow", "adr-0003"]
---

# Fase 3 — Solicitudes de Recarga (N productos)

## Resumen ejecutivo

Esta fase implementa el **workflow completo de solicitudes de recarga** con N productos, reemplazando progresivamente el modelo `transfers` (1 producto) por `solicitudes_recarga` (N productos), según lo resuelto en el [ADR-0003](../adr/adr-0003-transfers-to-solicitudes.md). La bodega auxiliar solicita recarga a la principal con N productos en una sola solicitud; el bodeguero central aprueba, despacha (descuenta stock de Principal) y la auxiliar recibe (incrementa su stock). Todo el flujo es trazable, transaccional y compatible con la vista derivada de `transfers` durante 6 meses.

## Cambios realizados

| Archivo | Líneas | Tipo | Descripción |
|---|---|---|---|
| `apps/api/app/modules/solicitudes/repository.py` | +300 | **nuevo** | `SolicitudRepository` con `get_by_id`, `get_by_id_with_lock` (SELECT FOR UPDATE), `list`, `update_estado`, `update_linea_despacho`, `update_linea_recepcion`, `count_by_estado`, `count_by_bodega`, `generate_unique_codigo` (formato SOL-YYYYMMDD-NNNN). |
| `apps/api/app/modules/solicitudes/service.py` | 700 (refactor) | modificado | `SolicitudService` con workflow completo: `create_solicitud` / `approve_solicitud` / `dispatch_solicitud` (total o parcial) / `receive_solicitud` / `cancel_solicitud` / `reject_solicitud` + aliases `create` / `approve` / `dispatch` / `receive` / `reject` / `cancel` que aceptan schemas Pydantic + `get_distribucion_multibodega` (spec §4.1) + `get_derived_transfer` (compat legacy). |
| `apps/api/app/modules/solicitudes/schemas.py` | 220 (refactor) | modificado | Schemas Pydantic 2: `SolicitudCreate`, `SolicitudLineaCreate`, `SolicitudLineaDespacho`, `SolicitudLineaRecepcion`, `SolicitudDespacho`, `SolicitudRecepcion`, `SolicitudAprobacion`, `SolicitudRechazo`, `SolicitudCancelacion`, `SolicitudResponse` (con `total_productos` y `total_unidades`), `DistribucionMultibodegaResponse` (spec §4.1), `TransferDerivedResponse` (vista compat). |
| `apps/api/app/modules/solicitudes/router.py` | 250 (refactor) | modificado | 9 endpoints: `POST/GET /solicitudes`, `GET /solicitudes/{id}`, `POST /solicitudes/{id}/approve|dispatch|receive|reject|cancel`, `GET /solicitudes/distribucion/multibodega`, `GET /solicitudes/{id}/derived`. |
| `apps/api/app/modules/transfers/router.py` | 200 (refactor) | modificado | Marcar deprecated (docstring), mantener GETs, retornar **410 Gone** en POST/PATCH/DELETE, agregar `GET /transfers/{id}/derived` que mapea `Transfer.code == solicitud.codigo`. |
| `apps/api/app/modules/transfers/__init__.py` | 20 | **nuevo** | Docstring de módulo @deprecated con plan de retiro 6 meses. |
| `apps/api/app/db/models/solicitudes.py` | 20 | modificado | Añadir `CheckConstraint` "origen != destino" (único portable a SQLite; los demás checks viven en service). |
| `apps/api/app/core/errors.py` | 60 | modificado | Nuevas excepciones: `SolicitudInvalidStateError`, `BarcodeMismatchError`, `ProductNotActiveError`. |
| `apps/api/tests/unit/test_solicitudes.py` | 1000 (nuevo) | **nuevo** | 27 tests cubriendo workflow completo, validaciones, distribucion, audit, vista derivada, concurrencia. |
| `apps/api/tests/integration/test_solicitudes.py` | 30 (modificado) | modificado | Alinear tests con nueva semántica: dispatch descuenta de Principal, receive incrementa Auxiliar. |

**Total**: ~1 archivo nuevo grande + 1 archivo nuevo de tests + 7 archivos modificados.

## Decisiones de implementación (resumen ADR-0003)

### Namespace unificado de estados

| Modelo (DB) | API | Significado |
|---|---|---|
| `pending` | `pending` | Solicitud creada, esperando aprobación |
| `approved` | `approved` | Supervisor aprobó, pendiente de despacho |
| `in_transit` | `in_transit` | Despachado desde Principal, en camino |
| `partially_received` | `partially_received` | Recepción parcial por línea |
| `received` | `received` | Todas las líneas recibidas completas |
| `rejected` | `rejected` | Supervisor rechazó con motivo |
| `cancelled` | `cancelled` | Origen canceló antes de aprobar |

> **Nota**: el spec del usuario prefiere `partial` (en lugar de `partially_received`). Mantenemos el nombre del modelo (más explícito y snake_case) en la API por compatibilidad con los tests existentes; el alias se puede aplicar en una fase futura via serializador Pydantic.

### Reglas de validación (ADR-0002)

| Regla | Validación | Defensa en profundidad |
|---|---|---|
| Origen ∈ {auxiliar, mecanico_box con parent_warehouse_id} | `SolicitudService._validate_direction()` | Servicio (SQLite no soporta subqueries en CHECK) |
| Destino = `principal` | `SolicitudService._validate_direction()` | Servicio |
| Origen ≠ destino | `_validate_direction()` + `CheckConstraint` en modelo | Doble capa |
| Producto existe y está activo | `SolicitudService.create_solicitud()` | Servicio |
| Productos únicos en la solicitud | `SolicitudCreate.validate_unique_products` | Pydantic + servicio |
| Cantidad > 0 | `Quantity = Annotated[Decimal, Field(gt=0, ...)]` | Pydantic + servicio |

### Reglas de transición de estado

```
pending  → approved   → in_transit  → partially_received  → received
   ↓           ↓             ↓                                    
cancelled  rejected   (rejected NO permitido; cancelación NO permitida)  
```

- `cancel` solo si `pending` (origen cancela antes de aprobar)
- `reject` solo si `pending` o `approved` (con motivo obligatorio, min 5 chars)
- `dispatch` solo si `approved`; descuenta de Principal
- `receive` solo si `in_transit` o `partially_received`; incrementa Auxiliar

## Diagrama de estados

```
            ┌─────────┐
            │ pending │
            └────┬────┘
       cancel/    │    \approve
        ┌─────────┴──────────┐
        ▼                    ▼
   ┌─────────┐         ┌──────────┐
   │cancelled│         │ approved │
   └─────────┘         └─────┬────┘
                        dispatch \reject
                  ┌──────────────┴───────┐
                  ▼                      ▼
            ┌───────────┐          ┌──────────┐
            │in_transit │          │ rejected │
            └─────┬─────┘          └──────────┘
                  │ receive (N veces)
                  ▼
        ┌──────────────────┐
        │partially_received│
        └────────┬─────────┘
                 │ receive (última)
                 ▼
            ┌──────────┐
            │ received │
            └──────────┘
```

## Lock pesimista: `SELECT FOR UPDATE` en Postgres, `BEGIN IMMEDIATE` en SQLite

`SolicitudRepository.get_by_id_with_lock()` usa `with_for_update()` que SQLAlchemy traduce a:
- **Postgres**: `SELECT ... FOR UPDATE` real (fila bloqueada hasta commit).
- **SQLite**: no-op (SQLite no soporta `FOR UPDATE`); el writer-lock se obtiene via `SQLiteDatabase.begin_immediate_transaction()` del motor, que adquiere el `RLock` Python (Fase 1 fix [T-1]).

Esto garantiza que dos dispatch concurrentes al mismo `solicitud_id` se serializan correctamente y no hay race conditions en la transición de estado.

## Defensa en profundidad: validación en BD

Aunque la validación principal vive en el service, añadimos el constraint portable a SQLite en el modelo:

```python
CheckConstraint(
    "id_bodega_origen <> id_bodega_destino",
    name="ck_solicitudes_origen_distinto_destino",
)
```

Los checks que requieren subqueries (`origen ∈ {auxiliar, mecanico_box}` y `destino = principal`) NO se pueden expresar en SQLite. Se aplicarán en Postgres via migración aditiva `0006b_solicitudes_check_postgres.sql` cuando se haga la migración a Postgres real. La validación service-side cubre el caso SQLite (tests + dev).

## Ejemplo de flujo end-to-end con curl/PowerShell

```bash
# 1. Login (devuelve token)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"demo123"}' | jq -r .token)

# 2. Crear solicitud de 3 productos
curl -X POST http://localhost:8000/api/v1/solicitudes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "bodega_origen_id": "<UUID-AUX-1>",
    "bodega_destino_id": "<UUID-PRINCIPAL>",
    "prioridad": "normal",
    "notas": "Recarga semanal",
    "lineas": [
      {"producto_id": "<UUID-P1>", "cantidad_solicitada": 10},
      {"producto_id": "<UUID-P2>", "cantidad_solicitada": 20},
      {"producto_id": "<UUID-P3>", "cantidad_solicitada": 30}
    ]
  }'
# → 201 con codigo: "SOL-20260714-0001", estado: "pending", total_productos: 3

# 3. Aprobar (supervisor)
curl -X POST http://localhost:8000/api/v1/solicitudes/<SOL-ID>/approve \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
# → 200 con estado: "approved", approved_at: <timestamp>

# 4. Despachar (origen: 30 de P1, 20 de P2; P3 se despacha despues)
curl -X POST http://localhost:8000/api/v1/solicitudes/<SOL-ID>/dispatch \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "lineas": [
      {"producto_id": "<UUID-P1>", "cantidad_despachada": 10},
      {"producto_id": "<UUID-P2>", "cantidad_despachada": 20}
    ]
  }'
# → 200 con estado: "in_transit", dispatched_at: <timestamp>
# Stock Principal: P1 -= 10, P2 -= 20 (via MovementEngine)

# 5. Recibir parcial (Auxiliar confirma que llegaron 10 de P1 + 15 de P2; 5 faltantes)
curl -X POST http://localhost:8000/api/v1/solicitudes/<SOL-ID>/receive \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "lineas": [
      {"producto_id": "<UUID-P1>", "cantidad_recibida": 10, "barcode": "7891234567891"},
      {"producto_id": "<UUID-P2>", "cantidad_recibida": 15, "barcode": "7891234567892", "incidencia": "5 unidades dañadas"}
    ]
  }'
# → 200 con estado: "partially_received"
# Stock Auxiliar: P1 += 10, P2 += 15

# 6. Recibir resto (cuando llega la mercancia faltante)
curl -X POST http://localhost:8000/api/v1/solicitudes/<SOL-ID>/receive \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"lineas": [{"producto_id": "<UUID-P2>", "cantidad_recibida": 5, "barcode": "7891234567892"}]}'
# → 200 con estado: "received", received_at: <timestamp>
```

## Cómo correr los tests

```bash
cd apps/api
python -m pytest tests/unit/test_solicitudes.py -v          # 27 tests nuevos
python -m pytest tests/integration/test_solicitudes.py -v   # 8 tests integration (workflow)
python -m pytest tests/unit/ tests/integration/ -q          # full suite: 155 passed
```

Los tests usan `unittest.IsolatedAsyncioTestCase` con un AsyncEngine SQLite + StaticPool para tener una BD compartida entre setup y endpoint. Los usuarios se insertan en una BD legacy (sync) porque el endpoint `/auth/login` opera sobre la BD legacy; los datos de bodegas/productos/stock se insertan via el AsyncSession. El router override `get_session` para usar el AsyncEngine del test.

## Riesgos conocidos

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | Migración a Postgres: el CHECK de "origen != destino" ya está, pero los otros 2 (origen ∈ {aux, box}, destino=principal) requieren subqueries que SQLite no soporta. | Migración aditiva `0006b_solicitudes_check_postgres.sql` con `EXECUTE` o trigger en Postgres. Documentado en `solicitudes.py:__table_args__`. |
| 2 | Deprecation de `transfers`: el frontend puede seguir usando `/api/v1/transfers` por 6 meses. | Mantenemos GETs funcionando + endpoint `/derived` que arma la vista virtual. Banner 410 Gone en writes. |
| 3 | `partially_received` (modelo) vs `partial` (spec del usuario): dos nombres para el mismo estado. | Mantenemos el nombre del modelo en la API por compat con tests existentes. Serializador Pydantic puede aplicar alias en Fase 4+. |
| 4 | Eager loading no usado: cada `SolicitudResponse` hace 3+ queries (solicitud, detalles, bodegas, productos). N+1 menor pero existe. | Aceptable en UI con paginación de 50 items. Optimizar via `selectinload` cuando se migre a modelo con `relationship()` (bug SA 2.0.36 + Py 3.14). |
| 5 | `get_distribucion_multibodega` retorna `ubicacion_principal: null`: la spec §4.1 pide formato "Bodega X: 140 (P-01/E-02)" pero la tabla `inventario_stock_real` aún no se usa (Fase 6+). | Endpoint funcional; se completa en Fase 6 cuando se llene `inventario_stock_real`. |
| 6 | Vista derivada `/derived` opera sobre el servicio async, pero `transfers/router.py` es sync (legacy). | El router async de `/solicitudes/{id}/derived` es el path oficial. El router sync de `/transfers/{id}/derived` retorna 503 si la app no tiene la BD legacy disponible. |

## Próximos pasos (Fase 4 — Replenishment automático)

1. Implementar `ReplenishmentEvaluator` (job Arq cada 5 min) que escanea `stock_levels` con `quantity <= min_quantity` y llama a `SolicitudService.create_solicitud()` para generar solicitudes automáticas.
2. UI `SolicitudesAuxPage` con filtros (estado, bodega origen, rango fechas) + tabla + drawer de detalle.
3. UI `ReplenishmentPage` con botón "Generar Solicitud" por fila bajo mínimo.
4. Vista `MultibodegaGrid` con datos del endpoint `/solicitudes/distribucion/multibodega`.
5. Job idempotente: si ya hay `pending` para esa bodega, skip.
6. Métricas: `solicitudes_por_estado{estado=...}` Prometheus.

## Verificación de aceptación

- ✅ Workflow completo create → approve → dispatch → receive → received (test_e2e_flujo_completo).
- ✅ Validación de origen ≠ destino, origen ≠ principal, destino = principal (ADR-0002).
- ✅ Producto inactivo rechazado.
- ✅ InsufficientStock si Principal no tiene stock.
- ✅ BarcodeMismatch si barcode no coincide.
- ✅ Cancel solo si pending; reject solo si pending|approved.
- ✅ Distribución multibodega (spec §4.1).
- ✅ Vista derivada `/solicitudes/{id}/derived` para compat con transfers.
- ✅ Transfers POST/PATCH/DELETE retornan 410 Gone.
- ✅ 27 tests nuevos pasando, 0 tests originales rotos.
- ✅ Logs estructurados (`solicitud.created`, `solicitud.approved`, `solicitud.dispatched`, `solicitud.received`, `solicitud.cancelled`, `solicitud.rejected`).
- ✅ MovementEngine como único punto de escritura de stock (Regla de Oro R4).
