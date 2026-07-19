// RecepcionBandejaPage: bandeja de solicitudes en transito para mi bodega (Fase 5).
//
// - Ruta: /recepciones/en-transito
// - Lista solicitudes en estado `in_transit` (o `partially_received`)
//   filtradas por la bodega destino del usuario logueado.
// - Tabla: codigo, bodega origen, # productos, total unidades, fecha despacho.
// - Click en una fila -> /recepciones/:id (RecepcionDetallePage).
// - 100% Tailwind v3 (ADR-0006). Coexiste con CSS plano de las vistas legacy.

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getErrorMessage, getJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

const ESTADOS_VISIBLE = new Set(["in_transit", "partially_received"]);

const ETIQUETA_ESTADO = {
  in_transit: "En transito",
  partially_received: "Recepcion parcial",
};

const COLOR_ESTADO = {
  in_transit: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  partially_received: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
};

function formatNum(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 });
}

function formatFecha(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString("es-CL", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export function RecepcionBandejaPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();

  const [solicitudes, setSolicitudes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Filtro: por defecto solo el destino del usuario; el bodeguero no
  // deberia estar viendo recepciones para otras bodegas.
  const destinoUser = user?.bodega_id || null;

  const cargar = useCallback(
    async (esRefresco = false) => {
      if (esRefresco) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);
      try {
        // El endpoint /solicitudes soporta filtro por bodega_destino_id.
        // Si no hay destinoUser, no filtramos (caso admin/supervisor).
        const params = new URLSearchParams();
        params.set("limit", "100");
        if (destinoUser) {
          params.set("bodega_destino_id", destinoUser);
        }
        // Traemos todas las que puedan ser de mi bodega; filtramos en
        // cliente por estado visible (in_transit + partially_received).
        const data = await getJson(`/solicitudes?${params.toString()}`);
        const lista = Array.isArray(data) ? data : [];
        const filtradas = lista.filter((s) => ESTADOS_VISIBLE.has(s.estado));
        // Orden: mas recientes primero (por created_at desc como proxy).
        filtradas.sort((a, b) => {
          const fa = a.dispatched_at || a.created_at || "";
          const fb = b.dispatched_at || b.created_at || "";
          return fb.localeCompare(fa);
        });
        setSolicitudes(filtradas);
      } catch (err) {
        setError(getErrorMessage(err, "No se pudo cargar la bandeja."));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [destinoUser],
  );

  useEffect(() => {
    cargar(false);
  }, [cargar]);

  const handleAbrir = useCallback(
    (solicitud) => {
      navigate(`/recepciones/${solicitud.id}`);
    },
    [navigate],
  );

  const handleRefresh = useCallback(() => {
    cargar(true);
  }, [cargar]);

  return (
    <div className="space-y-4">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Recepcion
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Recepciones en transito
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Solicitudes despachadas desde la bodega principal con destino
            a tu bodega. Click en una fila para escanear los productos.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            data-testid="contador-solicitudes"
            className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700"
          >
            {solicitudes.length} pendiente{solicitudes.length === 1 ? "" : "s"}
          </span>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {refreshing ? "Actualizando..." : "Actualizar"}
          </button>
        </div>
      </header>

      {loading ? (
        <p className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
          Cargando recepciones pendientes...
        </p>
      ) : error ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 shadow-sm">
          <p className="font-semibold">No se pudo cargar la bandeja</p>
          <p className="mt-1">{error}</p>
        </div>
      ) : solicitudes.length === 0 ? (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center shadow-sm">
          <p className="text-base font-semibold text-slate-700">
            No hay recepciones pendientes para tu bodega
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Cuando Principal despache productos a tu bodega, apareceran
            aca. Volve a chequear en unos minutos.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-4 py-2">Codigo</th>
                  <th className="px-4 py-2">Bodega origen</th>
                  <th className="px-4 py-2">Estado</th>
                  <th className="px-4 py-2 text-right"># Productos</th>
                  <th className="px-4 py-2 text-right">Total unidades</th>
                  <th className="px-4 py-2">Despachado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {solicitudes.map((s) => (
                  <tr
                    key={s.id}
                    onClick={() => handleAbrir(s)}
                    className="cursor-pointer hover:bg-slate-50"
                    data-testid={`fila-solicitud-${s.id}`}
                  >
                    <td className="px-4 py-2 font-mono text-xs text-indigo-700">
                      {s.codigo}
                    </td>
                    <td className="px-4 py-2">
                      <div className="font-mono text-xs font-semibold text-slate-800">
                        {s.bodega_origen_codigo}
                      </div>
                      <div className="text-xs text-slate-500">
                        {s.bodega_origen_nombre}
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          COLOR_ESTADO[s.estado] || "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {ETIQUETA_ESTADO[s.estado] || s.estado}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right text-slate-700">
                      {s.total_productos}
                    </td>
                    <td className="px-4 py-2 text-right text-slate-700">
                      {formatNum(s.total_unidades)}
                    </td>
                    <td className="px-4 py-2 text-xs text-slate-500">
                      {formatFecha(s.dispatched_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
