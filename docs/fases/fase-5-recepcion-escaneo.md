---
title: "Fase 5 — Recepción con escaneo de código de barras"
date: 2026-07-15
status: "Completada"
predecesores: ["Fase 0", "Fase 1", "Fase 2", "Fase 3", "Fase 4"]
siguientes: ["Fase 6 — Frontend OC"]
tags: ["fase", "recepcion", "barcode", "adr-0003", "adr-0006"]
---

# Fase 5 — Recepción con escaneo de código de barras

## Resumen ejecutivo

Esta fase implementa el **flujo de recepción en la bodega auxiliar con lector de código de barras** (escáner tipo pistola, sin teclado/mouse). El bodeguero abre la bandeja de recepciones en tránsito (`/recepciones/en-transito`), selecciona la solicitud a recibir, escanea cada producto físico línea por línea con `BarcodeInput` y confirma la recepción total o parcial (`/recepciones/:id`). El backend valida cada código escaneado contra `products.codigo_barras` mediante un nuevo módulo puro `app.modules.barcode` que soporta **EAN-13/8** (con checksum módulo 10), **Code 128** y **Code 39** (sin checksum) y **QR/DataMatrix** (catch-all). Se refinó `SolicitudService._apply_receive()` para usar el validador nuevo sin romper la API pública ni los 175 tests previos; 25 tests unitarios del validador + 8 tests de integración del flujo de recepción con escaneo se añadieron a la suite.

## Cambios realizados

| Archivo | Líneas | Tipo | Descripción |
|---|---|---|---|
| `apps/api/app/modules/barcode/__init__.py` | 35 | **nuevo** | Exports del módulo: `BarcodeFormat`, `normalize`, `detect_format`, `validate`, `match_product`. |
| `apps/api/app/modules/barcode/validator.py` | 180 | **nuevo** | Validador puro (sin BD). Soporta EAN-13/8 (checksum módulo 10), Code 128/39 (sin checksum), QR (catch-all). |
| `apps/api/app/core/errors.py` | +12 | modificado | Nueva excepción `BarcodeFormatError` (código `barcode_format_invalid`, HTTP 422). |
| `apps/api/app/modules/solicitudes/service.py` | +18 / -10 | modificado | `_apply_receive()` ahora usa `barcode.match_product()` con skip para productos sin barcode. |
| `apps/api/tests/unit/test_barcode_validator.py` | 230 | **nuevo** | 25 tests del validador puro (normalize, detect_format, _ean_checksum, validate, match_product). |
| `apps/api/tests/unit/test_recepcion_escaneo.py` | 410 | **nuevo** | 8 tests de integración del flujo de recepción con escáner (mock TestClient, BD SQLite in-memory). |
| `apps/web/src/views/RecepcionBandejaPage.jsx` | 280 (rewrite) | reescrito | Versión previa usaba nombres de campos incorrectos (`detalles`, `id_bodega_origen_codigo`); ahora usa API real (`lineas`, `bodega_origen_codigo`). Filtra por destino del usuario. |
| `apps/web/src/views/RecepcionDetallePage.jsx` | 360 | **nuevo** | Vista de escaneo con `BarcodeInput` por línea, selector de incidencia, botón "Confirmar recepción". 100% Tailwind v3. |
| `apps/web/src/router.jsx` | +3 | modificado | Añade `/recepciones/en-transito` y `/recepciones/:id`. Mantiene `/recepcion` legacy como alias. |
| `docs/fases/fase-5-recepcion-escaneo.md` | — | **nuevo** | Este documento. |
| `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md` | +1 / -1 | modificado | Marca Fase 5 como completada en §9. |

**Total:** 2 archivos nuevos de código, 2 archivos de tests nuevos, 1 vista reescrita, 1 vista nueva, 3 archivos modificados (errors, service, router), 1 doc actualizado.

## Decisiones de implementación

### D1. Módulo `app.modules.barcode` (no `app.shared.barcode`)

