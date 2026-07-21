# Plan de Reducción de Errores mypy (Fase 5 → 6+)

**Fecha**: 2026-07-21
**Estado**: WIP, 222 errores restantes (bajó de 297 con el sweep de Fase 5 = **-25%**)

## Contexto

El sistema tiene un baseline de **287–297 errores mypy** pre-existentes. El
proyecto NO bloquea CI por mypy (es informational). Este PR aplicó
fixes de bajo costo:

1. **`__all__` explicito en `app/db/session.py`** (−62 errores
   "Module does not explicitly export attribute")
2. **Eliminacion de `# type: ignore` innecesarios** (`unused-ignore`)
   en 7 archivos: `config.py`, `notifications/templates.py`,
   `solicitudes/queries/distribucion.py`, `db/seed.py`, `db/base.py`,
   `db/sqlite_legacy.py`, `transfers/router.py`
3. **Imports de `Any`** faltantes en `db/base.py`, `db/sqlite_legacy.py`,
   `transfers/router.py`
4. **Tipo de retorno** en `_build_upsert` y `process_result_value`
   (`db/seed.py`, `db/base.py`)

Resultado neto: **297 → 222** errores (−25%).

## Distribucion restante (222 errores)

| Categoria | Cuenta | Esfuerzo | Prioridad |
|-----------|-------:|----------|-----------|
| `no-untyped-def` | 110 | ALTO (anotar cada funcion) | media |
| `type-arg` (dict/list/tuple sin tipo) | 33 | BAJO (mecanico) | media |
| `return-value` (Record vs Response) | 31 | MEDIO (agregar `model_validate` o cast) | alta |
| `union-attr` (None attribute) | 14 | BAJO (assert o cast) | media |
| `no-any-return` | 6 | BAJO (cast explicito) | baja |
| `no-untyped-call` | 5 | BAJO (anotar firmas) | baja |
| `attr-defined` | 4 | BAJO (imports) | baja |
| `assignment` | 4 | BAJO (assert) | baja |
| `call-overload` (auth repo async) | 3 | MEDIO (tipar `Any`) | media |
| Otros (call-arg, name-defined, override, valid-type) | 12 | VARIABLE | baja |

## Plan de Fase 6 (recomendado, en orden de costo/beneficio)

### Sprint 1 (4h) — Bajo costo, alto volumen
- [ ] `dict` → `dict[str, Any]` en 33 lineas (`templates.py`,
  `multibodega.py`, `actions/_common.py`, `service.py` x 4)
- [ ] `list` → `list[X]` en 5 lineas (`auth/repository.py`, etc.)
- [ ] `tuple` → `tuple[X, ...]` en 3 lineas (`sqlite_legacy.py`)
- [ ] `Callable` → `Callable[..., X]` en 2 lineas (`auth/dependencies.py`,
  `rate_limit.py`)

**Resultado esperado**: 222 → 178 (−44 errores).

### Sprint 2 (3h) — return-value con model_validate
- [ ] `warehouses/router.py`: 4 lineas (List[WarehouseRecord] → List[WarehouseResponse])
- [ ] `products/router.py`: 4 lineas
- [ ] `categories/router.py`: 4 lineas
- [ ] `ubicaciones/router.py`: 4 lineas
- [ ] `product_extension/router.py`: 2 lineas
- [ ] `inventory/router.py`: 4 lineas
- [ ] `transfers/router.py`: 1 linea

Estrategia: agregar `model_validate(rec)` o `cast(WarehouseResponse, rec)`
en cada handler.

**Resultado esperado**: 178 → 156 (−22 errores).

### Sprint 3 (4h) — `no-untyped-def` agresivo en routers
- [ ] Anotar firmas de las ~110 funciones en `solicitudes/router.py`
  (16), `ordenes_compra/router.py` (8), `products/repository.py` (1),
  `warehouses/repository.py` (1), `transfers/repository.py` (1),
  `inventory/repository.py` (2), `auth/repository.py` (3),
  `categories/repository.py` (1), `reports/router.py` (4),
  `notificaciones/router.py` (4), `audit/router.py` (3),
  `proveedores/router.py` (5), `supervisores/router.py` (5),
  `stock_real/router.py` (1), `ubicaciones/router.py` (4),
  `auth/router.py` (3), `auth/dependencies.py` (1),
  `transfers/router.py` (6), `transfers/service.py` (3),
  `auth/service.py` (2), `solicitudes/service.py` (1),
  `worker.py` (7), etc.

**Resultado esperado**: 156 → 50 (−106 errores).

### Sprint 4 (2h) — Casos especiales
- [ ] `categories/service.py` 4 lineas: fix `list?[…]` con cast `Optional[List[…]]`
- [ ] `replenishment.py` 12 lineas: fix `ReplenishmentReport | None` con assert
- [ ] `db/session.py` 4 lineas: fix `str | None` con `url = url or ""`
- [ ] `auth/repository.py` 3 lineas: tipar `Any` explicitamente para `AsyncSession | Any`
- [ ] `core/logging.py` 2 lineas: cast `**kwargs` o refactor signature

**Resultado esperado**: 50 → ~20 errores.

### Sprint 5 (1h) — Final
- [ ] Refactor `ReplenishmentReport` para que no retorne None
- [ ] Limpiar 5–10 errores finales

**Resultado esperado**: **~10–15 errores restantes**, todos
aceptables como TODO documentados.

## Recomendacion

Ejecutar Sprints 1–3 en la **Fase 6** (después de go-live). El
sistema actual es funcional con 222 errores mypy. NO es bloqueante
para go-live (CI no falla por mypy).

## Excluidos del scope

- Errores en `db/session.py`/`db/sqlite_legacy.py` relacionados con la
  API legacy sync (se migrarán a async en Fase 6+, junto con los
  repositorios que aún usan `SQLiteDatabase`).
- Errores en `worker.py`: el codigo de Arq está bien; solo falta
  anotación de tipos que es trabajo mecanico.
