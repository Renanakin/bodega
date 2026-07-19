// SolicitudesAuxPage: gestion de solicitudes de recarga (Fase 3 + Fase 4).
//
// - Lista solicitudes con filtros (estado, bodega origen, rango fechas).
// - Tabla con paginacion + drawer de detalle al click en una fila.
// - Boton "Nueva solicitud manual" (placeholder Fase 4; se completa
//   cuando se implemente el form modal en Fase 5/6).
// - Disenada 100% con Tailwind v3.
import { useCallback, useEffect, useMemo, useState } from "react";

import { getErrorMessage, getJson, postJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

const ESTADOS = [
  { value: "", label: "Todos" },
  { value: "pending", label: "Pendiente" },
  { value: "approved", label: "Aprobada" },
  { value: "in_transit", label: "En transito" },
  { value: "partially_received", label: "Recepcion parcial" },
  { value: "received", label: "Recibida" },
  { value: "rejected", label: "Rechazada" },
  { value: "cancelled", label: "Cancelada" },
];

const ETIQUETA_ESTADO = {
  pending: "Pendiente",
  approved: "Aprobada",
  in_transit: "En transito",
  partially_received: "Recepcion parcial",
  received: "Recibida",
  rejected: "Rechazada",
  cancelled: "Cancelada",
  partial: "Recepcion parcial",
};

const COLOR_ESTADO = {
  pending: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  approved: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  in_transit: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  partially_received: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  partial: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  received: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
  rejected: "bg-rose-100 text-rose-800 ring-1 ring-rose-300",
  cancelled: "bg-slate-200 text-slate-700 ring-1 ring-slate-300",
};

const COLOR_PRIORIDAD = {
  alta: "text-rose-700 font-semibold",
  urgente: "text-rose-700 font-bold",
  normal: "text-slate-600",
};

const PAGE_SIZE = 25;

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

function toIsoDate(value) {
  if (!value) return undefined;
  // Input type=date emite 'YYYY-MM-DD'; lo convertimos a ISO completo.
  // Para fecha_desde usamos 00:00 y para fecha_hasta 23:59:59 (server side).
  return new Date(`${value}T00:00:00`).toISOString();
}

export function SolicitudesAuxPage() {
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();

  const [solicitudes, setSolicitudes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filtros
  const [estadoFiltro, setEstadoFiltro] = useState("");
  const [bodegaFiltro, setBodegaFiltro] = useState("");
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");

  // Drawer
  const [detalle, setDetalle] = useState(null);
  const [detalleLoading, setDetalleLoading] = useState(false);

  // Paginacion
  const [skip, setSkip] = useState(0);
  const total = solicitudes.length;
  const itemsPagina = useMemo(
    () => solicitudes.slice(skip, skip + PAGE_SIZE),
    [solicitudes, skip],
  );

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (estadoFiltro) params.set("estado", estadoFiltro);
      if (bodegaFiltro) params.set("bodega_origen_id", bodegaFiltro);
      if (fechaDesde) params.set("fecha_desde", toIsoDate(fechaDesde));
      if (fechaHasta) params.set("fecha_hasta", toIsoDate(fechaHasta));
      params.set("limit", "200");
      const data = await getJson(`/solicitudes?${params.toString()}`);
      setSolicitudes(Array.isArray(data) ? data : []);
      setSkip(0);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar solicitudes."));
    } finally {
      setLoading(false);
    }
  }, [estadoFiltro, bodegaFiltro, fechaDesde, fechaHasta]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const bodegasUnicas = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const s of solicitudes) {
      if (seen.has(s.bodega_origen_id)) continue;
      seen.add(s.bodega_origen_id);
      out.push({
        id: s.bodega_origen_id,
        codigo: s.bodega_origen_codigo,
      });
    }
    return out.sort((a, b) => a.codigo.localeCompare(b.codigo));
  }, [solicitudes]);

  const abrirDetalle = useCallback(async (solicitudId) => {
    setDetalleLoading(true);
    try {
      const data = await getJson(`/solicitudes/${solicitudId}`);
      setDetalle(data);
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al cargar detalle",
        description: getErrorMessage(err),
      });
    } finally {
      setDetalleLoading(false);
    }
  }, [pushToast]);

  const cerrarDetalle = useCallback(() => setDetalle(null), []);

  const aprobar = useCallback(
    async (id) => {
      setPendingLabel("Aprobando solicitud...");
      try {
        await postJson(`/solicitudes/${id}/approve`, {});
        pushToast({ tone: "success", title: "Solicitud aprobada" });
        await cargar();
        if (detalle?.id === id) await abrirDetalle(id);
      } catch (err) {
        pushToast({
          tone: "danger",
          title: "Error al aprobar",
          description: getErrorMessage(err),
        });
      } finally {
        clearPending();
      }
    },
    [setPendingLabel, clearPending, pushToast, cargar, detalle, abrirDetalle],
  );

  const rechazar = useCallback(
    async (id) => {
      const motivo = window.prompt(
        "Motivo de rechazo (minimo 5 caracteres):",
        "Rechazada por supervisor",
      );
      if (!motivo || motivo.length < 5) return;
      setPendingLabel("Rechazando solicitud...");
      try {
        await postJson(`/solicitudes/${id}/reject`, { motivo });
        pushToast({ tone: "info", title: "Solicitud rechazada" });
        await cargar();
        if (detalle?.id === id) await abrirDetalle(id);
      } catch (err) {
        pushToast({
          tone: "danger",
          title: "Error al rechazar",
          description: getErrorMessage(err),
        });
      } finally {
        clearPending();
      }
    },
    [setPendingLabel, clearPending, pushToast, cargar, detalle, abrirDetalle],
  );

  const puedeAprobar = useMemo(
    () => user?.role === "admin" || user?.role === "supervisor",
    [user],
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Operaciones
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Solicitudes de recarga
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Workflow completo: pendiente → aprobada → en transito → recibida.
            Click en una fila para ver el detalle y aprobar o rechazar.
          </p>
        </div>
        <button
          type="button"
          disabled
          title="Disponible en Fase 5/6"
          className="rounded-md bg-slate-200 px-3 py-2 text-sm font-semibold text-slate-500 shadow-sm cursor-not-allowed"
        >
          + Nueva solicitud manual
        </button>
      </header>

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
            onClick={() => {
              setEstadoFiltro("");
              setBodegaFiltro("");
              setFechaDesde("");
              setFechaHasta("");
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Limpiar
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">Cargando solicitudes...</p>
        ) : error ? (
          <p className="p-6 text-sm text-rose-600">Error: {error}</p>
        ) : total === 0 ? (
          <div className="p-8 text-center">
            <p className="text-base font-semibold text-slate-700">
              No hay solicitudes con esos filtros
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Prueba limpiando los filtros o espera la proxima corrida
              automatica del ReplenishmentEvaluator.
            </p>
          </div>
        ) : (
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
        )}
      </div>

      {/* Drawer de detalle */}
      {(detalle || detalleLoading) && (
        <div
          className="fixed inset-0 z-40 flex justify-end bg-slate-900/50"
          role="dialog"
          aria-modal="true"
          onClick={cerrarDetalle}
        >
          <div
            className="h-full w-full max-w-xl overflow-y-auto bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {detalleLoading || !detalle ? (
              <p className="text-sm text-slate-500">Cargando detalle...</p>
            ) : (
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Solicitud
                    </p>
                    <h2 className="mt-1 font-mono text-lg font-bold text-slate-900">
                      {detalle.codigo}
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      Creada {formatFecha(detalle.created_at)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={cerrarDetalle}
                    className="rounded p-1 text-slate-500 hover:bg-slate-100"
                    aria-label="Cerrar"
                  >
                    <span aria-hidden="true">x</span>
                  </button>
                </div>

                <div className="flex flex-wrap gap-2">
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                      COLOR_ESTADO[detalle.estado] || COLOR_ESTADO.pending
                    }`}
                  >
                    {ETIQUETA_ESTADO[detalle.estado] || detalle.estado}
                  </span>
                  <span
                    className={`inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs ${
                      COLOR_PRIORIDAD[detalle.prioridad] || COLOR_PRIORIDAD.normal
                    }`}
                  >
                    Prioridad: {detalle.prioridad || "normal"}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs">
                  <div>
                    <p className="font-semibold text-slate-600">Origen</p>
                    <p className="font-mono text-slate-800">
                      {detalle.bodega_origen_codigo} — {detalle.bodega_origen_nombre}
                    </p>
                  </div>
                  <div>
                    <p className="font-semibold text-slate-600">Destino</p>
                    <p className="font-mono text-slate-800">
                      {detalle.bodega_destino_codigo} — {detalle.bodega_destino_nombre}
                    </p>
                  </div>
                  <div>
                    <p className="font-semibold text-slate-600">Aprobada</p>
                    <p className="text-slate-800">
                      {formatFecha(detalle.approved_at)}
                    </p>
                  </div>
                  <div>
                    <p className="font-semibold text-slate-600">Despachada</p>
                    <p className="text-slate-800">
                      {formatFecha(detalle.dispatched_at)}
                    </p>
                  </div>
                  <div className="col-span-2">
                    <p className="font-semibold text-slate-600">Recibida</p>
                    <p className="text-slate-800">
                      {formatFecha(detalle.received_at)}
                    </p>
                  </div>
                </div>

                {detalle.notas && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Notas
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">
                      {detalle.notas}
                    </p>
                  </div>
                )}

                {detalle.motivo_rechazo && (
                  <div className="rounded-md border border-rose-200 bg-rose-50 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wider text-rose-700">
                      Motivo de rechazo
                    </p>
                    <p className="mt-1 text-sm text-rose-800">
                      {detalle.motivo_rechazo}
                    </p>
                  </div>
                )}

                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Lineas ({detalle.total_productos} productos,{" "}
                    {formatNum(detalle.total_unidades)} unidades)
                  </p>
                  <div className="overflow-hidden rounded-md border border-slate-200">
                    <table className="min-w-full divide-y divide-slate-200 text-xs">
                      <thead className="bg-slate-50 text-slate-600">
                        <tr>
                          <th className="px-2 py-1.5 text-left">SKU</th>
                          <th className="px-2 py-1.5 text-left">Producto</th>
                          <th className="px-2 py-1.5 text-right">Solicitado</th>
                          <th className="px-2 py-1.5 text-right">Despachado</th>
                          <th className="px-2 py-1.5 text-right">Recibido</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {(detalle.lineas || []).map((l) => (
                          <tr key={l.producto_id}>
                            <td className="px-2 py-1.5 font-mono">
                              {l.producto_sku}
                            </td>
                            <td className="px-2 py-1.5">{l.producto_nombre}</td>
                            <td className="px-2 py-1.5 text-right">
                              {formatNum(l.cantidad_solicitada)}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {formatNum(l.cantidad_despachada)}
                            </td>
                            <td className="px-2 py-1.5 text-right">
                              {formatNum(l.cantidad_recibida)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {puedeAprobar && detalle.estado === "pending" && (
                  <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-4">
                    <button
                      type="button"
                      onClick={() => aprobar(detalle.id)}
                      className="flex-1 rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-500"
                    >
                      Aprobar
                    </button>
                    <button
                      type="button"
                      onClick={() => rechazar(detalle.id)}
                      className="flex-1 rounded-md bg-rose-600 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-500"
                    >
                      Rechazar
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
