// ReportsPage: vista de reportes operativos y ejecutivos (Fase 8).
//
// Ruta: /reports
//
// Tabs:
//   - Operacional: exportes CSV (inventario, transferencias, historial).
//   - Ejecutivo:   snapshot de KPIs (valorizado, alertas, top productos).
//   - Auditoria:   tabla de audit_logs con filtros (usuario, accion, fecha).
//
// Endpoint ejecutivo: GET /api/v1/reports/ejecutivo
// Export PDF:         se genera en el cliente con jsPDF (decision
//                     documentada en fase-8 — evita dependencia server-side).
//
// Refactor completo a Tailwind v3 (ADR-0006). La version anterior usaba CSS
// plano legacy con TableSimple/EmptyState/FilterBar; ahora es 100% utility.
import { useCallback, useEffect, useMemo, useState } from "react";

import { getErrorMessage, getJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";
import { downloadCsv } from "../lib/export";

const TABS = [
  { id: "operacional", label: "Operacional" },
  { id: "ejecutivo", label: "Ejecutivo" },
  { id: "auditoria", label: "Auditoria" },
];

const ESTADO_COLOR = {
  pendiente: "bg-slate-100 text-slate-700 ring-1 ring-slate-300",
  aprobada: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
  en_transito: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  partially_received: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  received: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
  rechazada: "bg-rose-100 text-rose-800 ring-1 ring-rose-300",
  cancelada: "bg-slate-200 text-slate-600 ring-1 ring-slate-300",
};

function formatCLP(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  });
}

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

/**
 * Genera un PDF simple del snapshot ejecutivo en el cliente.
 * Usa la API `window.print()` con un `iframe` oculto que renderiza HTML
 * formateado. Esto evita agregar la dependencia `jsPDF` (~50KB) al bundle
 * y deja al browser del usuario hacer el layout final.
 *
 * Decisión documentada en fase-8 (Fase 8: "NO introducir dependencias
 * pesadas; PDF: jsPDF (~50KB) o HTML-to-print"). Implementamos la opción
 * HTML-to-print porque es 0KB adicional.
 */
