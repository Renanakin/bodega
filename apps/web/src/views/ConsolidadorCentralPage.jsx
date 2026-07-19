// ConsolidadorCentralPage: detecta quiebres que la Bodega Principal no puede
// cubrir y permite crear una OC consolidada (Fase 6).
//
// Ruta: /consolidador
//
// Reglas:
// - Carga solicitudes en estados que consumen stock de la Principal:
//   `pending`, `approved`, `in_transit`.
// - Agrupa lineas por producto y suma cantidades solicitadas = demanda.
// - Compara con stock disponible en Principal (StockLevel.quantity).
// - Si demanda > stock disponible => deficit => "Requiere compra".
// - Boton "Crear OC desde este deficit" navega a /ordenes-compra con un
//   prefill via location state (NuevaOCForm se auto-rellena).
// - Disenada 100% con Tailwind v3 (sin CSS plano legacy).
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getErrorMessage, getJson } from "../lib/api";

const ESTADOS_CONSUMEN = ["pending", "approved", "in_transit"];

function formatCantidad(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 });
}

export function ConsolidadorCentralPage() {
  const navigate = useNavigate();

  const [quiebres, setQuiebres] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [solicitudesIncluidas, setSolicitudesIncluidas] = useState(0);

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Cargar solicitudes que consumen stock de Principal
      const params = new URLSearchParams();
      ESTADOS_CONSUMEN.forEach((e) => params.append("estado", e));
      params.set("limit", "500");
      const solicitudes = await getJson(`/solicitudes?${params.toString()}`);

      // 2. Cargar bodegas para encontrar la principal
      const bodegas = await getJson("/warehouses");
      const bodegaPrincipal = (Array.isArray(bodegas) ? bodegas : []).find(
        (b) => b.warehouse_type === "principal",
      );

      if (!bodegaPrincipal) {
        setQuiebres([]);
        setSolicitudesIncluidas(0);
        return;
      }

      // 3. Cargar stock real de Principal
      const stockList = await getJson(
        `/inventario/real?warehouse_id=${bodegaPrincipal.id}`,
      );
      const stockPorProducto = new Map();
      for (const s of stockList || []) {
        // El backend expone `bodega_id` en la respuesta (snake_case de
        // la BD legacy). Mapeamos el stock por producto.
        stockPorProducto.set(s.producto_id, Number(s.quantity || 0));
      }

      // 4. Cargar catalogo de productos (para sku/nombre)
      // El endpoint actual de products NO filtra por is_active, asi que
      // se asume que la operacion normal mantiene productos inactivos
      // fuera del flujo.
      const productos = await getJson("/products");
      const productoPorId = new Map();
      for (const p of productos || []) {
        productoPorId.set(p.id, p);
      }

      // 5. Agregar demanda por producto (suma de todas las lineas)
      const demandaPorProducto = new Map();
      for (const sol of solicitudes || []) {
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

      // 6. Calcular deficit
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
      setSolicitudesIncluidas((solicitudes || []).length);
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
      id_bodega_principal: null, // se resuelve en el form con la lista de bodegas
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
            Productos con solicitudes activas cuya demanda agregada supera
            el stock disponible en la Bodega Principal. Cada fila marcada
            en rojo representa un deficit que requiere compra externa.
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
              El consolidador se actualiza cada vez que se crean o
              aprueban solicitudes nuevas.
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
        . Demanda = suma de cantidades en solicitudes en estado{" "}
        <code className="rounded bg-slate-100 px-1">pending</code>,{" "}
        <code className="rounded bg-slate-100 px-1">approved</code> o{" "}
        <code className="rounded bg-slate-100 px-1">in_transit</code>. Stock
        se lee de{" "}
        <code className="rounded bg-slate-100 px-1">stock_levels.quantity</code>{" "}
        en la Bodega Principal.
      </p>
    </div>
  );
}
