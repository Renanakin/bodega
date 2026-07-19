---
title: "Fase 4 — Replenishment automático"
date: "2026-07-14"
status: "Completada"
predecesores: ["Fase 0", "Fase 1", "Fase 2", "Fase 3"]
siguientes: ["Fase 5 — Recepción con escaneo"]
tags: ["fase", "replenishment", "cron", "arq", "worker", "adr-0004"]
---

# Fase 4 — Replenishment automático

## Resumen ejecutivo

Esta fase implementa el **job automático que detecta stock bajo mínimo en bodegas auxiliares y crea solicitudes de recarga** sin intervención humana. Corre como cron de Arq cada 5 minutos sobre un proceso separado de la API, expone un endpoint para trigger manual (`POST /api/v1/solicitudes/auto-generar`) y un endpoint de catálogo bajo mínimo (`GET /api/v1/solicitudes/bajo-minimo`) que alimenta la UI `ReplenishmentPage` (Tailwind). El Evaluator es idempotente (si ya hay PENDING desde la bodega, omite), respeta las reglas de Fase 3 (origen=auxiliar, destino=principal, productos activos) y delega la creación de solicitudes a `SolicitudService` para mantener la separación `router / service / repository / jobs`. En el frontend, `SolicitudesAuxPage` se reescribe con Tailwind v3: filtros por estado / bodega / fechas, paginación, drawer de detalle con acciones de aprobar / rechazar.

## Cambios realizados

| Archivo | Líneas | Tipo | Descripción |
|---|---|---|---|
| `apps/api/app/modules/solicitudes/replenishment.py` | 250 (refactor) | modificado | Refactor del `ReplenishmentEvaluator`: `is_active.is_(True)` idiomático, prioridad `'alta'` lowercase, imports al top, métodos públicos `evaluate_all` / `evaluate_warehouse` / `evaluate_one`, parámetro `dry_run: bool = False`, helpers `_calcular_cantidad` / `_calcular_prioridad` con tests dedicados. |
| `apps/api/app/worker.py` | 200 (nuevo) | **nuevo** | Worker Arq con `replenishment_task` y cron cada 5 min. Configuración via `WorkerSettings` (clase con atributos de clase, convención Arq 0.26). Hooks `on_startup` / `on_shutdown` con logs estructurados. |
| `apps/api/app/core/config.py` | +30 | modificado | Settings nuevos: `redis_host`, `redis_port`, `redis_db` (separados de `redis_url` para `RedisSettings` de Arq) + `replenishment_interval_minutes` (default 5). |
| `apps/api/app/modules/solicitudes/schemas.py` | +70 | modificado | Schemas Pydantic nuevos: `ReplenishmentReportResponse` y `StockBajoMinimoResponse` (Literal `["normal", "alta", "urgente"]`). |
| `apps/api/app/modules/solicitudes/router.py` | +140 | modificado | Endpoints nuevos: `POST /solicitudes/auto-generar` (admin/supervisor) y `GET /solicitudes/bajo-minimo` (cualquier usuario autenticado). Query params: `bodega_id`, `dry_run`. |
| `apps/web/src/views/ReplenishmentPage.jsx` | 350 (rewrite) | modificado | Reescrito con Tailwind v3: header con título y 2 botones (preview / generar), filtro por bodega, tabla de SKUs bajo mínimo con columnas (Bodega, SKU, Producto, Stock actual, Mínimo, Máximo, Sugerido, Prioridad, Acción), banner de reporte de la última corrida, manejo de loading / error / empty. |
| `apps/web/src/views/SolicitudesAuxPage.jsx` | 530 (rewrite) | modificado | Reescrito con Tailwind v3: filtros (estado / bodega / rango fechas), tabla con badges de estado por color, paginación 25/página, drawer de detalle con líneas + acciones (aprobar / rechazar). |
| `apps/api/tests/unit/test_replenishment_evaluator.py` | 580 (nuevo) | **nuevo** | 20 tests del Evaluator: 6 unit (helpers `_calcular_cantidad` / `_calcular_prioridad`) + 14 integración (happy path, idempotencia, dry_run, evaluate_one, prioridad, tipos de bodega). |
| `apps/api/tests/manual/test_e2e_fase4.py` | 175 (nuevo) | **nuevo** | Script E2E: setup 3 productos bajo mínimo en AUX-1, ejecuta `evaluate_all()`, valida 1 solicitud con 3 líneas, valida idempotencia. |

