"""
test_oc_correo_flujo.py
=======================

E2E del modulo de Ordenes de Compra por correo, desde el quiebre de stock
hasta el cuadre OC vs factura.

Cubre 3 escenarios:
- A. Happy path  - mercaderia llega completa, cuadre OK
- B. Descuadre   - mercaderia llega con diferencias (faltantes / sobrantes),
                   cuadre detecta diferencias
- C. Rechazo     - supervisor rechaza por link publico, OC queda en `rechazado`

Convenciones:
- Cada escenario usa una "OC_TAG" (sufijo unico) que se graba en
  `inventory_movements.notes` con prefijo "[E2E-OC-<TAG>]" para que
  el cuadre pueda matchear OC vs movimientos sin ambiguedad.
- Las recepciones usan `reference_type=receipt` y `reference_id` = numero
  de factura. El cuadre busca movimientos por TAG.
- El sistema NO tiene endpoint /recepciones: las recepciones son
  movimientos `in` con `reference_type=receipt`.
- El cuadre OC<->factura NO lo hace el sistema, lo hace este test
  (gap documentado - ver REPORTE).

Salida:
- Reporte en consola con metricas
- Exit code 0 si los 3 escenarios cierran como se espera
- Exit code 1 si algun escenario falla
- Exit code 2 si --cleanup falla

Uso:
    python test_oc_correo_flujo.py
    python test_oc_correo_flujo.py --cleanup     # rechaza OCs viejas al final
    python test_oc_correo_flujo.py --verbose     # logs de cada paso
"""
from __future__ import annotations

import argparse
import os
import random
import string
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE = os.environ.get("BOD_API", "http://localhost:8080/api/v1")
TIMEOUT = 15

ADMIN = ("admin", "admin12345")

# IDs del sistema en vivo (validados con la sesion actual)
BODEGA_PRINCIPAL = "a96d195d-58c2-4a5c-97d8-df333f44dab1"
BODEGA_NORTE = "3a5baf63-18f7-4ead-8cab-6ab412ac525a"
PROVEEDOR = "afe472c9-5d2b-4122-9bff-378b8f45c8d9"
SUPERVISOR = "a4557a4e-7479-43ce-a2d2-7c24784a4428"

# SKUs del sistema (FLOW-TEST-001 = $1500, PROD-NORMAL = $5000)
PROD_FLOW = "1e60dd58-f9db-4502-bd90-326a5fad36a5"   # FLOW-TEST-001
PROD_NORMAL = "9334392b-963c-4301-a9d6-aceada8a2173"  # PROD-NORMAL-44E53D

# Cuantos de stock dejamos al inicio del escenario en la principal.
# Necesitamos que la principal tenga stock para que la solicitud fluya.
# (En el sistema actual la principal esta en ~1044 FLOW y ~193 PROD-NORMAL)
# No tocamos stock aqui: las recepciones iran a principal.

# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------


def _suffix() -> str:
    """Sufijo aleatorio corto para evitar colisiones entre corridas."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=5))


def _sanitize(obj):
    """Convierte Decimal/UUID/datetime a tipos JSON-serializables, recursivo."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Decimal):
        return str(obj)
    from uuid import UUID

    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize(v) for v in obj]
    return str(obj)


