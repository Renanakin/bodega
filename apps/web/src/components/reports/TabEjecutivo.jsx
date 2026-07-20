// Tab "Ejecutivo" de la pagina de Reports.
// Snapshot ejecutivo: KPIs, top productos, valor por bodega, export PDF.
import { useCallback, useEffect, useState } from "react";
import { getErrorMessage, getJson } from "../../lib/api";
import { useUi } from "../../context/UiContext";
import { downloadEjecutivoPDF, ESTADO_COLOR, formatCLP, formatFecha, formatNum } from "./helpers";

export function TabEjecutivo() {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { pushToast } = useUi();

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJson("/reports/ejecutivo");
      setSnapshot(data);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar el reporte ejecutivo."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (loading) {
    return <p className="text-sm text-slate-500">Generando snapshot ejecutivo...</p>;
  }
  if (error) {
    return (
      <p className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
        Error: {error}
      </p>
    );
  }
  if (!snapshot) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-slate-500">
          Generado: {formatFecha(snapshot.generado_en)}
        </p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={cargar}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Refrescar
          </button>
          <button
            type="button"
            onClick={() => downloadEjecutivoPDF(snapshot)}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
          >
            Descargar Reporte Ejecutivo (PDF)
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Stock total valorizado
          </p>
          <p className="mt-1 text-2xl font-bold text-slate-900">
            {formatCLP(snapshot.stock_total_activo_valorizado)}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Alertas criticas
          </p>
          <p
            className={`mt-1 text-2xl font-bold ${
              snapshot.alertas_criticas_count > 0 ? "text-rose-700" : "text-slate-900"
            }`}
          >
            {snapshot.alertas_criticas_count}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Transferencias en ruta
          </p>
          <p className="mt-1 text-2xl font-bold text-sky-700">
            {snapshot.transferencias_en_ruta_count}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Productos activos
          </p>
          <p className="mt-1 text-2xl font-bold text-slate-900">
            {snapshot.total_productos_activos}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Bodegas activas
          </p>
          <p className="mt-1 text-2xl font-bold text-slate-900">
            {snapshot.total_bodegas}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Solicitudes por estado
          </p>
          <ul className="mt-1 space-y-0.5 text-sm">
            {Object.entries(snapshot.solicitudes_por_estado || {}).map(([estado, count]) => (
              <li key={estado} className="flex items-center gap-2">
                <span
                  className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${
                    ESTADO_COLOR[estado] || "bg-slate-100 text-slate-700"
                  }`}
                >
                  {estado}
                </span>
                <span className="text-slate-700">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">
            Top productos mas movidos
          </h3>
          <div className="mt-2 overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-2 py-1">SKU</th>
                  <th className="px-2 py-1">Producto</th>
                  <th className="px-2 py-1 text-right">Unidades</th>
                  <th className="px-2 py-1 text-right">Movs</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {snapshot.top_productos_mas_movidos.map((p) => (
                  <tr key={p.producto_id}>
                    <td className="px-2 py-1 font-mono text-xs">{p.sku}</td>
                    <td className="px-2 py-1 text-slate-700">{p.nombre}</td>
                    <td className="px-2 py-1 text-right">{formatNum(p.unidades_movidas)}</td>
                    <td className="px-2 py-1 text-right">{p.movimientos_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800">
            Top productos menos movidos
          </h3>
          <div className="mt-2 overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-2 py-1">SKU</th>
                  <th className="px-2 py-1">Producto</th>
                  <th className="px-2 py-1 text-right">Unidades</th>
                  <th className="px-2 py-1 text-right">Movs</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {snapshot.top_productos_menos_movidos.map((p) => (
                  <tr key={p.producto_id}>
                    <td className="px-2 py-1 font-mono text-xs">{p.sku}</td>
                    <td className="px-2 py-1 text-slate-700">{p.nombre}</td>
                    <td className="px-2 py-1 text-right">{formatNum(p.unidades_movidas)}</td>
                    <td className="px-2 py-1 text-right">{p.movimientos_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-800">Valor por bodega</h3>
        <div className="mt-2 overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                <th className="px-3 py-2">Codigo</th>
                <th className="px-3 py-2">Nombre</th>
                <th className="px-3 py-2">Tipo</th>
                <th className="px-3 py-2 text-right">Unidades</th>
                <th className="px-3 py-2 text-right">Valor CLP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {snapshot.valor_por_bodega.map((b) => (
                <tr key={b.bodega_id}>
                  <td className="px-3 py-1.5 font-mono text-xs">{b.bodega_code}</td>
                  <td className="px-3 py-1.5 text-slate-700">{b.bodega_name}</td>
                  <td className="px-3 py-1.5 text-slate-600">{b.bodega_type}</td>
                  <td className="px-3 py-1.5 text-right">{formatNum(b.unidades_total)}</td>
                  <td className="px-3 py-1.5 text-right font-semibold">
                    {formatCLP(b.valor_total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