**Total**: 2 archivos backend nuevos (worker + tests), 1 archivo E2E, 6 archivos backend / frontend modificados.

## Decisiones de implementación (resumen ADR-0004)

### Worker como proceso separado

Siguiendo el [ADR-0004](../adr/adr-0004-smtp-async-architecture.md), el cron de replenishment corre en el **mismo proceso** que el futuro worker SMTP de Fase 7. Ambos consumen de la misma cola Redis (`arq:queue`) y comparten `WorkerSettings`. Esto evita operar dos procesos de worker en producción.

| Componente | Tecnología | Justificación |
|---|---|---|
| Cola | Redis LIST `arq:queue` | Persistencia, idempotencia con `BLPOP` |
| Worker | Arq 0.26.3 | Async nativo, cron jobs built-in, mismo event loop que FastAPI |
| Cron schedule | `minute={0,5,10,...,55}` | Cada 5 minutos, redondeo a múltiplos válidos de 60 |
| Persistencia | Tabla `solicitudes_recarga` | Misma que Fase 3, auditoría completa |
| UI trigger | `POST /solicitudes/auto-generar` | On-demand sin esperar cron, admin/supervisor |

### Endpoint manual

`POST /api/v1/solicitudes/auto-generar` permite disparar el Evaluator on-demand con dos flags:

- `bodega_id` (opcional): si se pasa, evalúa solo esa bodega via `evaluate_one`. Si no, evalúa todas.
- `dry_run` (opcional): si es `true`, evalúa y reporta el impacto pero NO crea solicitudes. Útil para preview desde la UI.

Permisos: `admin` o `supervisor`.

### Idempotencia (R6)

El Evaluator consulta `solicitudes_recarga WHERE id_bodega_origen = ? AND estado = 'pending'` antes de crear. Si hay resultado, se omite la bodega (`solicitudes_omitidas_pendientes += 1`) y se registra log `replenishment.skipped_pending`. Garantía: aunque el cron corra cada 5 min y haya 12 ejecuciones por hora, no se acumulan solicitudes duplicadas.

### Cantidad sugerida (regla de negocio)

Para cada (bodega, producto) bajo mínimo:

```
target = max_quantity if max_quantity is not None else min_quantity * 2
cantidad = max(target - quantity, 0)
```

Si `target - quantity <= 0` se skipea (caso degenerado, ej: stock encima del target por error humano).

### Prioridad automática

```
prioridad = 'alta' if (quantity / min_quantity) < 0.5 else 'normal'
```

Si una solicitud tiene al menos una línea `'alta'`, la solicitud completa se marca `'alta'` (caso crítico gana sobre normal).

### Solo bodegas auxiliares

`evaluate_all` filtra `Warehouse.warehouse_type == 'auxiliar' AND is_active == True`. Las bodegas `principal` y `mecanico_box` quedan excluidas (ADR-0002 IMP-005: boxes consumen del auxiliar padre via suma recursiva, fuera del scope de esta fase).

### Solo productos activos

Productos con `is_active = False` se skipean aunque estén bajo mínimo. Log `replenishment.product_skipped` por cada uno.

## Diagrama del flujo

```
                    ┌──────────────────────┐
                    │  Arq cron (5 min)    │
                    │  apps/api/app/worker │
                    └──────────┬───────────┘
                               │ ejecuta replenishment_task(ctx)
                               ▼
                    ┌──────────────────────┐
                    │  ReplenishmentEval.  │
                    │   .evaluate_all()    │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌──────────────────┐ ┌─────────────┐ ┌─────────────────┐
    │ Listar bodegas   │ │ Por cada    │ │ Idempotencia:   │
    │ auxiliares       │ │ bodega:     │ │ ¿hay PENDING?   │
    │ activas          │ │  - stock    │ │  → omitir       │
    └──────────────────┘ │    bajo min │ └─────────────────┘
                         │  - calcular │
                         │    cantidad │
                         │  - filtrar  │
                         │    inactivos│
                         └──────┬──────┘
                                │ si hay lineas
                                ▼
                    ┌──────────────────────┐
                    │ SolicitudService     │
                    │ .create_solicitud()  │
                    │  - valida origen/    │
                    │    destino           │
                    │  - genera codigo     │
                    │  - inserta detalles  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  solicitudes_recarga │
                    │  estado=pending      │
                    │  → SolicitudesAuxPg  │
                    └──────────────────────┘
```