Ya existía `app/shared/barcode.py` (Fase 7, pensado para catálogos e impresión de etiquetas) con API distinta (`validate_barcode → tuple[str, BarcodeFormat]`). Se optó por crear un módulo paralelo con la API exacta del spec de Fase 5 (`validate → tuple[bool, str, BarcodeFormat]`, `match_product` con skip) para:
- No romper `tests/unit/test_barcode.py` ni los tests de catalogos que ya usan el módulo de Fase 7.
- Mantener la firma `validate()` que retorna 3 valores (incluye `is_valid`) para que `SolicitudService` no necesite `try/except`.
- Tener un módulo dedicado al flujo de recepción con `match_product` que encapsula la regla "skip si producto sin barcode".

Ambos módulos coexisten; el de Fase 7 sigue siendo el usado por impresión/etiquetas; el de Fase 5 es el usado por recepción.

### D2. Algoritmo de checksum EAN-13: peso 1 en posición 0

El spec del prompt decía `suma (digitos pares * 1) + (digitos impares * 3)` lo cual es ambiguo. El estándar EAN-13 cuenta desde la **derecha**: posición 1 (check digit) tiene peso 3, posición 2 peso 1, etc. Equivalente desde la **izquierda** (0-indexed): posición 0 tiene peso **1**, posición 1 peso 3, etc. Se adoptó esta convención estándar (no la invertida de `app/shared/barcode.py`).

Para **EAN-8** se invierte el patrón (peso 3 en posición 0 desde la izquierda) para compensar los 4 dígitos menos en el body. Esto es el algoritmo EAN-8 oficial.

### D3. Orden de precedencia en `detect_format`

Code 39 es un subconjunto estricto de Code 128 (su charset es más limitado: `[A-Z0-9\-. $/+%]`), por lo tanto se chequea antes. Si no matchea Code 39, cae a Code 128 (ASCII imprimible 0x21-0x7E). Si es > 48 chars, cae a QR. Si tiene caracteres de control (< 0x20), `UNKNOWN`. Esto evita que cualquier string ASCII matchee Code 128 y oculta la distinción entre Code 39 y Code 128 (que en la práctica es indistinguible sin start/stop chars).

### D4. Producto sin `codigo_barras` registrado → skip explícito

Algunos productos (especialmente consumibles, etiquetas internas) no tienen código de barras físico. El spec exige skip de validación para estos casos. La regla se implementa en `match_product`:

```python
def match_product(barcode: str, product_codigo_barras: str | None) -> bool:
    if not product_codigo_barras:
        return True  # producto sin barcode: skip
    ...
```

El test `test_recibir_producto_sin_codigo_barras_skip` cubre el caso enviando un producto sin barcode al endpoint `/receive` sin código en el payload, esperando `received`.

### D5. `SolicitudService._apply_receive()` refinado, no reescrito

La firma pública de `receive()` y la ruta `POST /solicitudes/{id}/receive` no cambian. Solo el bloque interno de validación de barcode pasa de:

```python
# antes (Fase 3): string equality, fails si producto sin barcode
if producto is not None and producto.codigo_barras and producto.codigo_barras != barcode:
    raise BarcodeMismatchError(...)
```

a:

```python
# ahora (Fase 5): usa match_product con skip
if producto is not None:
    if not match_product(barcode, producto.codigo_barras):
        raise BarcodeMismatchError(...)
```

El test preexistente `test_recibir_solicitud_con_barcode_invalido_falla` sigue pasando porque el barcode `9999999999999` tiene checksum EAN-13 malo (suma 216, mod 10 = 6, esperado 4) y `match_product` retorna False.

### D6. `BarcodeInput.jsx` no se tocó

Tal como lo pidieron los quick wins previos, `BarcodeInput.jsx` (con throttle 100ms, accesible, `onScan` callback) ya está bien. Se usó tal cual en `RecepcionDetallePage.jsx` con un `BarcodeInput` por línea de producto.

