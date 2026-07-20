// Barra de filtros para la pagina de Solicitudes de Recarga.
import { ESTADOS } from "./constants";

export function SolicitudesFilters({
  estadoFiltro, setEstadoFiltro,
  bodegaFiltro, setBodegaFiltro,
  fechaDesde, setFechaDesde,
  fechaHasta, setFechaHasta,
  bodegasUnicas,
  cargar, limpiarFiltros,
}) {
  return (
    <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-5">
      <div>
        <label
          htmlFor="filtro-estado"
          className="block text-xs font-medium text-slate-700"
        >
          Estado
        </label>
        <select
          id="filtro-estado"
          value={estadoFiltro}
          onChange={(e) => setEstadoFiltro(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          {ESTADOS.map((e) => (
            <option key={e.value} value={e.value}>
              {e.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label
          htmlFor="filtro-bodega-origen"
          className="block text-xs font-medium text-slate-700"
        >
          Bodega origen
        </label>
        <select
          id="filtro-bodega-origen"
          value={bodegaFiltro}
          onChange={(e) => setBodegaFiltro(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          <option value="">Todas</option>
          {bodegasUnicas.map((b) => (
            <option key={b.id} value={b.id}>
              {b.codigo}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label
          htmlFor="filtro-desde"
          className="block text-xs font-medium text-slate-700"
        >
          Desde
        </label>
        <input
          id="filtro-desde"
          type="date"
          value={fechaDesde}
          onChange={(e) => setFechaDesde(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label
          htmlFor="filtro-hasta"
          className="block text-xs font-medium text-slate-700"
        >
          Hasta
        </label>
        <input
          id="filtro-hasta"
          type="date"
          value={fechaHasta}
          onChange={(e) => setFechaHasta(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      <div className="flex items-end gap-2">
        <button
          type="button"
          onClick={cargar}
          className="flex-1 rounded-md bg-slate-800 px-3 py-1.5 text-sm font-semibold text-white hover:bg-slate-700"
        >
          Aplicar
        </button>
        <button
          type="button"
          onClick={limpiarFiltros}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Limpiar
        </button>
      </div>
    </div>
  );
}