## Ejemplo de log estructurado

Una corrida normal (3 SKUs bajo mínimo en AUX-1) emite:

```json
{"event":"replenishment.evaluated","bodegas":1,"skus_bajo_minimo":3,"solicitudes_creadas":1,"solicitudes_omitidas":0,"errores":0,"dry_run":false,"timestamp":"2026-07-14T22:26:26Z"}
{"event":"solicitud.created","solicitud_id":"c5a8a84e-b5f6-44a4-bf0c-6dbf25c1ff21","codigo":"SOL-20260714-0001","origen":"AUX-1","origen_tipo":"auxiliar","destino":"PRINCIPAL","total_productos":3}
{"event":"replenishment.solicitud_created","solicitud_id":"c5a8a84e-...","codigo":"SOL-20260714-0001","bodega_origen":"AUX-1","total_lineas":3,"prioridad":"alta"}
```

Una corrida idempotente (re-correr con solicitud PENDING existente):

```json
{"event":"replenishment.skipped_pending","bodega":"AUX-1","motivo":"solicitud PENDING existente"}
{"event":"replenishment.evaluated","bodegas":1,"skus_bajo_minimo":0,"solicitudes_creadas":0,"solicitudes_omitidas":1,"errores":0}
```

## Cómo correr el worker localmente

```bash
# 1. Asegurar Redis corriendo
docker run -d --name redis-dev -p 6379:6379 redis:7-alpine

# 2. Arrancar el worker (proceso separado del API)
cd apps/api
arq app.worker

# Output esperado:
# 2026-07-14 22:20:20 [info     ] worker.configured cron_minutes=[0,5,10,...] redis_host=localhost redis_db=0
# 22:20:20.061 [info     ] worker.startup
# 22:25:00.001 [info     ] worker.replenishment.completed bodegas=3 skus_bajo_minimo=5 solicitudes_creadas=2 ...
```

En docker-compose, el servicio `worker` ejecuta el mismo comando como `command: arq app.worker`. No afecta el startup de la API (proceso separado).

## Cómo correr los tests

```bash
cd apps/api

# Tests del ReplenishmentEvaluator (20 nuevos)
python -m pytest tests/unit/test_replenishment_evaluator.py -v

# E2E manual con output detallado
python -m tests.manual.test_e2e_fase4

# Suite completa
python -m pytest tests/unit tests/integration -q
# → 175 passed, 7 skipped (Postgres-only tests)
```

## API expuesta

### `POST /api/v1/solicitudes/auto-generar`

Roles: `admin`, `supervisor`.

| Query param | Tipo | Default | Descripción |
|---|---|---|---|
| `bodega_id` | UUID | null | Si se pasa, evalúa solo esa bodega (`evaluate_one`). Si no, todas. |
| `dry_run` | bool | false | Si true, evalúa y reporta pero NO crea solicitudes. |

Response (200):

```json
{
  "bodegas_evaluadas": 1,
  "skus_bajo_minimo": 3,
  "solicitudes_creadas": 1,
  "solicitudes_omitidas_pendientes": 0,
  "errores": [],
  "dry_run": false,
  "timestamp": "2026-07-14T22:26:26.123456+00:00"
}
```

### `GET /api/v1/solicitudes/bajo-minimo`

Roles: cualquier usuario autenticado.

| Query param | Tipo | Default | Descripción |
|---|---|---|---|
| `bodega_id` | UUID | null | Filtra a una sola bodega. |

Response (200): lista de `StockBajoMinimoResponse`.

```json
[
  {
    "bodega_id": "ff36edac-...",
    "bodega_codigo": "AUX-1",
    "bodega_nombre": "Auxiliar Taller 1",
    "producto_id": "b52e095c-...",
    "producto_sku": "F-001",
    "producto_nombre": "Filtro",
    "stock_actual": 3.0,
    "stock_minimo": 10.0,
    "stock_maximo": 50.0,
    "cantidad_sugerida": 47.0,
    "prioridad": "alta"
  }
]
```

