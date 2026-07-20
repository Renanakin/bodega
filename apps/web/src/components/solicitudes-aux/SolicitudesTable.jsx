// Tabla de solicitudes de recarga con paginacion.
import { COLOR_ESTADO, COLOR_PRIORIDAD, ETIQUETA_ESTADO, PAGE_SIZE } from "./constants";
import { formatFecha, formatNum } from "./formatters";

export function SolicitudesTable({
  loading,
  error,
  total,
  itemsPagina,
  abrirDetalle,
  setSkip,
  skip,
}) {
  if (loading) {
    return <p className="p-6 text-sm text-slate-500">Cargando solicitudes...</p>;
  }
  if (error) {
    return <p className="p-6 text-sm text-rose-600">Error: {error}</p>;
  }
  if (total === 0) {
    return (
      <div className="p-8 text-center">
        <p className="text-base font-semibold text-slate-700">
          No hay solicitudes con esos filtros
        </p>
        <p className="mt-1 text-sm text-slate-500">
          Prueba limpiando los filtros o espera la proxima corrida
          automatica del ReplenishmentEvaluator.
        </p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            <th className="px-4 py-2">Codigo</th>
            <th className="px-4 py-2">Estado</th>
            <th className="px-4 py-2">Origen</th>
            <th className="px-4 py-2">Destino</th>
            <th className="px-4 py-2 text-right"># Productos</th>
            <th className="px-4 py-2 text-right">Total unidades</th>
            <th className="px-4 py-2">Prioridad</th>
            <th className="px-4 py-2">Fecha</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {itemsPagina.map((s) => (
            <tr
              key={s.id}
              onClick={() => abrirDetalle(s.id)}
              className="cursor-pointer hover:bg-slate-50"
            >
              <td className="px-4 py-2 font-mono text-xs text-indigo-700">
                {s.codigo}
              </td>
              <td className="px-4 py-2">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                    COLOR_ESTADO[s.estado] || COLOR_ESTADO.pending
                  }`}
                >
                  {ETIQUETA_ESTADO[s.estado] || s.estado}
                </span>
              </td>
              <td className="px-4 py-2 font-mono text-xs text-slate-700">
                {s.bodega_origen_codigo}
              </td>
              <td className="px-4 py-2 font-mono text-xs text-slate-700">
                {s.bodega_destino_codigo}
              </td>
              <td className="px-4 py-2 text-right text-slate-700">
                {s.total_productos}
              </td>
              <td className="px-4 py-2 text-right text-slate-700">
                {formatNum(s.total_unidades)}
              </td>
              <td
                className={`px-4 py-2 ${
                  COLOR_PRIORIDAD[s.prioridad] || COLOR_PRIORIDAD.normal
                }`}
              >
                {s.prioridad || "normal"}
              </td>
              <td className="px-4 py-2 text-xs text-slate-500">
                {formatFecha(s.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center justify-between border-t border-slate-200 px-4 py-2 text-xs text-slate-500">
        <span>
          Mostrando {itemsPagina.length} de {total} (max 200)
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
            disabled={skip === 0}
            className="rounded border border-slate-300 bg-white px-2 py-1 disabled:opacity-50"
          >
            Anterior
          </button>
          <button
            type="button"
            onClick={() => setSkip(skip + PAGE_SIZE)}
            disabled={skip + PAGE_SIZE >= total}
            className="rounded border border-slate-300 bg-white px-2 py-1 disabled:opacity-50"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