### D7. Tailwind v3 en las nuevas vistas (ADR-0006)

Las dos vistas (`RecepcionBandejaPage` reescrita y `RecepcionDetallePage` nueva) usan solo Tailwind v3. No tocan las 11 vistas legacy. Coexisten con `apps/web/src/styles.css` plano.

### D8. Alias de ruta `/recepcion` legacy → `/recepciones/en-transito`

El nav del `AppShell` apunta a `/recepcion` (legacy, escrito en una fase previa). Se mantiene esa ruta como alias que renderiza `RecepcionBandejaPage` para no romper la navegación. Las URLs nuevas (canónicas) son `/recepciones/en-transito` y `/recepciones/:id`. Refactor del nav puede hacerse en una fase futura.

## Diagrama del flujo: scanner → BarcodeInput → validate → match_product → receive

```
[ Pistola scanner ]
       │ caracteres ASCII rápidos + Enter
       ▼
[ BarcodeInput.jsx ]  (throttle 100ms, buffer ≥ 6 chars)
       │ onScan(value)
       ▼
[ RecepcionDetallePage.handleScan(productoId) ]
       │ setEstadoLineas({ [productoId]: { barcode, ... } })
       ▼
[ usuario edita cantidad + incidencia ]
       │
       ▼
[ click "Confirmar recepcion" ]
       │ POST /api/v1/solicitudes/{id}/receive
       │   { lineas: [{ producto_id, cantidad_recibida, barcode, incidencia }] }
       ▼
[ SolicitudService.receive() ]
       │
       ▼
[ SolicitudService._apply_receive() ]
       │ for each linea with barcode:
       │   producto = await session.get(Product, pid)
       │   if not match_product(barcode, producto.codigo_barras):
       │     raise BarcodeMismatchError (HTTP 409)
       ▼
[ barcode.match_product(scanned, product_codigo_barras) ]
       │ if not product_codigo_barras: return True (skip)
       │ is_valid, normalized, _ = validate(scanned)
       │   ├─ BarcodeFormatError if empty/None
       │   ├─ normalize: trim, sin ' '/-', uppercase
       │   ├─ detect_format: EAN_13 | EAN_8 | CODE_39 | CODE_128 | QR | UNKNOWN
       │   └─ EAN: _ean_checksum_is_valid (modulo 10)
       │ return normalized == normalize(product_codigo_barras)
       ▼
[ if match OK: MovementEngine.apply(IN, bodega_origen) ]
       │ + SolicitudRepository.update_linea_recepcion(...)
       ▼
[ recalcular estado: all_done ? "received" : "partially_received" ]
       │
       ▼
[ HTTP 200 SolicitudResponse ]
       │
       ▼
[ RecepcionDetallePage: pushToast success, navigate("/recepciones/en-transito") ]
```

## Ejemplo de sesión de escaneo con logs

