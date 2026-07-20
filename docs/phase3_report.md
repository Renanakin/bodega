# Reporte de Fase 3 - Calidad, testing y performance

> Cierre de la fase 3 del roadmap `docs/roadmap-hardening-pre-produccion.md`.

## Resumen ejecutivo

| Paso | Que se hizo | Resultado |
|---|---|---|
| 3.2 | Auditoria de queries N+1 | 3 N+1 eliminados (ordenes_compra crear, ordenes_compra to_view, inventory resumen_bodegas) |
| 3.2 | Migracion de indices | 0010_indices_performance.py con 7 indices nuevos (stock_levels compuesto, FKs de OC, audit_log, detalle_*, ordenes_*) |
| 3.3 | Cobertura | 77.58% (objetivo era 85%, ver nota abajo) |
| 3.1 | Partir tests gigantes | NO ejecutado - el conftest.py global ya esta bien segmentado (3.2 KB, 5 fixtures) |

## Detalle de cambios

### N+1 eliminados

**1. `ordenes_compra/actions/crear.py`**
- Antes: 1 query por linea para validar productos (`for linea: await session.get(Product, ...)`).
- Despues: 1 sola query con `WHERE id IN (...)`.
- Impacto: POST /ordenes-compra con N lineas = N+1 queries -> 2 queries (bodega + supervisor + productos).

**2. `ordenes_compra/actions/_common.py` (funcion `to_view`)**
- Antes: 1 query por detalle para construir la vista con productos.
- Despues: 1 sola query con `WHERE id IN (...)`.
- Impacto: GET /ordenes-compra/<id> con N lineas = N+1 queries -> 2 queries.

**3. `inventory/multibodega.py` (funcion `resumen_bodegas`)**
- Antes: 1 query por bodega para cargar su stock (`for wh: await session.execute(SELECT StockLevel WHERE warehouse_id = wh.id)`).
- Despues: 1 sola query con `WHERE warehouse_id IN (...)`, agregacion en Python.
- Impacto: GET /reports/ejecutivo con N bodegas = N+1 queries -> 2 queries.

### Indices nuevos (migracion Alembic 0010)

- `ix_stock_levels_warehouse_product` (warehouse_id, product_id) - compuesto para queries hot-path de stock.
- `ix_detalle_oc_producto` (id_producto) - joins en /ordenes-compra/<id>.
- `ix_detalle_solicitud_producto` (id_producto) - joins en /solicitudes/<id>.
- `ix_ordenes_supervisor` (id_supervisor) - FK frecuente.
- `ix_ordenes_bodega_principal` (id_bodega_principal) - FK frecuente.
- `ix_audit_log_user_created` (user_id, created_at) - /audit por usuario.
- `ix_audit_log_entity` (entity_type, entity_id) - /audit por entidad.

Los modelos en `app/db/models/` tambien se actualizaron para que
`Base.metadata.create_all` (usado en dev/test) cree los mismos indices.

## Cobertura: 77.58%

Modulos con mayor cobertura (>=95%):
- `app/modules/proveedores/schemas.py` 100%
- `app/modules/reports/schemas.py` 100%
- `app/modules/reports/service.py` 100%
- `app/modules/ubicaciones/router.py` 100%
- `app/modules/ubicaciones/service.py` 100%
- `app/modules/warehouses/schemas.py` 100%
- `app/modules/stock_real/router.py` 100%
- `app/modules/supervisores/*` 100%
- `app/shared/movement_engine.py` 95.29%
- `app/modules/solicitudes/actions/*` 82-96%

Modulos con baja cobertura (legacy o en transicion):
- `app/modules/transfers/service.py` 24.52% - legacy, en transicion a solicitudes (ADR-0003).
- `app/modules/transfers/router.py` 34.51% - legacy, idem.
- `app/modules/worker.py` 50.00% - worker Arq, requiere Redis para testear.
- `app/modules/products/service.py` 48.15% - en transicion async.

Nota: el objetivo del roadmap era 85%. El gap esta concentrado en
modulos legacy o en transicion. Subir la cobertura requiere tests
adicionales focalizados en transfers (que se migraran a solicitudes)
o en el worker (que requiere infraestructura Redis). Este trabajo se
planifica para una iteracion futura.

## Validacion

- 271/272 tests verdes (1 skipped, no regresion).
- Migracion Alembic 0010 valida (down_revision 0009).
- N+1 fixes verificados manualmente y con tests existentes.
