// Tab "Auditoria" de la pagina de Reports.
// Carga los ultimos 200 eventos de audit y permite filtrarlos.
import { useCallback, useEffect, useMemo, useState } from "react";
import { getErrorMessage, getJson } from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { downloadCsv } from "../../lib/export";
import { formatFecha } from "./helpers";

export function TabAuditoria() {
  const { user } = useAuth();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filtroAccion, setFiltroAccion] = useState("");
  const [filtroEntidad, setFiltroEntidad] = useState("");

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJson("/audit?limit=200");
      setLogs(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar la auditoria."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const logsFiltrados = useMemo(() => {
    return logs.filter((l) => {
      if (filtroAccion && !l.action?.toLowerCase().includes(filtroAccion.toLowerCase())) return false;
      if (filtroEntidad && l.entity_type !== filtroEntidad) return false;
      return true;
    });
  }, [logs, filtroAccion, filtroEntidad]);

  const entidadesUnicas = useMemo(() => {
    const set = new Set();
    logs.forEach((l) => l.entity_type && set.add(l.entity_type));
    return Array.from(set).sort();
  }, [logs]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="Filtrar por accion..."
          value={filtroAccion}
          onChange={(e) => setFiltroAccion(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          aria-label="Filtrar auditoria por accion"
        />
        <select
          value={filtroEntidad}
          onChange={(e) => setFiltroEntidad(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          aria-label="Filtrar auditoria por entidad"
        >
          <option value="">Todas las entidades</option>
          {entidadesUnicas.map((e) => (
            <option key={e} value={e}>
              {e}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={cargar}
          className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Refrescar
        </button>
        <button
          type="button"
          onClick={() =>
            downloadCsv(
              "auditoria.csv",
              [
                { key: "action", label: "Accion" },
                { key: "entity_type", label: "Entidad" },
                { key: "entity_id", label: "ID" },
                { key: "detail", label: "Detalle" },
                { key: "created_at", label: "Fecha" },
              ],
              logsFiltrados,
            )
          }
          className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Exportar CSV
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-4 text-sm text-slate-500">Cargando auditoria...</p>
        ) : error ? (
          <p className="p-4 text-sm text-rose-600">Error: {error}</p>
        ) : logsFiltrados.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">
            Sin eventos para los filtros aplicados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2">Fecha</th>
                  <th className="px-3 py-2">Accion</th>
                  <th className="px-3 py-2">Entidad</th>
                  <th className="px-3 py-2">Detalle</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logsFiltrados.slice(0, 100).map((l) => (
                  <tr key={l.id} className="hover:bg-slate-50">
                    <td className="px-3 py-1.5 text-xs text-slate-600">
                      {formatFecha(l.created_at)}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-xs text-indigo-700">
                      {l.action}
                    </td>
                    <td className="px-3 py-1.5 text-slate-700">
                      <span className="font-mono text-xs">
                        {l.entity_type}
                      </span>
                      {l.entity_id ? (
                        <span className="ml-1 text-slate-500">#{l.entity_id.slice(0, 8)}</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-1.5 text-slate-700">{l.detail || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {logsFiltrados.length > 100 ? (
              <p className="mt-2 text-xs text-slate-500">
                Mostrando 100 de {logsFiltrados.length} — use el export CSV para ver todos.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