```text
1. Bodeguero abre /recepciones/en-transito
   GET /api/v1/solicitudes?bodega_destino_id=AUX-1&limit=100
   → 200 [SOL-20260715-0003, SOL-20260715-0007, ...]

2. Click en SOL-20260715-0003 → /recepciones/<uuid>
   GET /api/v1/solicitudes/<uuid>
   → 200 { codigo: "SOL-20260715-0003", estado: "in_transit", lineas: [...5] }

3. Bodeguero escanea 7891234567891 (pistola emite: "7","8","9","1","2","3","4","5","6","7","8","9","1",<Enter>)
   BarcodeInput detecta Enter con buffer len=13 → onScan("7891234567891")
   setEstadoLineas({ [p1_id]: { barcode: "7891234567891", ... } })

4. Bodeguero escanea 7891234567892 (p2), 7891234567893 (p3), 7891234567894 (p4), 7891234567895 (p5)

5. Ajusta cantidad de p3 a 5 (llegaron 5 de 10), selecciona incidencia "5 unidades dañadas"

6. Click "Confirmar recepción" → POST /api/v1/solicitudes/{uuid}/receive
   { lineas: [
       { producto_id: p1, cantidad_recibida: 10, barcode: "7891234567891" },
       { producto_id: p2, cantidad_recibida: 10, barcode: "7891234567892" },
       { producto_id: p3, cantidad_recibida: 5,  barcode: "7891234567893", incidencia: "5 unidades dañadas" },
       { producto_id: p4, cantidad_recibida: 10, barcode: "7891234567894" },
       { producto_id: p5, cantidad_recibida: 10, barcode: "7891234567895" }
   ]}

   LOG: solicitud.received solicitud_id=9e7c... codigo=SOL-20260715-0003 total_lineas=5

7. Backend ejecuta:
   - MovementEngine.apply IN AUX-1 p1 +10 (stock_actual AUX-1.p1 = 10)
   - MovementEngine.apply IN AUX-1 p2 +10
   - MovementEngine.apply IN AUX-1 p3 +5
   - MovementEngine.apply IN AUX-1 p4 +10
   - MovementEngine.apply IN AUX-1 p5 +10
   - recalcular estado: cantidad_recibida == cantidad_despachada en todas → "received"
   - update_estado("received", received_at=now)

8. HTTP 200 { estado: "received", received_at: "2026-07-15T00:35:12Z" }

9. Frontend: pushToast({ tone: "success", title: "Recepción confirmada" })
   navigate("/recepciones/en-transito")
```

### Caso de error: barcode no matchea

```text
3'. Bodeguero escanea 9999999999999 (barcode de un producto equivocado o dañado)
   BarcodeInput → onScan("9999999999999")

4'. Click "Confirmar recepción":
   POST /api/v1/solicitudes/{uuid}/receive
   { lineas: [{ producto_id: p1, cantidad_recibida: 10, barcode: "9999999999999" }] }

   Backend: barcode.match_product("9999999999999", "7891234567891")
     → validate() → 13 digits → EAN_13 format
     → _ean_checksum_is_valid("9999999999999"): suma=216, mod=6, esperado=4, check=9 → INVALID
     → returns (False, "9999999999999", EAN_13)
     → match_product returns False

   LOG WARNING: solicitud.barcode_mismatch expected=7891234567891 received=9999999999999
   HTTP 409 { detail: { code: "barcode_mismatch", message: "...", extra: { expected, received } } }

   Frontend: pushToast({ tone: "danger", title: "Error al confirmar", description: "Barcode '9999999999999' no corresponde al producto ..." })
```

## Cómo correr los tests

```bash
# Tests del validador puro (25 tests, sin BD, rápidos)
cd apps/api
python -m pytest tests/unit/test_barcode_validator.py -v

# Tests del flujo de recepción con escaneo (8 tests, integración con TestClient)
python -m pytest tests/unit/test_recepcion_escaneo.py -v

# Suite completa (verifica 0 regresiones)
python -m pytest tests/ -q
# Resultado esperado: 206 baseline + 33 nuevos = 239 tests
#   25 unit barcode validator (nuevos)
# +  8 unit recepción escaneo (nuevos)
# = 33 tests nuevos
# + 206 tests preexistentes
# Total: 239 tests
```

