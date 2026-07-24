# Reporte E2E: Módulo de Órdenes de Compra por Correo

**Fecha:** 2026-07-24
**Tester:** Mavis (test automatizado contra sistema en vivo)
**Sistema:** Bodegaje v1.0.0 (commit `62cfa3e`)
**Stack:** FastAPI + Postgres 17 + Arq worker + Mailpit
**Script:** [`auditoria-fase5/test_oc_correo_flujo.py`](./test_oc_correo_flujo.py)

---

## Resumen ejecutivo

Se ejecutaron 3 escenarios end-to-end del módulo completo de Ordenes de Compra (OC),
desde el **quiebre de stock** hasta el **cuadre OC↔factura**, contra el sistema
en producción (http://localhost:8080). Los 3 escenarios cerraron correctamente.

| # | Escenario                       | OC (corrida final) | Resultado     | Tiempo |
| - | ------------------------------- | ------------------ | ------------- | ------ |
| A | Happy path (cuadra perfecto)    | OC-0061            | ✅ cuadra     |  ~3s   |
| B | Descuadre (faltante + sobrante) | OC-0062            | ⚠️ detectado  |  ~3s   |
| C | Rechazo por link público        | OC-0063            | ✅ rechazado  |  ~2s   |

**Pasados: 3/3 — Tiempo total: 11.9s — Exit code: 0**

> El script es **idempotente y robusto**: usa TAG aleatorio por corrida
> para no colisionar con ejecuciones previas. Si hay OCs viejas en
> `enviado_a_supervisor` (de otros tests), las detecta y las marca como
> `previas` (no mías), y con `--cleanup` las rechaza automáticamente.

---

## Uso del script

```bash
# Corrida normal
python test_oc_correo_flujo.py
# -> 3/3 verde, exit 0, exit 1 si algun escenario falla

# Corrida con limpieza previa y posterior
python test_oc_correo_flujo.py --cleanup
# -> Rechaza OCs en 'enviado_a_supervisor' antes y despues
# -> Deja el sistema completamente limpio

# Con logs detallados
python test_oc_correo_flujo.py --verbose
```

---

## Flujo completo cubierto

```
[Operador] Solicitud manual (Norte → Principal)
    │
    ▼
[admin/supervisor] Aprueba → Despacha → Recibe (mueve stock)
    │
    ▼
[Operador] Crea OC para reponer (proveedor → Principal)
    │
    ▼
[API] POST /ordenes-compra/{id}/enviar-correo
    │   → inserta en email_outbox
    │   → encola task en Arq
    │   → genera token de aprobación HMAC
    │   → estado OC = "enviado_a_supervisor"
    ▼
[Worker] Arq toma la task, envía vía SMTP a Mailpit
    │   → estado outbox = "sent"
    ▼
[Supervisor] Click en link del email
    │   → GET /public/ordenes-compra/aprobar/{token} (ver)
    │   → POST /public/ordenes-compra/aprobar/{token} (aprobar)
    │     o
    │   → POST /public/ordenes-compra/rechazar/{token} (rechazar con motivo)
    │
    ├─ Aprobado  → OC.estado = "aprobado"
    │   → [Operador] POST /ordenes-compra/{id}/comprar
    │   → OC.estado = "comprado"
    │   → [Operador] Recepción: POST /inventory/movements (in, receipt, factura)
    │   → Cuadre OC vs factura (manual o externo)
    │
    └─ Rechazado → OC.estado = "rechazado", motivo persistido
                  → FIN (no se compra, no se recibe, no se mueve stock)
```

---

## Escenario A — Happy Path (cuadra perfecto)

**OC-0016** — `Proveedor Happy A7ehdo`

| Paso | Acción                                                 | Resultado  |
| ---- | ------------------------------------------------------ | ---------- |
| A.1  | Crear solicitud manual (Norte→Principal, 50 FLOW)      | 201 OK     |
| A.2  | Approve → Dispatch → Receive (50 FLOW movidos)         | 200/200/200 |
| A.3  | Crear OC (100 FLOW @ $1500)                            | 201 OC-0016 (total $150.000) |
| A.4  | Enviar correo (encolar email + token)                 | 200, OC.estado=`enviado_a_supervisor` |
| A.5  | Worker envía email (Mailpit)                           | outbox.status=`sent` en < 1s |
| A.6  | Aprobar por link público (sin auth)                    | 200, OC.estado=`aprobado` |
| A.7  | Marcar como comprada (proveedor entregó)               | 200, OC.estado=`comprado` |
| A.8  | Recepción: 1 movimiento `in` con `reference_id=FAC-A7ehdo` | 201 |
| A.9  | **Cuadre: OK** — OC pidió 100, llegaron 100            | ✅         |

**Movimiento resultante:**

```
movement_type=in  reference_type=receipt  reference_id=FAC-A7ehdo
product_sku=FLOW-TEST-001  quantity=100.00
notes="[E2E-OC-A7ehdo] OC-0016 - Recepcion factura FAC-A7ehdo - "
```

---

## Escenario B — Descuadre (faltante + sobrante)

**OC-0017** — `Proveedor Descuadre Bndu8a`

| Línea  | SKU                | Pedido | Recibido | Diferencia | Tipo      |
| ------ | ------------------ | ------ | -------- | ---------- | --------- |
| 1      | FLOW-TEST-001      | 50     | 45       | **-5**     | faltante  |
| 2      | PROD-NORMAL-44E53D | 30     | 32       | **+2**     | sobrante  |

**Cuadre detecta correctamente** ambos tipos. Acción sugerida por el test
(reportada al operador, **NO bloqueante**):

```
Nota de Credito al proveedor por: FLOW-TEST-001 (-5.00)
Devolver excedente al proveedor: PROD-NORMAL-44E53D (+2.00)
```

> **Hallazgo importante:** El sistema **NO bloquea automáticamente** el
> descuadre. La responsabilidad de actuar sobre la diferencia queda en el
> operador (gestión de NC o devolución). Esto es coherente con el alcance
> actual del módulo (el sistema registra, el humano decide).

---

## Escenario C — Rechazo por link público

**OC-0018** — `Proveedor Rechazo C7cec4`

| Paso | Acción                                          | Resultado  |
| ---- | ----------------------------------------------- | ---------- |
| C.1  | Crear OC (200 FLOW @ $9999)                     | 201 OC-0018 (total $1.999.800) |
| C.2  | Enviar correo (encolar email)                   | 200        |
| C.3  | Supervisor rechaza con motivo por link público  | 200, OC.estado=`rechazado` |
| C.4  | Verificar estado final                          | `rechazado`, motivo persistido |
| C.5  | Verificar que NO se generó ningún movimiento    | 0 movs con TAG C7cec4 ✅ |

El motivo se persistió correctamente:

```
"Precio unitario excede presupuesto aprobado para C7cec4"
```

---

## Hallazgos críticos

### 🟢 Lo que funciona

1. **Flujo completo de aprobación por correo**: la OC se encola en
   `email_outbox`, el worker la envía por SMTP (Mailpit en dev), genera
   token HMAC, supervisor abre link público, aprueba/rechaza sin auth.
2. **Idempotencia del token**: el link público es one-shot. Reusarlo no
   duplica acciones (validado por código en `aprobar_con_token`).
3. **Estados terminales claros**: `comprado` (A) y `rechazado` (C) son
   mutuamente excluyentes. `aprobado` es estado intermedio antes de
   `comprar`.
4. **Motivo de rechazo persistido** y visible en la respuesta OC.
5. **Rechazo total**: tras rechazo, **no** se genera ningún movimiento de
   stock ni de inventario, ni se envía correo a proveedor.

### 🟡 Gaps del módulo (oportunidades de mejora)

1. **No existe endpoint `/recepciones` ni tabla `oc_recepciones`.**
   - La "recepción" es un movimiento `in` con `reference_type=receipt`.
   - El cruce OC↔factura es responsabilidad del operador/herramienta externa.
   - **Recomendación:** crear `POST /ordenes-compra/{id}/recepcion` que
     registre la recepción formalmente, la asocie a la OC, y devuelva el
     resultado del cuadre automático.
2. **El cuadre OC↔factura NO existe en el sistema.**
   - Hoy el cuadre es responsabilidad de este test o del operador.
   - **Recomendación:** agregar `GET /ordenes-compra/{id}/cuadre?factura=...`
     que liste diferencias y devuelva estado (ok/faltante/sobrante).
3. **El sistema NO bloquea descuadres.**
   - El operador puede registrar una recepción con cualquier cantidad.
   - Esto es coherente con el alcance pero un aviso/warning en la UI
     reduciría errores humanos.
4. **El número de factura es texto libre.**
   - No hay validación de formato ni unicidad. Dos recepciones con la
     misma factura podrían generar descuadres confusos.
5. **No hay endpoint público para que el proveedor marque "entregado".**
   - El flujo asume que el operador confirma la compra tras hablar con el
     proveedor por otro canal. Podría ser un cuarto actor (proveedor con
     cuenta, link similar al del supervisor).

### 🔴 Observaciones técnicas

1. **El path público es `/aprobar/` (sin n).** El endpoint
   `GET /api/v1/public/ordenes-compra/aprobar/{token}` y
   `POST /api/v1/public/ordenes-compra/rechazar/{token}`. **NO** existe
   `/aprobacion/` (singular con n).
2. **El token de aprobación se devuelve en la respuesta de
   `POST /api/v1/ordenes-compra/{id}/enviar-correo`.** Esto facilita el
   testing E2E pero en producción NO debe exponerse al cliente (viaja en
   el email vía outbox).
3. **Rate limit de 5 req/min en endpoints públicos.** Aplicado por IP
   (ADR-0005 IMP-004). No interfiere con el flujo normal pero un supervisor
   haciendo doble-click puede recibir 429.
4. **Rate limit de 5 logins/min por username** (C5.2). Detectado durante
   el armado del test: si se corre el script varias veces seguidas, el
   login puede recibir 429. **Solución implementada:** retry automático
   con espera de `Retry-After` en `APIClient.login()`.
5. **El cuadre test usa TAG en `notes` para evitar colisiones** con
   recepciones de OC previas. Esto es solo para el test; en producción
   el cuadre debería ser por `id_orden_compra` ↔ movimientos asociados.

---

## Cobertura del test

| Funcionalidad                                  | Cubierto | Notas |
| ---------------------------------------------- | -------- | ----- |
| Crear solicitud de reposición                  | ✅       | Escenario A |
| Approve / Dispatch / Receive de solicitud     | ✅       | Escenario A |
| Crear OC                                       | ✅       | A, B, C |
| Enviar correo (encolar + worker)               | ✅       | A, B, C |
| Aprobar OC por link público                    | ✅       | A, B |
| Rechazar OC por link público con motivo        | ✅       | C |
| Marcar OC como comprada                        | ✅       | A, B |
| Registrar recepción (movimiento `in`)          | ✅       | A, B |
| Cuadre OC vs factura (faltante)                | ✅       | B |
| Cuadre OC vs factura (sobrante)                | ✅       | B |
| Cuadre OC vs factura (perfecto)                | ✅       | A |
| Rechazo total (sin movimientos)                | ✅       | C |
| Persistencia de motivo de rechazo              | ✅       | C |
| Token HMAC one-shot                            | ⚠️       | Validado por código; no probado reuso |
| Idempotencia de solicitud (por bodega+producto)| ⚠️       | Cubierto en BUG 9 (otro test) |
| Auto-generación de OC desde alerta de stock    | ❌       | No implementado (operador crea manual) |
| Idempotencia del script (corrida multiple)     | ✅       | TAG aleatorio por corrida |
| Rate limit de login (429) con retry            | ✅       | Detectado y resuelto con backoff |
| Limpieza de OCs previas (`--cleanup`)          | ✅       | Flag opcional, exit 0 garantizado |

---

## Recomendaciones para v1.1.0

1. **Endpoint `/recepciones`** que tome payload `{id_oc, factura, lineas[]}`
   y registre movimientos `in` con la OC asociada.
2. **Endpoint `/cuadre`** que reciba `id_oc` + `factura` y devuelva
   `{esperado, recibido, diferencias, cuadra, accion_sugerida}`.
3. **UI en el módulo de OC**: botón "Registrar recepción" con flujo guiado
   y vista de cuadre inmediata.
4. **Validación柔柔 (soft) de descuadre**: al recibir N unidades vs las M
   pedidas, mostrar warning (no bloqueante) en la UI.
5. **Webhooks al proveedor**: tras marcar `comprado`, enviar email/SMS al
   proveedor con instrucciones de entrega y código OC.

---

## Conclusión

El módulo de OC por correo **funciona end-to-end** y los 3 escenarios del
flujo crítico (happy, descuadre, rechazo) están cubiertos por tests
automatizados que pasan contra el sistema en vivo.

El script es **idempotente y robusto**:
- Corre en ~12 segundos
- Exit code 0 si todo cierra, 1 si falla un escenario, 2 si falla el cleanup
- Soporta flag `--cleanup` para rechazar OCs previas de tests
- Implementa retry automático en el login si recibe 429 (rate limit)
- Deja el sistema en estado limpio (0 OCs pendientes)

El principal gap es la **ausencia de un endpoint nativo de recepción y
cuadre**, hoy implementado en este test. Agregar `/recepciones` y
`/cuadre` convertiría al sistema en self-service para el operador
(eliminando la necesidad de este script externo).
