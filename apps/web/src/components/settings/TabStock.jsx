// Tab "Parametros de Stock" de la pagina de Settings.
// Tabla de stock_levels con filtros por bodega y edicion inline de min.
import { useCallback, useEffect, useMemo, useState } from "react";
import { getErrorMessage, getJson, putJson } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { useUi } from "../../context/UiContext";

export function TabStock() {
  const { user } = useAuth();
  const { pushToast } = useUi();
  const [stockLevels, setStockLevels] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filtroBodega, setFiltroBodega] = useState("");
  const [busqueda, setBusqueda] = useState("");

  const esAdmin = user?.role === "admin" || user?.role === "supervisor";

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, w] = await Promise.all([getJson("/inventory/stock"), getJson("/warehouses")]);
      setStockLevels(Array.isArray(s) ? s : []);
      setWarehouses(Array.isArray(w) ? w : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar el stock."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const itemsFiltrados = useMemo(() => {
    return stockLevels.filter((s) => {
      if (filtroBodega && s.warehouse_id !== filtroBodega) return false;
      if (busqueda.trim()) {
        const q = busqueda.toLowerCase();
        if (
          !s.product_sku?.toLowerCase().includes(q) &&
          !s.product_name?.toLowerCase().includes(q)
        ) return false;
      }
      return true;
    });
  }, [stockLevels, filtroBodega, busqueda]);

  const updateMin = async (s, newMin) => {
    try {
      await putJson(
        `/inventory/parametros/${s.product_id}/${s.warehouse_id}`,
        {
          stock_minimo: Number(newMin),
          stock_maximo: Number(s.max_quantity || newMin),
          lead_time_dias: 7,
        },
      );
      pushToast({ tone: "success", title: "Minimo actualizado", description: s.product_sku });
      await cargar();
    } catch (err) {
      pushToast({ tone: "danger", title: "Error al actualizar", description: getErrorMessage(err) });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={filtroBodega}
          onChange={(e) => setFiltroBodega(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          aria-label="Filtrar por bodega"
        >
          <option value="">Todas las bodegas</option>
          {warehouses.map((w) => (
            <option key={w.id} value={w.id}>
              {w.code} &mdash; {w.name}
            </option>
          ))}
        </select>
        <input
          type="search"
          placeholder="Buscar SKU o nombre..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          className="flex-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          aria-label="Buscar stock"
        />
        <button
          type="button"
          onClick={cargar}
          className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Refrescar
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-4 text-sm text-slate-500">Cargando stock...</p>
        ) : error ? (
          <p className="p-4 text-sm text-rose-600">Error: {error}</p>
        ) : itemsFiltrados.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">
            Sin resultados para el filtro aplicado.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2">SKU</th>
                  <th className="px-3 py-2">Producto</th>
                  <th className="px-3 py-2">Bodega</th>
                  <th className="px-3 py-2 text-right">Stock</th>
                  <th className="px-3 py-2 text-right">Min (editable)</th>
                  <th className="px-3 py-2 text-center">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {itemsFiltrados.slice(0, 50).map((s) => {
                  const bajo = Number(s.min_quantity) > 0 && Number(s.quantity) <= Number(s.min_quantity);
                  return (
                    <tr key={`${s.warehouse_id}-${s.product_id}`} className="hover:bg-slate-50">
                      <td className="px-3 py-1.5 font-mono text-xs text-slate-700">
                        {s.product_sku}
                      </td>
                      <td className="px-3 py-1.5 text-slate-800">{s.product_name}</td>
                      <td className="px-3 py-1.5 text-slate-700">
                        <span className="font-mono text-xs">{s.warehouse_code}</span>
                      </td>
                      <td className="px-3 py-1.5 text-right font-semibold text-slate-800">
                        {s.quantity}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        {esAdmin ? (
                          <input
                            type="number"
                            min="0"
                            defaultValue={s.min_quantity}
                            onBlur={(e) => {
                              const val = e.target.value;
                              if (val !== String(s.min_quantity)) {
                                updateMin(s, val);
                              }
                            }}
                            className="w-20 rounded-md border border-slate-300 px-1 py-0.5 text-right text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                            aria-label={`Editar minimo de ${s.product_sku}`}
                          />
                        ) : (
                          <span className="text-slate-600">{s.min_quantity}</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-center">
                        {bajo ? (
                          <span className="inline-flex items-center rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800 ring-1 ring-rose-300">
                            Bajo minimo
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-300">
                            OK
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {itemsFiltrados.length > 50 ? (
              <p className="mt-2 px-3 text-xs text-slate-500">
                Mostrando 50 de {itemsFiltrados.length}.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