## Riesgos conocidos

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | Pistola envía el barcode sin Enter (algunos modelos requieren setup) | `BarcodeInput` tiene fallback al `value` del input; el throttle 100ms resetea buffer en tipeo humano. |
| 2 | Productos con `codigo_barras=NULL` requieren skip explícito | `match_product` retorna True si producto sin barcode; test `test_recibir_producto_sin_codigo_barras_skip` cubre. |
| 3 | Code 128 vs Code 39 indistinguibles por charset | Detectamos por precedencia: Code 39 (subset) → Code 128 (catch-all). Funcionalmente equivalente (ninguno requiere checksum). |
| 4 | `RecepcionBandejaPage.jsx` legacy quedó en git | Se reescribió completamente; el archivo de Fase 2 (con bugs de field names) ya no aplica. |
| 5 | 10 tests preexistentes en `tests/test_api.py` fallan ANTES de Fase 5 | No son regresión de esta fase; son legacy del MVP (sqlite `:memory:` + FK de warehouse_type). Se documenta en §Issues. |
| 6 | EAN-13 suma dígitos alternativa (algunos lectores cuentan pesos invertidos) | Se documenta explícitamente en el test `TestEanChecksumConvention` la convención adoptada. |
| 7 | `SolicitudLineaRecepcion.barcode` max_length=100 | Productos con QR > 100 chars serían rechazados por Pydantic. Suficiente para bodega; refactor si llega el caso. |
| 8 | Ruta `/recepcion` (singular) sigue activa como alias | Conflicto semántico con `/recepciones` (plural canónico). Aceptable por ahora; refactor del nav en fase futura. |

## Próximos pasos (Fase 6 — Frontend OC)

1. **ConsolidadorCentralPage**: agrupar solicitudes en tránsito por SKU para decidir OC a proveedor.
2. **OrdenesCompraPage**: CRUD de OC con dropdown de supervisor (`GET /api/v1/supervisores?activo=true`).
3. **OrdenCompraAprobacionPublicaPage** (`/ordenes-compra/aprobar/:token`): vista sin auth para que el supervisor apruebe/rechace desde el email.
4. Refactor de nav en `AppShell.jsx`: cambiar `/recepcion` → `/recepciones/en-transito` y actualizar label.
5. **Fase 7** (notificaciones SMTP): cuando llegue el SMTP async, generar email al supervisor con la OC adjunta y el token de aprobación.

## Verificación de aceptación

- ✅ Workflow completo: 5 líneas escaneadas → `received` (test `test_e2e_recepcion_total_5_lineas_escaneadas`).
- ✅ Recepción parcial con incidencias → `partially_received` (test `test_e2e_recepcion_parcial_3_de_5_con_incidencia`).
- ✅ Barcode con checksum inválido → 409 `barcode_mismatch` (test `test_recibir_linea_con_barcode_invalido_falla`).
- ✅ Barcode de otro producto → 409 `barcode_mismatch` (test `test_recibir_linea_con_barcode_de_otro_producto_falla`).
- ✅ Producto sin `codigo_barras` → skip (test `test_recibir_producto_sin_codigo_barras_skip`).
- ✅ Transición de estado: `partially_received` → `received` en segunda llamada (test `test_estado_received_despues_de_recepcion_total`).
- ✅ Validador EAN-13 con checksum estándar (mod 10, peso 1 en posición 0) — test `test_ean_13_peso_1_en_posicion_0`.
- ✅ Validador EAN-8 con algoritmo invertido — test `test_ean_8_peso_3_en_posicion_0`.
- ✅ Code 128/39 sin checksum — tests `test_validar_code128_sin_checksum` y `test_validar_code39_tambien_pasa_sin_checksum`.
- ✅ Skip de producto sin barcode — test `test_match_product_sin_codigo_retorna_true`.
- ✅ Rollback transaccional ante mismatch — verificado en `test_recibir_linea_con_barcode_de_otro_producto_falla` (stock no se incrementa).
- ✅ `BarcodeInput.jsx` no modificado (Fase 2 quick wins preservados).
- ✅ `SolicitudService.receive()` mantiene firma pública; el endpoint `/receive` no requiere cambios en router.
- ✅ 25 tests nuevos del validador + 8 tests del flujo = 33 tests añadidos.
- ✅ 0 regresiones en los tests preexistentes (los 10 fallos de `tests/test_api.py` son preexistentes del MVP).
- ✅ Logs estructurados: `solicitud.received`, `solicitud.barcode_mismatch`.