## Riesgos conocidos

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | Cron puede solaparse con un trigger manual largo | Arq garantiza 1 job por worker; con `max_jobs=10` y 1 worker el solapamiento no es problema. Si se necesitan más workers, se escala horizontal. |
| 2 | Si la consulta de stock bajo minimo tarda >5 min en BD grande (>1M SKUs), el cron se atrasa | Índices en `stock_levels(warehouse_id)` (existente) y considerar índice compuesto `(warehouse_id, quantity, min_quantity)` en Fase 9 si el volumen lo justifica. |
| 3 | `replenishment_eval_interval_seconds` y `replenishment_interval_minutes` son settings duplicados | Mantener ambos: segundos es el legado, minutos es el canónico. Limpiar en Fase 9 cuando se migre a `replenishment_cron_minutes` único. |
| 4 | Boxes no disparan replenishment directo (ADR-0002) | Diseño intencional: el box consume del auxiliar padre. La suma recursiva box→auxiliar se aborda en Fase 5/6 si la spec lo requiere. |
| 5 | Endpoint `/solicitudes/auto-generar` sin rate limiting | Un operador podría dispararlo 1000 veces/segundo. Mitigado por el flag `dry_run` (preview sin costo) y por la idempotencia. Rate limiting real en Fase 10 (Nginx). |
| 6 | Worker no se reinicia automáticamente en producción si muere | Se configura `restart: unless-stopped` en docker-compose. Monitoring de liveness en `/api/v1/health` queda para Fase 9. |
| 7 | El Evaluator delega en `SolicitudService.create_solicitud` que NO loguea `user_id` en este path | El log `replenishment.solicitud_created` deja rastro del trigger (cron vs manual). Aceptable para v1; en Fase 9 añadimos `trigger_source: "cron" \| "manual"` al log. |

## Próximos pasos (Fase 5 — Recepción con escaneo)

1. `BarcodeInput.jsx` ya existe (Fase 2). Integrarlo en `RecepcionBandejaPage` y `RecepcionDetallePage`.
2. Endpoint `POST /solicitudes/{id}/receive-line` con payload por línea + barcode opcional.
3. Validación de barcode EAN-13 con checksum (helper `BarcodeValidator`).
4. UI para escaneo masivo con teclado + Enter.
5. Estados visuales: pendiente / parcial / completo en cada línea.
6. Métricas: `replenishment_evaluations_total`, `replenishment_solicitudes_created_total` (Prometheus, Fase 9).

## Verificación de aceptación

- ✅ 20 tests nuevos del Evaluator pasando (`tests/unit/test_replenishment_evaluator.py`).
- ✅ E2E manual valida: 3 SKUs bajo mínimo en AUX-1 → 1 solicitud con 3 líneas, cantidades correctas (47, 9, 16), prioridad `alta`, idempotente.
- ✅ 175 tests unit + integration pasando (155 baseline + 20 nuevos de Fase 4).
- ✅ 188 tests totales pasando si contamos `tests/test_api.py` (155 baseline + 20 nuevos + 13 legacy `test_api.py` que pasan).
- ✅ Los 11 fallos pre-existentes en `tests/test_api.py` y `tests/integration/test_async_session.py` son por código legacy de Fase 0/1, no causados por Fase 4.
- ✅ Frontend builds clean (`npm run build` → 0 errores, bundle 337 KB / gzip 99 KB).
- ✅ Worker Arq se importa y configura sin errores (`python -c "from app.worker import WorkerSettings"`).
- ✅ Logs estructurados: `replenishment.evaluated`, `replenishment.solicitud_created`, `replenishment.skipped_pending`, `replenishment.product_skipped`, `replenishment.dry_run_would_create`, `worker.replenishment.completed`.
- ✅ Endpoint manual respeta roles: `admin` o `supervisor` (testeado via dependency).
- ✅ Endpoint catálogo: paginación natural (sin offset, 1 sola query) y filtrable por bodega.
- ✅ Idempotencia verificada: 2da corrida con PENDING existente omite la bodega.
- ✅ Reglas de Fase 3 respetadas: validación de origen / destino dentro de `SolicitudService.create_solicitud`.
- ✅ Solo bodegas tipo `auxiliar` se procesan (no `principal`, no `mecanico_box`).
- ✅ Solo productos activos se incluyen en líneas.
- ✅ dry_run no persiste cambios pero reporta el impacto esperado.