function downloadEjecutivoPDF(snapshot) {
  if (!snapshot) return;
  const generado = new Date(snapshot.generado_en).toLocaleString("es-CL");
  const topMas = (snapshot.top_productos_mas_movidos || [])
    .map(
      (p, i) =>
        `<tr><td>${i + 1}</td><td>${p.sku}</td><td>${p.nombre}</td><td>${formatNum(p.unidades_movidas)}</td><td>${p.movimientos_count}</td></tr>`,
    )
    .join("");
  const topMenos = (snapshot.top_productos_menos_movidos || [])
    .map(
      (p, i) =>
        `<tr><td>${i + 1}</td><td>${p.sku}</td><td>${p.nombre}</td><td>${formatNum(p.unidades_movidas)}</td><td>${p.movimientos_count}</td></tr>`,
    )
    .join("");
  const valorPorBodega = (snapshot.valor_por_bodega || [])
    .map(
      (b) =>
        `<tr><td>${b.bodega_code}</td><td>${b.bodega_name}</td><td>${b.bodega_type}</td><td>${formatNum(b.unidades_total)}</td><td>${formatCLP(b.valor_total)}</td></tr>`,
    )
    .join("");
  const solicitudesHTML = Object.entries(snapshot.solicitudes_por_estado || {})
    .map(([estado, count]) => `<li>${estado}: <strong>${count}</strong></li>`)
    .join("");

  const html = `<!doctype html>
<html lang="es"><head><meta charset="utf-8" />
<title>Reporte Ejecutivo - ${generado}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Tahoma, sans-serif;
         padding: 24px; color: #1e293b; }
  h1 { margin: 0 0 4px; font-size: 24px; }
  h2 { margin-top: 28px; font-size: 16px; color: #475569; text-transform: uppercase; letter-spacing: 0.05em; }
  .meta { color: #64748b; font-size: 12px; margin-bottom: 24px; }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
  .kpi { border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; }
  .kpi-label { font-size: 11px; color: #64748b; text-transform: uppercase; }
  .kpi-value { font-size: 22px; font-weight: 700; color: #0f172a; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 12px; }
  th, td { border-bottom: 1px solid #e2e8f0; padding: 6px 8px; text-align: left; }
  th { background: #f1f5f9; font-weight: 600; }
  ul { margin: 4px 0 0 16px; font-size: 12px; }
  @media print { body { padding: 0; } }
</style></head><body>
<h1>Reporte Ejecutivo</h1>
<p class="meta">Generado: ${generado}</p>

<div class="kpis">
  <div class="kpi"><div class="kpi-label">Stock valorizado</div>
    <div class="kpi-value">${formatCLP(snapshot.stock_total_activo_valorizado)}</div></div>
  <div class="kpi"><div class="kpi-label">Alertas criticas</div>
    <div class="kpi-value">${snapshot.alertas_criticas_count}</div></div>
  <div class="kpi"><div class="kpi-label">Transferencias en ruta</div>
    <div class="kpi-value">${snapshot.transferencias_en_ruta_count}</div></div>
  <div class="kpi"><div class="kpi-label">Productos activos</div>
    <div class="kpi-value">${snapshot.total_productos_activos}</div></div>
  <div class="kpi"><div class="kpi-label">Bodegas activas</div>
    <div class="kpi-value">${snapshot.total_bodegas}</div></div>
  <div class="kpi"><div class="kpi-label">Solicitudes por estado</div>
    <div class="kpi-value"><ul>${solicitudesHTML}</ul></div></div>
</div>

<h2>Valor por bodega</h2>
<table><thead><tr><th>Codigo</th><th>Nombre</th><th>Tipo</th><th>Unidades</th><th>Valor CLP</th></tr></thead>
<tbody>${valorPorBodega}</tbody></table>

<h2>Top ${snapshot.config?.top_n || 5} productos mas movidos</h2>
<table><thead><tr><th>#</th><th>SKU</th><th>Nombre</th><th>Unidades</th><th>Movimientos</th></tr></thead>
<tbody>${topMas}</tbody></table>

<h2>Top ${snapshot.config?.top_n || 5} productos menos movidos</h2>
<table><thead><tr><th>#</th><th>SKU</th><th>Nombre</th><th>Unidades</th><th>Movimientos</th></tr></thead>
<tbody>${topMenos}</tbody></table>
</body></html>`;

  // Abrir en ventana nueva y disparar print(). El usuario elige "Guardar
  // como PDF" en el dialog del browser.
  const win = window.open("", "_blank", "width=900,height=1200");
  if (!win) {
    alert("El browser bloqueo la ventana emergente. Habilite popups para este sitio.");
    return;
  }
  win.document.write(html);
  win.document.close();
  win.addEventListener("load", () => {
    win.focus();
    win.print();
  });
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
        active
          ? "border-indigo-600 text-indigo-700"
          : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-800"
      }`}
    >
      {children}
    </button>
  );
}

function TabOperacional({ stock, transfers, movements, warehouses, error, loading }) {
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

function TabEjecutivo() {
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

function TabAuditoria() {
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

export function ReportsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("operacional");
  const [stock, setStock] = useState([]);
  const [transfers, setTransfers] = useState([]);
  const [movements, setMovements] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelado = false;
    async function cargar() {
      setLoading(true);
      setError(null);
      try {
        const [s, t, m, w] = await Promise.all([
          getJson("/inventory/stock"),
          getJson("/transfers"),
          getJson("/inventory/movements?limit=200"),
          getJson("/warehouses"),
        ]);
        if (!cancelado) {
          setStock(Array.isArray(s) ? s : []);
          setTransfers(Array.isArray(t) ? t : []);
          setMovements(Array.isArray(m) ? m : []);
          setWarehouses(Array.isArray(w) ? w : []);
        }
      } catch (err) {
        if (!cancelado) {
          setError(getErrorMessage(err, "No se pudo cargar los datos operativos."));
        }
      } finally {
        if (!cancelado) setLoading(false);
      }
    }
    cargar();
    return () => {
      cancelado = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Reportes
        </p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">Reportes</h1>
        <p className="mt-1 text-sm text-slate-600">
          Exportes operativos (CSV), snapshot ejecutivo (PDF) y auditoria
          reciente. Sesion activa: {user?.full_name} ({user?.role}).
        </p>
      </header>

      <div className="border-b border-slate-200" role="tablist" aria-label="Tabs de reportes">
        <nav className="flex space-x-2">
          {TABS.map((t) => (
            <TabButton key={t.id} active={tab === t.id} onClick={() => setTab(t.id)}>
              {t.label}
            </TabButton>
          ))}
        </nav>
      </div>

      <div role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "operacional" ? (
          <TabOperacional
            stock={stock}
            transfers={transfers}
            movements={movements}
            warehouses={warehouses}
            error={error}
            loading={loading}
          />
        ) : tab === "ejecutivo" ? (
          <TabEjecutivo />
        ) : (
          <TabAuditoria />
        )}
      </div>
    </div>
  );
}
