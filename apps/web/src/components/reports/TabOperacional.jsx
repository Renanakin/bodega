// Tab "Operacional" de la pagina de Reports.
// Muestra historial de movimientos con filtros y exports CSV.
import { useMemo, useState } from "react";
import { downloadCsv } from "../../lib/export";
import { formatNum } from "./helpers";

export function TabOperacional({ stock, transfers, movements, warehouses, error, loading }) {
  const [skuFilter, setSkuFilter] = useState("");
  const [warehouseFilter, setWarehouseFilter] = useState("");
  const normalizedSku = skuFilter.trim().toLowerCase();
  const historyRows = useMemo(
    () =>
      movements.filter((item) => {
        const matchesSku = !normalizedSku || item.product_sku?.toLowerCase().includes(normalizedSku);
        const matchesWarehouse = !warehouseFilter || item.warehouse_id === warehouseFilter;
        return matchesSku && matchesWarehouse;
      }),
    [movements, normalizedSku, warehouseFilter],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() =>
            downloadCsv(
              "inventario.csv",
              [
                { key: "warehouse_name", label: "Bodega" },
                { key: "product_sku", label: "SKU" },
                { key: "product_name", label: "Producto" },
                { key: "quantity", label: "Stock" },
                { key: "min_quantity", label: "Minimo" },
              ],
              stock,
            )
          }
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Exportar inventario
        </button>
        <button
          type="button"
          onClick={() =>
            downloadCsv(
              "transferencias.csv",
              [
                { key: "code", label: "Codigo" },
                { key: "from_warehouse_name", label: "Origen" },
                { key: "to_warehouse_name", label: "Destino" },
                { key: "product_sku", label: "SKU" },
                { key: "quantity", label: "Solicitada" },
                { key: "received_quantity", label: "Recibida" },
                { key: "status", label: "Estado" },
              ],
              transfers,
            )
          }
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Exportar transferencias
        </button>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold text-slate-800">
          Historial de movimientos (filtrable)
        </h3>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            type="search"
            placeholder="Filtrar por SKU..."
            value={skuFilter}
            onChange={(e) => setSkuFilter(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            aria-label="Filtrar historial por SKU"
          />
          <select
            value={warehouseFilter}
            onChange={(e) => setWarehouseFilter(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            aria-label="Filtrar historial por bodega"
          >
            <option value="">Todas las bodegas</option>
            {warehouses.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() =>
              downloadCsv(
                "historial.csv",
                [
                  { key: "product_sku", label: "SKU" },
                  { key: "warehouse_code", label: "Bodega" },
                  { key: "movement_type", label: "Tipo" },
                  { key: "quantity", label: "Cantidad" },
                  { key: "reference_id", label: "Referencia" },
                  { key: "notes", label: "Detalle" },
                ],
                historyRows,
              )
            }
            className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Exportar historial
          </button>
        </div>
        {error ? (
          <p className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            Error: {error}
          </p>
        ) : loading ? (
          <p className="text-sm text-slate-500">Cargando...</p>
        ) : historyRows.length === 0 ? (
          <p className="text-sm text-slate-500">Sin movimientos para el filtro.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2">SKU</th>
                  <th className="px-3 py-2">Bodega</th>
                  <th className="px-3 py-2">Tipo</th>
                  <th className="px-3 py-2 text-right">Cantidad</th>
                  <th className="px-3 py-2">Referencia</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {historyRows.slice(0, 30).map((m, i) => (
                  <tr key={`${m.product_sku}-${i}`} className="hover:bg-slate-50">
                    <td className="px-3 py-1.5 font-mono text-xs text-slate-700">
                      {m.product_sku}
                    </td>
                    <td className="px-3 py-1.5 text-slate-700">{m.warehouse_code}</td>
                    <td className="px-3 py-1.5 text-slate-600">{m.movement_type}</td>
                    <td className="px-3 py-1.5 text-right text-slate-800">
                      {formatNum(m.quantity)}
                    </td>
                    <td className="px-3 py-1.5 text-slate-500">
                      {m.reference_id || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {historyRows.length > 30 ? (
              <p className="mt-2 text-xs text-slate-500">
                Mostrando 30 de {historyRows.length} — use el export CSV para ver todos.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
