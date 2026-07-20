// Barra de filtros para la pagina de Ordenes de Compra.
import { ESTADOS } from "./constants";

export function OrdenesFilters({
  estadoFiltro,
  setEstadoFiltro,
  proveedorFiltro,
  setProveedorFiltro,
  fechaDesde,
  setFechaDesde,
  fechaHasta,
  setFechaHasta,
}) {
  return (
    <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-5">
      <div>
        <label htmlFor="estado" className="text-xs font-semibold uppercase text-slate-500">
          Estado
        </label>
        <select
          id="estado"
          value={estadoFiltro}
          onChange={(e) => setEstadoFiltro(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        >
          {ESTADOS.map((e) => (
            <option key={e.value} value={e.value}>
              {e.label}
            </option>
          ))}
        </select>
      </div>
      <div className="sm:col-span-2">
        <label htmlFor="prov" className="text-xs font-semibold uppercase text-slate-500">
          Proveedor (ILIKE)
        </label>
        <input
          id="prov"
          type="text"
          value={proveedorFiltro}
          onChange={(e) => setProveedorFiltro(e.target.value)}
          placeholder="Buscar por nombre..."
          className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        />
      </div>
      <div>
        <label htmlFor="desde" className="text-xs font-semibold uppercase text-slate-500">
          Desde
        </label>
        <input
          id="desde"
          type="date"
          value={fechaDesde}
          onChange={(e) => setFechaDesde(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        />
      </div>
      <div>
        <label htmlFor="hasta" className="text-xs font-semibold uppercase text-slate-500">
          Hasta
        </label>
        <input
          id="hasta"
          type="date"
          value={fechaHasta}
          onChange={(e) => setFechaHasta(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        />
      </div>
    </div>
  );
}
