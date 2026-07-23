// ReplenishmentPage: vista de reposicion automatica (Fase 4).
//
// Muestra los SKUs bajo minimo de las bodegas auxiliares y permite
// generar solicitudes automaticas via POST /solicitudes/auto-generar.
// Disenada 100% con Tailwind v3 (sin CSS plano legacy).
import { useCallback, useEffect, useMemo, useState } from "react";

import { getErrorMessage, getJson, postJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

const ESTILO_PRIORIDAD = {
  alta: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  normal: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
};

function formatCantidad(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 });
}

function formatTimestamp(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("es-CL", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export function ReplenishmentPage() {
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();

  const [items, setItems] = useState([]);
  const [cubiertos, setCubiertos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastReport, setLastReport] = useState(null);
  const [filtroBodega, setFiltroBodega] = useState("");

  const puedeDisparar = useMemo(() => {
    if (!user) return false;
    return user.role === "admin" || user.role === "supervisor";
  }, [user]);

  const cargarBajoMinimo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const query = filtroBodega ? `?bodega_id=${filtroBodega}` : "";
      // BUG 10 (fix 2026-07-23): cargamos en paralelo bajo-minimo y
      // bajo-minimo/cubiertos-por-pendientes. El segundo nos da
      // contexto cuando el primero devuelve 0: hay SKUs bajo
      // minimo pero ya estan cubiertos por solicitudes PENDING.
      const [data, ctx] = await Promise.all([
        getJson(`/solicitudes/bajo-minimo${query}`),
        getJson("/solicitudes/bajo-minimo/cubiertos-por-pendientes").catch(() => null),
      ]);
      setItems(Array.isArray(data) ? data : []);
      setCubiertos(ctx && Array.isArray(ctx.items) ? ctx.items : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar el catalogo bajo minimo."));
    } finally {
      setLoading(false);
    }
  }, [filtroBodega]);

  useEffect(() => {
    cargarBajoMinimo();
  }, [cargarBajoMinimo]);

  const bodegasUnicas = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const it of items) {
      if (seen.has(it.bodega_id)) continue;
      seen.add(it.bodega_id);
      out.push({ id: it.bodega_id, codigo: it.bodega_codigo, nombre: it.bodega_nombre });
    }
    return out.sort((a, b) => a.codigo.localeCompare(b.codigo));
  }, [items]);

  const itemsFiltrados = useMemo(() => {
    if (!filtroBodega) return items;
    return items.filter((it) => it.bodega_id === filtroBodega);
  }, [items, filtroBodega]);

  const dispararGeneracion = useCallback(
    async ({ bodegaId = null, dryRun = false } = {}) => {
      if (!puedeDisparar) {
        pushToast({
          tone: "danger",
          title: "Sin permisos",
          description: "Solo admin o supervisor pueden disparar la generacion.",
        });
        return;
      }
      setPendingLabel(dryRun ? "Calculando..." : "Generando solicitudes...");
      try {
        const params = new URLSearchParams();
        if (bodegaId) params.set("bodega_id", bodegaId);
        if (dryRun) params.set("dry_run", "true");
        const query = params.toString() ? `?${params.toString()}` : "";
        const report = await postJson(`/solicitudes/auto-generar${query}`);
        setLastReport(report);
        const accion = dryRun ? "Calculo" : "Generacion";
        pushToast({
          tone: report.solicitudes_creadas > 0 ? "success" : "info",
          title: `${accion} completada`,
          description:
            `${report.solicitudes_creadas} solicitud(es) creada(s), ` +
            `${report.solicitudes_omitidas_pendientes} omitida(s) por pendiente previa.`,
        });
        if (!dryRun) {
          // Refrescar el catalogo: las solicitudes generadas no aparecen
          // aca (siguen bajo minimo hasta que se aprueben/dispachen), pero
          // el reporte muestra el resultado completo.
          await cargarBajoMinimo();
        }
      } catch (err) {
        pushToast({
          tone: "danger",
          title: "Error al generar solicitudes",
          description: getErrorMessage(err),
        });
      } finally {
        clearPending();
      }
    },
    [puedeDisparar, pushToast, setPendingLabel, clearPending, cargarBajoMinimo],
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Reposicion automatica
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Alertas de stock bajo minimo
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Detecta SKUs que cayeron bajo su minimo y crea solicitudes
            automaticas a la Bodega Principal. La corrida automatica
            ejecuta cada {5} minutos; aqui puedes dispararla manualmente
            o previsualizar el impacto.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => dispararGeneracion({ dryRun: true })}
            disabled={!puedeDisparar || loading}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Previsualizar (dry run)
          </button>
          <button
            type="button"
            onClick={() => dispararGeneracion()}
            disabled={!puedeDisparar || loading}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Generar solicitudes
          </button>
        </div>
      </header>

      {lastReport && (
        <div
          className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-900 shadow-sm"
          role="status"
          aria-live="polite"
        >
          <div className="flex items-center justify-between">
            <p className="font-semibold">
              Ultima corrida: {lastReport.dry_run ? "previsualizacion" : "ejecucion real"} —{" "}
              {formatTimestamp(lastReport.timestamp)}
            </p>
            <button
              type="button"
              onClick={() => setLastReport(null)}
              className="rounded p-1 text-indigo-700 hover:bg-indigo-100"
              aria-label="Cerrar"
            >
              <span aria-hidden="true">x</span>
            </button>
          </div>
          <ul className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <li>
              <span className="block text-xs uppercase tracking-wide text-indigo-700">
                Bodegas
              </span>
              <span className="text-lg font-bold">{lastReport.bodegas_evaluadas}</span>
            </li>
            <li>
              <span className="block text-xs uppercase tracking-wide text-indigo-700">
                SKUs bajo minimo
              </span>
              <span className="text-lg font-bold">{lastReport.skus_bajo_minimo}</span>
            </li>
            <li>
              <span className="block text-xs uppercase tracking-wide text-indigo-700">
                Creadas
              </span>
              <span className="text-lg font-bold">{lastReport.solicitudes_creadas}</span>
            </li>
            <li>
              <span className="block text-xs uppercase tracking-wide text-indigo-700">
                Omitidas (pendiente)
              </span>
              <span className="text-lg font-bold">
                {lastReport.solicitudes_omitidas_pendientes}
              </span>
            </li>
          </ul>
          {lastReport.errores?.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-semibold text-rose-700">
                {lastReport.errores.length} error(es) — ver detalle
              </summary>
              <ul className="mt-1 list-disc pl-5 text-xs text-rose-700">
                {lastReport.errores.map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <label
            htmlFor="filtro-bodega"
            className="text-sm font-medium text-slate-700"
          >
            Bodega:
          </label>
          <select
            id="filtro-bodega"
            value={filtroBodega}
            onChange={(e) => setFiltroBodega(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Todas las auxiliares</option>
            {bodegasUnicas.map((b) => (
              <option key={b.id} value={b.id}>
                {b.codigo} — {b.nombre}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={cargarBajoMinimo}
          className="self-start rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 sm:self-auto"
        >
          Refrescar
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">Cargando catalogo bajo minimo...</p>
        ) : error ? (
          <p className="p-6 text-sm text-rose-600">Error: {error}</p>
        ) : itemsFiltrados.length === 0 ? (
          <div className="p-8">
            <div className="text-center">
              <p className="text-base font-semibold text-slate-700">
                Sin alertas de stock bajo minimo
              </p>
              <p className="mt-1 text-sm text-slate-500">
                {cubiertos.length > 0
                  ? "Todas las bodegas auxiliares tienen su stock bajo minimo cubierto por solicitudes PENDING."
                  : "Todas las bodegas auxiliares tienen su stock sobre el minimo configurado. El sistema volvera a evaluar en la proxima corrida automatica."}
              </p>
            </div>
            {cubiertos.length > 0 ? (
              <div className="mx-auto mt-6 max-w-3xl overflow-hidden rounded-lg border border-amber-200 bg-amber-50">
                <div className="border-b border-amber-200 bg-amber-100 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-amber-900">
                  SKUs bajo minimo cubiertos por solicitudes pendientes ({cubiertos.length})
                </div>
                <ul className="divide-y divide-amber-200 text-sm">
                  {cubiertos.map((it) => (
                    <li
                      key={`${it.solicitud_id}-${it.bodega_id}-${it.producto_id}`}
                      className="flex flex-wrap items-center gap-2 px-4 py-2 text-amber-900"
                    >
                      <span className="font-mono text-xs font-semibold">
                        {it.producto_sku}
                      </span>
                      <span className="text-amber-800">{it.producto_nombre}</span>
                      <span className="text-amber-700">en</span>
                      <span className="font-mono text-xs">{it.bodega_codigo}</span>
                      <span className="ml-auto text-xs text-amber-700">
                        Stock {formatCantidad(it.stock_actual)} / min{" "}
                        {formatCantidad(it.stock_minimo)} - solicita{" "}
                        {formatCantidad(it.cantidad_solicitada)}
                      </span>
                      <a
                        href={`/solicitudes?highlight=${encodeURIComponent(it.solicitud_id)}`}
                        className="rounded border border-amber-300 bg-white px-2 py-0.5 text-xs font-semibold text-amber-800 hover:bg-amber-100"
                      >
                        {it.solicitud_codigo}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th scope="col" className="px-4 py-2">Bodega</th>
                  <th scope="col" className="px-4 py-2">SKU</th>
                  <th scope="col" className="px-4 py-2">Producto</th>
                  <th scope="col" className="px-4 py-2 text-right">Stock actual</th>
                  <th scope="col" className="px-4 py-2 text-right">Min.</th>
                  <th scope="col" className="px-4 py-2 text-right">Max.</th>
                  <th scope="col" className="px-4 py-2 text-right">Sugerido</th>
                  <th scope="col" className="px-4 py-2 text-center">Prioridad</th>
                  <th scope="col" className="px-4 py-2 text-right">Accion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {itemsFiltrados.map((it) => (
                  <tr key={`${it.bodega_id}-${it.producto_id}`} className="hover:bg-slate-50">
                    <td className="px-4 py-2 font-mono text-xs text-slate-700">
                      {it.bodega_codigo}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs text-slate-600">
                      {it.producto_sku}
                    </td>
                    <td className="px-4 py-2 text-slate-800">{it.producto_nombre}</td>
                    <td className="px-4 py-2 text-right text-rose-700 font-semibold">
                      {formatCantidad(it.stock_actual)}
                    </td>
                    <td className="px-4 py-2 text-right text-slate-600">
                      {formatCantidad(it.stock_minimo)}
                    </td>
                    <td className="px-4 py-2 text-right text-slate-600">
                      {it.stock_maximo != null ? formatCantidad(it.stock_maximo) : "-"}
                    </td>
                    <td className="px-4 py-2 text-right text-indigo-700 font-semibold">
                      {formatCantidad(it.cantidad_sugerida)}
                    </td>
                    <td className="px-4 py-2 text-center">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          ESTILO_PRIORIDAD[it.prioridad] || ESTILO_PRIORIDAD.normal
                        }`}
                      >
                        {it.prioridad}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        type="button"
                        onClick={() =>
                          dispararGeneracion({ bodegaId: it.bodega_id })
                        }
                        disabled={!puedeDisparar}
                        className="rounded border border-indigo-300 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
                        title="Disparar el Evaluator solo para esta bodega"
                      >
                        Generar solicitud
                      </button>
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
        <code className="rounded bg-slate-100 px-1">cantidad = max - actual</code>{" "}
        (o <code className="rounded bg-slate-100 px-1">min*2 - actual</code> si max
        no esta definido). Prioridad{" "}
        <span className="font-semibold text-amber-700">alta</span> cuando el
        stock cae bajo el 50% del minimo. Idempotente: si ya hay una linea
        PENDING para el mismo (bodega, producto), se omite ese SKU;
        el resto se procesa normalmente.
      </p>
    </div>
  );
}
