// ConsolidadorCentralPage: detecta quiebres que la Bodega Principal no puede
// cubrir y permite crear una OC consolidada (Fase 6).
//
// Ruta: /consolidador
//
// Reglas:
// - Carga solicitudes en estados que consumen stock de la Principal:
//   `pending`, `approved`, `in_transit`.
// - BUG 6 (fix 2026-07-22): filtra ademas por origen == bodega principal
//   activa. Una solicitud donde origen != principal (ej. auxiliar -> otra
//   auxiliar, o auxiliar -> principal como devolucion) NO consume stock
//   de la principal y por tanto no genera deficit para el consolidador.
// - Toma la bodega principal que este activa y tenga nombre consistente
//   con el dominio (Bodega Central / Principal). Si hay varias marcadas
//   como principal, prioriza is_active=true y luego la de mayor stock.
// - Agrupa lineas por producto y suma cantidades solicitadas = demanda.
// - Compara con stock disponible en Principal (StockLevel.quantity).
// - Si demanda > stock disponible => deficit => "Requiere compra".
// - Boton "Crear OC desde este deficit" navega a /ordenes-compra con un
//   prefill via location state (NuevaOCForm se auto-rellena).
// - Disenada 100% con Tailwind v3 (sin CSS plano legacy).
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getErrorMessage, getJson } from "../lib/api";

// Estados que comprometen stock futuro de la principal.
const ESTADOS_CONSUMEN = ["pending", "approved", "in_transit"];

function formatCantidad(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 });
}

/**
 * Elige la bodega principal de forma robusta cuando hay varias marcadas
 * como ``warehouse_type=principal`` (caso comun en seeds de test o
 * estados heredados). Prioriza:
 * 1) is_active=true
 * 2) nombre que parezca "principal"/"central" (heuristica)
 * 3) mayor stock_levels.quantity agregado (si esta disponible)
 * 4) primera del listado como ultimo recurso
 */
function elegirBodegaPrincipal(bodegas, stockPorBodega = new Map()) {
  if (!Array.isArray(bodegas) || bodegas.length === 0) return null;
  const principales = bodegas.filter((b) => b.warehouse_type === "principal");
  if (principales.length === 0) return null;
  if (principales.length === 1) return principales[0];

  const ordenadas = [...principales].sort((a, b) => {
    if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
    const aLooks = /principal|central/i.test(a.name || "") ? 1 : 0;
    const bLooks = /principal|central/i.test(b.name || "") ? 1 : 0;
    if (aLooks !== bLooks) return bLooks - aLooks;
    const aStock = stockPorBodega.get(a.id) || 0;
    const bStock = stockPorBodega.get(b.id) || 0;
    return bStock - aStock;
  });
  return ordenadas[0];
}