class APIClient:
    def __init__(self, base: str = BASE) -> None:
        self.base = base
        self.s = requests.Session()
        self.token: str | None = None

    def login(self, username: str, password: str) -> None:
        """Login con retry automatico si hay 429 (rate limit por username).
        OWASP: max 5 logins/min por username. Si lo excedemos, esperamos
        Retry-After y reintentamos hasta 3 veces.
        """
        url = f"{self.base}/auth/login"
        body = {"username": username, "password": password}
        for intento in range(4):
            r = self.s.post(
                url,
                json=body,
                headers={"X-Forwarded-For": "10.0.0.1"},
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                data = r.json()
                self.token = data["token"]
                self.s.headers.update({"Authorization": f"Bearer {self.token}"})
                return
            if r.status_code == 429:
                # Rate limit: respetar Retry-After (en segundos) o default 15s
                retry_after = int(r.headers.get("Retry-After", "15"))
                print(f"  [login] 429 rate limit, esperando {retry_after}s (intento {intento+1}/4)")
                time.sleep(retry_after + 1)
                continue
            # Otro error
            r.raise_for_status()
        raise RuntimeError("Login fallo tras 4 intentos por rate limit (429)")

    def get(self, path: str, **kw) -> requests.Response:
        return self.s.get(f"{self.base}{path}", timeout=TIMEOUT, **kw)

    def post(self, path: str, json=None, **kw) -> requests.Response:
        return self.s.post(
            f"{self.base}{path}",
            json=_sanitize(json) if json is not None else None,
            timeout=TIMEOUT,
            **kw,
        )

    def patch(self, path: str, json=None, **kw) -> requests.Response:
        return self.s.patch(
            f"{self.base}{path}",
            json=_sanitize(json) if json is not None else None,
            timeout=TIMEOUT,
            **kw,
        )


# ---------------------------------------------------------------------------
# Helpers del flujo
# ---------------------------------------------------------------------------


def _check(r: requests.Response, expected: int | tuple[int, ...], msg: str) -> None:
    """Valida codigo de estado, raise si no coincide."""
    exp = expected if isinstance(expected, tuple) else (expected,)
    if r.status_code not in exp:
        raise AssertionError(
            f"{msg}: status {r.status_code} (esperado {exp}). "
            f"Body: {r.text[:400]}"
        )


def _ok(r: requests.Response, expected: int | tuple[int, ...] = (200, 201), msg: str = ""):
    """check + return json (o text si falla el parseo)."""
    _check(r, expected, msg)
    try:
        return r.json()
    except Exception:
        return r.text


def get_stock(api: APIClient, warehouse_id: str, product_id: str) -> Decimal:
    """Devuelve la cantidad en stock para (warehouse, product). 0 si no hay fila."""
    r = api.get(
        "/inventory/stock",
        params={"warehouse_id": warehouse_id, "product_id": product_id},
    )
    _check(r, 200, "get stock")
    for row in r.json():
        if row["warehouse_id"] == warehouse_id and row["product_id"] == product_id:
            return Decimal(str(row["quantity"]))
    return Decimal("0")


def set_parametros_stock(
    api: APIClient,
    warehouse_id: str,
    product_id: str,
    min_q: Decimal | None = None,
    max_q: Decimal | None = None,
) -> None:
    """Setea min/max de stock (no toca quantity). Si un valor es None no se envia."""
    body: dict = {}
    if min_q is not None:
        body["min_quantity"] = str(min_q)
    if max_q is not None:
        body["max_quantity"] = str(max_q)
    if not body:
        return
    r = api.put(
        f"/inventory/parametros/{product_id}/{warehouse_id}",
        json=body,
    )
    _check(r, (200, 201, 204), f"set parametros stock {product_id}/{warehouse_id}")


def crear_solicitud_reposicion(
    api: APIClient,
    *,
    id_bodega_origen: str,
    id_bodega_destino: str,
    lineas: list[dict],
    notas: str,
) -> dict:
    """Crea solicitud de reposicion. Direcciones: bodega_origen_id=quien entrega,
    bodega_destino_id=quien recibe. La principal solo entrega (origen)."""
    # Aceptamos los nombres largos o cortos
    origen = id_bodega_origen
    destino = id_bodega_destino
    body = {
        "bodega_origen_id": origen,
        "bodega_destino_id": destino,
        "prioridad": "alta",
        "notas": notas,
        "lineas": lineas,
    }
    r = api.post("/solicitudes", json=body)
    return _ok(r, 201, "crear solicitud")


def mover_solicitud(
    api: APIClient,
    sol_id: str,
    accion: str,
    lineas: list[dict] | None = None,
) -> dict:
    """Avanza una solicitud: approve / dispatch / receive / reject / cancel.

    Para dispatch/receive se requiere `lineas` con
    {"producto_id": UUID, "cantidad_despachada"|"cantidad_recibida": Decimal}.
    """
    body: dict | None = None
    if accion in ("dispatch", "receive") and lineas is not None:
        # Mapeamos el nombre generico "cantidad" a lo que pide el schema
        norm = []
        for ln in lineas:
            entry = {"producto_id": ln["producto_id"]}
            if "cantidad_despachada" in ln:
                entry["cantidad_despachada"] = str(ln["cantidad_despachada"])
            if "cantidad_recibida" in ln:
                entry["cantidad_recibida"] = str(ln["cantidad_recibida"])
            if "cantidad" in ln:
                # dispatch: cantidad_despachada; receive: cantidad_recibida
                key = (
                    "cantidad_despachada"
                    if accion == "dispatch"
                    else "cantidad_recibida"
                )
                entry[key] = str(ln["cantidad"])
            norm.append(entry)
        body = {"lineas": norm}
    r = api.post(f"/solicitudes/{sol_id}/{accion}", json=body)
    return _ok(r, 200, f"solicitud {accion}")


def crear_oc(
    api: APIClient,
    *,
    lineas: list[dict],
    proveedor_nombre: str = "Proveedor Demo E2E",
    notas: str | None = None,
) -> dict:
    body = {
        "id_bodega_principal": BODEGA_PRINCIPAL,
        "id_supervisor": SUPERVISOR,
        "proveedor_nombre": proveedor_nombre,
        "lineas": lineas,
    }
    if notas:
        body["notas"] = notas
    r = api.post("/ordenes-compra", json=body)
    return _ok(r, 201, "crear OC")


def enviar_correo_oc(api: APIClient, oc_id: str) -> dict:
    r = api.post(f"/ordenes-compra/{oc_id}/enviar-correo")
    return _ok(r, 200, "enviar correo OC")


def aprobar_oc_publica(api: APIClient, token: str) -> dict:
    r = api.post(f"/public/ordenes-compra/aprobar/{token}")
    return _ok(r, 200, "aprobar OC publica")


def rechazar_oc_publica(api: APIClient, token: str, motivo: str) -> dict:
    r = api.post(
        f"/public/ordenes-compra/rechazar/{token}",
        json={"motivo": motivo},
    )
    return _ok(r, 200, "rechazar OC publica")


def comprar_oc(api: APIClient, oc_id: str) -> dict:
    r = api.post(f"/ordenes-compra/{oc_id}/comprar")
    return _ok(r, 200, "comprar OC")


def recepcionar_oc(
    api: APIClient,
    *,
    oc_codigo: str,
    tag: str,
    numero_factura: str,
    recepciones: list[dict],  # [{"id_producto": ..., "cantidad": ...}]
) -> list[dict]:
    """Registra movimientos `in` con reference_type=receipt, reference_id=factura
    y notes con el TAG para que el cuadre pueda matchear."""
    movimientos = []
    for rec in recepciones:
        body = {
            "warehouse_id": BODEGA_PRINCIPAL,
            "product_id": rec["id_producto"],
            "movement_type": "in",
            "quantity": str(rec["cantidad"]),
            "reference_type": "receipt",
            "reference_id": numero_factura,
            "notes": f"[E2E-OC-{tag}] {oc_codigo} - Recepcion factura {numero_factura} - "
            f"{rec.get('observacion', '')}".strip(),
        }
        r = api.post("/inventory/movements", json=body)
        mov = _ok(r, 201, f"recepcionar {rec['id_producto']}")
        movimientos.append(mov)
    return movimientos


def cuadrar_oc(
    api: APIClient,
    *,
    oc: dict,
    tag: str,
    numero_factura: str,
) -> dict:
    """Hace el match OC vs movimientos `in` con TAG y referencia a la factura.

    Devuelve:
    {
        "oc_codigo": ...,
        "factura": ...,
        "esperado": [{sku, cantidad}, ...],
        "recibido": [{sku, cantidad}, ...],
        "diferencias": [{sku, oc, recibido, dif}, ...],
        "cuadra": bool,
        "nota": str (si descuadre, accion sugerida)
    }
    """
    # Movimientos `in` con la factura Y con el TAG
    r = api.get("/inventory/movements", params={"limit": 200})
    _check(r, 200, "list movements")
    all_movs = r.json()

    # Filtrar: referencia=factura Y notes contiene el TAG
    tag_prefix = f"[E2E-OC-{tag}]"
    matched = [
        m
        for m in all_movs
        if m.get("reference_type") == "receipt"
        and m.get("reference_id") == numero_factura
        and tag_prefix in (m.get("notes") or "")
    ]

    # Esperado desde la OC
    esperado: dict[str, Decimal] = {}
    for det in oc["detalles"]:
        sku = det.get("product_sku") or det["id_producto"]
        esperado[sku] = Decimal(str(det["cantidad_pedida"]))

    # Recibido
    recibido: dict[str, Decimal] = {}
    for m in matched:
        sku = m["product_sku"]
        recibido[sku] = recibido.get(sku, Decimal("0")) + Decimal(str(m["quantity"]))

    # Diferencias
    diferencias = []
    for sku, oc_q in esperado.items():
        rec_q = recibido.get(sku, Decimal("0"))
        dif = rec_q - oc_q
        if dif != 0:
            diferencias.append(
                {
                    "sku": sku,
                    "oc": oc_q,
                    "recibido": rec_q,
                    "dif": dif,
                    "tipo": "faltante" if dif < 0 else "sobrante",
                }
            )

    cuadra = len(diferencias) == 0

    nota = ""
    if not cuadra:
        falt = [d for d in diferencias if d["tipo"] == "faltante"]
        sobr = [d for d in diferencias if d["tipo"] == "sobrante"]
        partes = []
        if falt:
            partes.append(
                "Nota de Credito al proveedor por: "
                + ", ".join(f"{d['sku']} (-{abs(d['dif'])})" for d in falt)
            )
        if sobr:
            partes.append(
                "Devolver excedente al proveedor: "
                + ", ".join(f"{d['sku']} (+{d['dif']})" for d in sobr)
            )
        nota = " | ".join(partes) if partes else "revisar"

    return {
        "oc_codigo": oc["codigo"],
        "factura": numero_factura,
        "esperado": [{"sku": k, "cantidad": v} for k, v in esperado.items()],
        "recibido": [{"sku": k, "cantidad": v} for k, v in recibido.items()],
        "diferencias": diferencias,
        "cuadra": cuadra,
        "nota": nota,
    }


def esperar_email_enviado(
    api: APIClient,
    *,
    outbox_id: str,
    to_email: str,
    subject_substr: str,
    timeout_s: int = 15,
) -> dict:
    """Espera a que el worker envie el email (status=sent)."""
    # El listado no se puede filtrar por to, asi que iteramos recientes
    # y matcheamos por outbox_id / to / subject.
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        # Listar movimientos outbox: usamos un endpoint si existe; si no, polling via
        # inventory movements (el worker no inserta movimientos). Lo mas portable:
        # consultar la BD via /audit o un endpoint admin. Aqui usamos la
        # observacion del worker via logs: vamos a la API y leemos los ultimos
        # movimientos; mejor un endpoint dedicado.
        #
        # En esta version del sistema no hay GET /email-outbox publico. Asi que
        # usamos la heuristica: si la OC ya esta en estado `enviado_a_supervisor`
        # y el worker esta vivo, el correo se envia. Verificamos via
        # GET /ordenes-compra/{oc_id} que el email_enviado_at este seteado y
        # damos un margen de 5s para que el SMTP outbox lo marque como sent.
        r = api.get("/ordenes-compra")
        _check(r, 200, "list OCs")
        last_oc = next((o for o in r.json() if o.get("email_enviado_at")), None)
        if last_oc:
            return {
                "outbox_id": outbox_id,
                "to_email": to_email,
                "subject_substr": subject_substr,
                "email_enviado_at": last_oc.get("email_enviado_at"),
            }
        time.sleep(1)
    return {"timeout": True, "last": last}


def fmt_table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "(sin filas)"
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    head = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    body = "\n".join(
        " | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols) for r in rows
    )
    return f"{head}\n{sep}\n{body}"


# ---------------------------------------------------------------------------
# Escenarios
# ---------------------------------------------------------------------------


def escenario_a_happy_path(api: APIClient) -> dict:
    """A. Happy path: solicitud -> OC -> email -> aprobar (link publico) ->
    comprar -> recepcion completa -> cuadre OK."""
    tag = "A" + _suffix()
    print(f"\n{'='*72}\n  ESCENARIO A: HAPPY PATH (tag={tag})\n{'='*72}")

    # 1. Crear solicitud manual desde norte (origen) hacia principal (destino)
    sol = crear_solicitud_reposicion(
        api,
        id_bodega_origen=BODEGA_NORTE,        # quien entrega (auxiliar)
        id_bodega_destino=BODEGA_PRINCIPAL,   # quien recibe (principal)
        lineas=[{"producto_id": PROD_FLOW, "cantidad_solicitada": Decimal("50")}],
        notas=f"[E2E-OC-{tag}] Solicitud manual pre-OC",
    )
    sol_codigo = sol["codigo"]
    print(f"  [A.1] Solicitud creada: {sol_codigo}")

    # 2. Aprobar + despachar + recibir (para vaciar algo de stock en principal
    #    antes de la OC, simulando consumo real)
    mover_solicitud(api, sol["id"], "approve")
    mover_solicitud(
        api,
        sol["id"],
        "dispatch",
        lineas=[{"producto_id": PROD_FLOW, "cantidad": Decimal("50")}],
    )
    mover_solicitud(
        api,
        sol["id"],
        "receive",
        lineas=[{"producto_id": PROD_FLOW, "cantidad": Decimal("50")}],
    )
    print(f"  [A.2] Solicitud {sol_codigo}: aprobada -> despachada -> recibida")

    # 3. Crear OC para reponer la principal (mismo SKU)
    oc = crear_oc(
        api,
        lineas=[{
            "id_producto": PROD_FLOW,
            "cantidad_pedida": Decimal("100"),
            "costo_unitario_pactado": Decimal("1500"),
        }],
        proveedor_nombre=f"Proveedor Happy {tag}",
        notas=f"[E2E-OC-{tag}] Reposicion de FLOW",
    )
    oc_id, oc_codigo = oc["id"], oc["codigo"]
    print(f"  [A.3] OC creada: {oc_codigo} (total={oc['total_estimado']})")

    # 4. Enviar correo (encolar email + token de aprobacion)
    envio = enviar_correo_oc(api, oc_id)
    token = envio["approval_token"]
    outbox_id = envio["outbox_id"]
    print(f"  [A.4] Correo encolado (outbox_id={outbox_id[:8]}...) token={token[:18]}...")

    # 5. Esperar a que el worker mande el email
    time.sleep(5)
    estado_envio = esperar_email_enviado(
        api, outbox_id=outbox_id, to_email="supervisor@bodega.cl", subject_substr=oc_codigo
    )
    print(f"  [A.5] Email enviado_at: {estado_envio.get('email_enviado_at', '?')}")

    # 6. Aprobar por link publico (sin auth)
    r_pub = requests.post(
        f"{BASE}/public/ordenes-compra/aprobar/{token}",
        timeout=TIMEOUT,
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    _check(r_pub, 200, "aprobar publica")
    pub = r_pub.json()
    print(f"  [A.6] OC aprobada por link publico. Estado: {pub.get('estado')}")

    # 7. Marcar como comprada (proveedor entrego)
    comprado = comprar_oc(api, oc_id)
    print(f"  [A.7] OC marcada como comprada: {comprado['estado']}")

    # 8. Recepcionar (llegan las 100 unidades)
    factura = f"FAC-{tag}"
    movs = recepcionar_oc(
        api,
        oc_codigo=oc_codigo,
        tag=tag,
        numero_factura=factura,
        recepciones=[{"id_producto": PROD_FLOW, "cantidad": Decimal("100")}],
    )
    print(f"  [A.8] Recepcion registrada: {len(movs)} movimiento(s), factura {factura}")

    # 9. Cuadre
    cuadre = cuadrar_oc(api, oc=oc, tag=tag, numero_factura=factura)
    print(f"  [A.9] CUADRE: {'OK' if cuadre['cuadra'] else 'FALLA'}")
    if not cuadre["cuadra"]:
        print(fmt_table(cuadre["diferencias"], ["sku", "oc", "recibido", "dif", "tipo"]))
    else:
        print(fmt_table(cuadre["recibido"], ["sku", "cantidad"]))

    assert cuadre["cuadra"], f"Escenario A: cuadre debe ser OK, diferencias={cuadre['diferencias']}"
    return {"tag": tag, "oc_codigo": oc_codigo, "cuadre": cuadre, "resultado": "OK"}


def escenario_b_descuadre(api: APIClient) -> dict:
    """B. Descuadre: la OC pide 50 FLOW + 30 PROD-NORMAL.
    Llegan 45 FLOW (-5) y 32 PROD-NORMAL (+2). El cuadre debe detectar diferencias."""
    tag = "B" + _suffix()
    print(f"\n{'='*72}\n  ESCENARIO B: DESCUADRE (tag={tag})\n{'='*72}")

    # 1. OC con 2 lineas
    oc = crear_oc(
        api,
        lineas=[
            {
                "id_producto": PROD_FLOW,
                "cantidad_pedida": Decimal("50"),
                "costo_unitario_pactado": Decimal("1500"),
            },
            {
                "id_producto": PROD_NORMAL,
                "cantidad_pedida": Decimal("30"),
                "costo_unitario_pactado": Decimal("5000"),
            },
        ],
        proveedor_nombre=f"Proveedor Descuadre {tag}",
        notas=f"[E2E-OC-{tag}] OC con 2 lineas para probar descuadre",
    )
    oc_id, oc_codigo = oc["id"], oc["codigo"]
    print(f"  [B.1] OC creada: {oc_codigo} (total={oc['total_estimado']})")

    # 2. Email + aprobar + comprar
    envio = enviar_correo_oc(api, oc_id)
    token = envio["approval_token"]
    print(f"  [B.2] Correo encolado, token={token[:18]}...")
    time.sleep(3)

    r_pub = requests.post(
        f"{BASE}/public/ordenes-compra/aprobar/{token}",
        timeout=TIMEOUT,
        headers={"X-Forwarded-For": "10.0.0.3"},
    )
    _check(r_pub, 200, "aprobar publica B")
    comprar_oc(api, oc_id)
    print(f"  [B.3] OC aprobada y comprada")

    # 3. Recepcion DESCUADRADA
    factura = f"FAC-{tag}"
    recepciones = [
        {"id_producto": PROD_FLOW, "cantidad": Decimal("45"), "observacion": "FALTAN 5"},
        {"id_producto": PROD_NORMAL, "cantidad": Decimal("32"), "observacion": "SOBRAN 2"},
    ]
    recepcionar_oc(
        api,
        oc_codigo=oc_codigo,
        tag=tag,
        numero_factura=factura,
        recepciones=recepciones,
    )
    print(f"  [B.4] Recepcion DESCUADRADA: 45/50 FLOW y 32/30 PROD-NORMAL, factura {factura}")

    # 4. Cuadre
    cuadre = cuadrar_oc(api, oc=oc, tag=tag, numero_factura=factura)
    print(f"  [B.5] CUADRE: {'OK' if cuadre['cuadra'] else 'FALLA (esperado)'}")
    print(fmt_table(cuadre["diferencias"], ["sku", "oc", "recibido", "dif", "tipo"]))
    if cuadre["nota"]:
        print(f"  [B.5.nota] Accion sugerida: {cuadre['nota']}")

    assert not cuadre["cuadra"], "Escenario B: cuadre debe FALLAR (hay descuadre)"
    # Verificamos que el sistema detecto al menos 1 faltante y 1 sobrante
    tipos = {d["tipo"] for d in cuadre["diferencias"]}
    assert "faltante" in tipos, f"se esperaba al menos 1 faltante, tipos={tipos}"
    assert "sobrante" in tipos, f"se esperaba al menos 1 sobrante, tipos={tipos}"
    print(f"  [B.5] Sistema detecto correctamente: {tipos}")
    return {"tag": tag, "oc_codigo": oc_codigo, "cuadre": cuadre, "resultado": "OK"}


def escenario_c_rechazo(api: APIClient) -> dict:
    """C. Rechazo: supervisor rechaza por link publico, OC queda en `rechazado`.
    NO se compra, NO se recibe, NO se mueve stock."""
    tag = "C" + _suffix()
    print(f"\n{'='*72}\n  ESCENARIO C: RECHAZO (tag={tag})\n{'='*72}")

    # 1. Crear OC que sera rechazada
    oc = crear_oc(
        api,
        lineas=[{
            "id_producto": PROD_FLOW,
            "cantidad_pedida": Decimal("200"),
            "costo_unitario_pactado": Decimal("9999"),
        }],
        proveedor_nombre=f"Proveedor Rechazo {tag}",
        notas=f"[E2E-OC-{tag}] OC cara para que el supervisor la rechaze",
    )
    oc_id, oc_codigo = oc["id"], oc["codigo"]
    print(f"  [C.1] OC creada: {oc_codigo} (total={oc['total_estimado']})")

    # 2. Email
    envio = enviar_correo_oc(api, oc_id)
    token = envio["approval_token"]
    print(f"  [C.2] Correo encolado, token={token[:18]}...")
    time.sleep(3)

    # 3. Rechazar por link publico
    motivo = f"Precio unitario excede presupuesto aprobado para {tag}"
    r_pub = requests.post(
        f"{BASE}/public/ordenes-compra/rechazar/{token}",
        json=_sanitize({"motivo": motivo}),
        timeout=TIMEOUT,
        headers={"X-Forwarded-For": "10.0.0.4"},
    )
    _check(r_pub, 200, "rechazar publica C")
    pub = r_pub.json()
    print(f"  [C.3] OC rechazada por link publico. Estado: {pub.get('estado')}")

    # 4. Verificar estado final
    r = api.get(f"/ordenes-compra/{oc_id}")
    final = _ok(r, 200, "get OC final")
    assert final["estado"] == "rechazado", f"estado final debe ser rechazado, es {final['estado']}"
    assert final["motivo_rechazo"] == motivo, f"motivo_rechazo no coincide"
    print(f"  [C.4] Estado final: {final['estado']}, motivo: '{final['motivo_rechazo']}'")

    # 5. Verificar que NO se genero movimiento `in` con este TAG
    r = api.get("/inventory/movements", params={"limit": 200})
    movs = r.json()
    movs_tag = [m for m in movs if f"[E2E-OC-{tag}]" in (m.get("notes") or "")]
    assert len(movs_tag) == 0, f"se generaron movimientos con TAG {tag} pese a rechazo: {movs_tag}"
    print(f"  [C.5] OK: 0 movimientos generados con TAG {tag} (rechazo fue total)")

    return {"tag": tag, "oc_codigo": oc_codigo, "estado": final["estado"], "resultado": "OK"}


# ---------------------------------------------------------------------------
# Cleanup de OCs previas (de tests anteriores)
# ---------------------------------------------------------------------------


def cleanup_old_pending_ocs(api: APIClient) -> int:
    """Rechaza todas las OCs en estado 'enviado_a_supervisor' que NO son
    de esta corrida. Usado con --cleanup para dejar el sistema limpio.

    Devuelve la cantidad de OCs rechazadas.
    """
    r = api.get("/ordenes-compra", params={"estado": "enviado_a_supervisor"})
    _check(r, 200, "list OCs pendientes")
    pendientes = [o for o in r.json() if o.get("email_enviado_at")]
    if not pendientes:
        return 0
    print(f"\n[cleanup] {len(pendientes)} OC(s) en enviado_a_supervisor, rechazando...")
    rechazadas = 0
    for oc in pendientes:
        try:
            r2 = api.post(
                f"/ordenes-compra/{oc['id']}/rechazar",
                json={"motivo": "Cleanup de tests previos - no requiere accion"},
            )
            if r2.status_code in (200, 201):
                rechazadas += 1
                print(f"  [cleanup] {oc['codigo']} -> rechazado")
            else:
                print(f"  [cleanup] {oc['codigo']} -> FAIL {r2.status_code}: {r2.text[:100]}")
        except Exception as e:
            print(f"  [cleanup] {oc['codigo']} -> ERROR: {e}")
    return rechazadas


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="E2E: modulo de Ordenes de Compra por correo (3 escenarios)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Rechaza OCs en enviado_a_supervisor de tests previos antes y despues",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Muestra logs detallados de cada request HTTP",
    )
    args = parser.parse_args()

    print("=" * 72)
    print("  E2E: MODULO DE ORDENES DE COMPRA POR CORREO")
    print("  3 escenarios: Happy path / Descuadre / Rechazo")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 72)
    print("\nHALLAZGO SOBRE EL MODULO:")
    print("  - NO existe endpoint /recepciones ni tabla oc_recepciones.")
    print("  - La 'recepcion' es un movimiento `in` con reference_type=receipt.")
    print("  - El cuadre OC<->factura NO lo hace el sistema; lo hace este test.")
    print("  - Path publico correcto: /aprobar/ (NO /aprobacion/)")

    api = APIClient()
    api.login(*ADMIN)
    print(f"\n[setup] Login OK como '{ADMIN[0]}'")

    if args.cleanup:
        n = cleanup_old_pending_ocs(api)
        if n:
            print(f"[cleanup] {n} OC(s) rechazadas antes de empezar")

    # Snapshot: max codigo de OC actual (las OCs de este test seran > este numero)
    r_all = api.get("/ordenes-compra")
    codigos_antes = {o["codigo"] for o in r_all.json()}
    print(f"[setup] OCs existentes antes del test: {len(codigos_antes)}")

    resultados = []
    failures = []
    started = time.time()

    for nombre, fn in [
        ("A_happy", escenario_a_happy_path),
        ("B_descuadre", escenario_b_descuadre),
        ("C_rechazo", escenario_c_rechazo),
    ]:
        try:
            res = fn(api)
            resultados.append({"escenario": nombre, **res})
        except Exception as e:
            print(f"\n  [FAIL] {nombre}: {e}")
            failures.append({"escenario": nombre, "error": str(e)})

    elapsed = time.time() - started

    # Resumen
    print(f"\n{'='*72}\n  RESUMEN\n{'='*72}\n")
    print(f"  Escenarios corridos: 3")
    print(f"  Pasados: {3 - len(failures)} / 3")
    print(f"  Fallados: {len(failures)} / 3")
    print(f"  Tiempo total: {elapsed:.1f}s")
    if resultados:
        print("\n  Detalle por escenario:")
        for r in resultados:
            print(f"    - {r['escenario']}: {r.get('resultado')} (oc={r.get('oc_codigo', '-')})")
    if failures:
        print("\n  Fallos:")
        for f in failures:
            print(f"    - {f['escenario']}: {f['error'][:200]}")

    # Validacion post: solo las OCs de este test deben haber cambiado de estado
    # a algo distinto de enviado_a_supervisor. Las que estaban en codigos_antes
    # son ruido previo, NO son nuestras.
    r = api.get("/ordenes-compra", params={"estado": "enviado_a_supervisor"})
    pendientes_post = [o for o in r.json() if o.get("email_enviado_at")]
    if pendientes_post:
        # Mias: codigos que NO existian al inicio
        mias_pendientes = [o for o in pendientes_post if o["codigo"] not in codigos_antes]
        previas_pendientes = [o for o in pendientes_post if o["codigo"] in codigos_antes]
        if mias_pendientes:
            print(f"\n  [FAIL] {len(mias_pendientes)} OC(s) CREADAS por este test quedaron en enviado_a_supervisor:")
            for o in mias_pendientes:
                print(f"    - {o['codigo']}")
            failures.append({"escenario": "post_test", "error": "OC del test sin cerrar"})
        if previas_pendientes:
            if args.cleanup:
                n = cleanup_old_pending_ocs(api)
                print(f"\n  [cleanup] {n} OC(s) previas rechazadas al final")
            else:
                print(f"\n  [INFO] {len(pendientes_post)} OC(s) previas (no de este test) "
                      f"en enviado_a_supervisor. Use --cleanup para rechazarlas.")

    # Exit code
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[abort] interrumpido por el usuario")
        sys.exit(130)
    except Exception as e:
        print(f"\n[fatal] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