export function ConsolidadorCentralPage() {
  const navigate = useNavigate();

  const [quiebres, setQuiebres] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [solicitudesIncluidas, setSolicitudesIncluidas] = useState(0);
  const [bodegaPrincipal, setBodegaPrincipal] = useState(null);
  const [warning, setWarning] = useState("");

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    setWarning("");
    try {
      // 1. Cargar solicitudes en estados que consumen stock futuro.
      // NOTA: limit=1000 debe coincidir con el ``le=1000`` del router
      // backend (GET /solicitudes). El cap se subio para soportar este
      // reporte agregado: si la operacion crece mas alla, se debera
      // agregar paginacion o un endpoint dedicado tipo
      // GET /solicitudes/todas que devuelva el agregado.
      const params = new URLSearchParams();
      ESTADOS_CONSUMEN.forEach((e) => params.append("estado", e));
      params.set("limit", "1000");
      const solicitudes = await getJson(`/solicitudes?${params.toString()}`);

      // 2. Cargar bodegas y stock agregado por bodega en paralelo.
      // El stock lo agregamos en cliente por bodega_id para alimentar la
      // heuristica de eleccion de principal.
      const [bodegas, stockList] = await Promise.all([
        getJson("/warehouses"),
        getJson("/inventario/real").catch(() => []),
      ]);
      const stockPorBodega = new Map();
      for (const s of stockList || []) {
        const prev = stockPorBodega.get(s.bodega_id) || 0;
        stockPorBodega.set(s.bodega_id, prev + Number(s.quantity || 0));
      }
      const principal = elegirBodegaPrincipal(bodegas, stockPorBodega);
      setBodegaPrincipal(principal);

      if (!principal) {
        setQuiebres([]);
        setSolicitudesIncluidas(0);
        setWarning(
          "No hay bodega marcada como 'principal'. Crea una para usar el consolidador.",
        );
        return;
      }

      // 3. Filtrar solicitudes: en este sistema, bodega_origen es la
      // bodega que RECIBE stock y bodega_destino es la que ENTREGA.
      // El backend rechaza con 400 "invalid_solicitud_direction" si
      // origen es principal. Esto significa que las recargas se modelan
      // como origen=auxiliar, destino=principal (la principal entrega).
      // Por tanto, las solicitudes que comprometen stock de la principal
      // son las que tienen bodega_destino_id == principal.id.
      //
      // Esta es la inversa de la convencion SQL comun ("origen = el
      // que emite"). En el dominio, "origen" semantica es "donde se
      // origina la necesidad" (la auxiliar), no "donde sale el stock".
      const solicitudesQueEntregan = (solicitudes || []).filter(
        (s) => s.bodega_destino_id === principal.id,
      );
      const solicitudesQueReciben = (solicitudes || []).filter(
        (s) => s.bodega_origen_id === principal.id,
      );
      // Para el contador "Solicitudes analizadas" mostramos el total
      // de solicitudes que tocan la principal (en cualquier direccion).
      const solicitudesQueTocanPrincipal = (solicitudes || []).filter(
        (s) =>
          s.bodega_origen_id === principal.id ||
          s.bodega_destino_id === principal.id,
      );

      // Warning si habia varias bodegas principales para que el operador
      // sepa cual se eligio (en vez de mostrarlo silenciosamente).
      const candidatos = (bodegas || []).filter(
        (b) => b.warehouse_type === "principal",
      );
      if (candidatos.length > 1) {
        const otras = candidatos
          .filter((b) => b.id !== principal.id)
          .map((b) => `${b.code}${b.is_active ? "" : " (INACTIVA)"}`)
          .join(", ");
        setWarning(
          `Hay ${candidatos.length} bodegas marcadas como principal; se usa "${principal.code}". Otras ignoradas: ${otras}.`,
        );
      }

      // 4. Stock disponible por producto en la principal
      const stockPorProducto = new Map();
      for (const s of stockList || []) {
        if (s.bodega_id === principal.id) {
          stockPorProducto.set(s.producto_id, Number(s.quantity || 0));
        }
      }

      // 5. Catalogo de productos (para sku/nombre)
      const productos = await getJson("/products");
      const productoPorId = new Map();
      for (const p of productos || []) {
        productoPorId.set(p.id, p);
      }

      // 6. Agregar demanda por producto (suma de las lineas de las
      // solicitudes que la principal debe ENTREGAR).
      const demandaPorProducto = new Map();
      for (const sol of solicitudesQueEntregan) {
        for (const d of sol.lineas || []) {
          if (Number(d.cantidad_solicitada) > 0) {
            const prev = demandaPorProducto.get(d.producto_id) || 0;
            demandaPorProducto.set(
              d.producto_id,
              prev + Number(d.cantidad_solicitada),
            );
          }
        }
      }

      // 7. Calcular deficit
      const items = [];
      for (const [productoId, demanda] of demandaPorProducto.entries()) {
        const stock = stockPorProducto.get(productoId) || 0;
        const prod = productoPorId.get(productoId) || {};
        const deficit = Math.max(0, demanda - stock);
        items.push({
          producto_id: productoId,
          sku: prod.sku || productoId.slice(0, 8),
          nombre: prod.name || "(producto)",
          demanda_total: demanda,
          stock_disponible: stock,
          deficit,
        });
      }
      // Ordenar por deficit descendente
      items.sort((a, b) => b.deficit - a.deficit);

      setQuiebres(items);
      setSolicitudesIncluidas(solicitudesQueTocanPrincipal.length);
      // Mantenemos las variables calculadas disponibles para futuros
      // reportes (info de entrada vs salida de stock).
      void solicitudesQueReciben;
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo consolidar quiebres."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const totalQuiebres = quiebres.length;
  const totalConDeficit = quiebres.filter((q) => q.deficit > 0).length;
  const totalUnidadesFaltantes = useMemo(
    () => quiebres.reduce((acc, q) => acc + q.deficit, 0),
    [quiebres],
  );

  const crearOC = (quibre) => {
    // Navega a /ordenes-compra con prefill via location state
    const prefill = {
      id_bodega_principal: bodegaPrincipal?.id || null,
      id_supervisor: "",
      proveedor_nombre: "",
      proveedor_contacto: "",
      notas: `Generada desde Consolidador (deficit ${formatCantidad(quibre.deficit)}).`,
      lineas: [
        {
          id_producto: quibre.producto_id,
          cantidad_pedida: quibre.deficit,
          costo_unitario_pactado: 0,
        },
      ],
    };
    navigate("/ordenes-compra", { state: { prefill, abrirDrawer: true } });
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Plan de compras
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Consolidador de Quiebres
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Productos con solicitudes activas que la Bodega Principal
            debe surtir. La demanda se calcula como la suma de cantidades
            en solicitudes donde la principal es destino (entrega stock);
            las solicitudes donde la principal es origen (recibe stock)
            no cuentan como consumo futuro. Cada fila marcada en rojo
            representa un deficit que requiere compra externa.
            {bodegaPrincipal
              ? ` Bodega principal usada: ${bodegaPrincipal.code} - ${bodegaPrincipal.name}.`
              : null}
          </p>
        </div>
        <button
          type="button"
          onClick={cargar}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
        >
          Refrescar
        </button>
      </header>

      {warning ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong className="font-semibold">Aviso:</strong> {warning}
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Solicitudes analizadas
          </p>
          <p className="mt-1 text-2xl font-bold text-slate-900">
            {solicitudesIncluidas}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            SKUs con deficit
          </p>
          <p className="mt-1 text-2xl font-bold text-rose-700">
            {totalConDeficit}{" "}
            <span className="text-sm font-normal text-slate-500">
              de {totalQuiebres}
            </span>
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Unidades faltantes (total)
          </p>
          <p className="mt-1 text-2xl font-bold text-rose-700">
            {formatCantidad(totalUnidadesFaltantes)}
          </p>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">Consolidando quiebres...</p>
        ) : error ? (
          <p className="p-6 text-sm text-rose-600">Error: {error}</p>
        ) : quiebres.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-base font-semibold text-slate-700">
              Sin solicitudes pendientes de despacho
            </p>
            <p className="mt-1 text-sm text-slate-500">
              {bodegaPrincipal
                ? `No hay solicitudes en estado pending/approved/in_transit que la ${bodegaPrincipal.code} deba surtir.`
                : "El consolidador se actualiza cada vez que se crean o aprueban solicitudes nuevas."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th scope="col" className="px-4 py-2">SKU</th>
                  <th scope="col" className="px-4 py-2">Producto</th>
                  <th scope="col" className="px-4 py-2 text-right">Demanda total</th>
                  <th scope="col" className="px-4 py-2 text-right">Stock disp.</th>
                  <th scope="col" className="px-4 py-2 text-right">Deficit</th>
                  <th scope="col" className="px-4 py-2 text-center">Estado</th>
                  <th scope="col" className="px-4 py-2 text-right">Accion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {quiebres.map((q) => (
                  <tr
                    key={q.producto_id}
                    className={q.deficit > 0 ? "bg-rose-50/30" : "hover:bg-slate-50"}
                  >
                    <td className="px-4 py-2 font-mono text-xs text-slate-600">
                      {q.sku}
                    </td>
                    <td className="px-4 py-2 text-slate-800">{q.nombre}</td>
                    <td className="px-4 py-2 text-right text-slate-700">
                      {formatCantidad(q.demanda_total)}
                    </td>
                    <td className="px-4 py-2 text-right text-slate-700">
                      {formatCantidad(q.stock_disponible)}
                    </td>
                    <td
                      className={`px-4 py-2 text-right font-semibold ${
                        q.deficit > 0 ? "text-rose-700" : "text-slate-500"
                      }`}
                    >
                      {formatCantidad(q.deficit)}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {q.deficit > 0 ? (
                        <span className="inline-flex items-center rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800 ring-1 ring-rose-300">
                          Requiere compra
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-300">
                          Cubierto
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {q.deficit > 0 ? (
                        <button
                          type="button"
                          onClick={() => crearOC(q)}
                          className="rounded border border-indigo-300 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                        >
                          Crear OC desde este deficit
                        </button>
                      ) : (
                        <span className="text-xs text-slate-400">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-500">
        Logica:{" "}
        <code className="rounded bg-slate-100 px-1">deficit = demanda_total - stock_disponible</code>
        . Demanda = suma de cantidades en solicitudes que la Bodega
        Principal debe ENTREGAR (destino = principal, origen = auxiliar
        o box) en estado{" "}
        <code className="rounded bg-slate-100 px-1">pending</code>,{" "}
        <code className="rounded bg-slate-100 px-1">approved</code> o{" "}
        <code className="rounded bg-slate-100 px-1">in_transit</code>.
        Stock se lee de{" "}
        <code className="rounded bg-slate-100 px-1">stock_levels.quantity</code>{" "}
        en la Bodega Principal.
      </p>
    </div>
  );
}
