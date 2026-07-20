// Helpers compartidos por la pagina de Reports.

export const TABS = [
  { id: "operacional", label: "Operacional" },
  { id: "ejecutivo", label: "Ejecutivo" },
  { id: "auditoria", label: "Auditoria" },
];

export const ESTADO_COLOR = {
  borrador: "bg-slate-100 text-slate-700",
  enviado_a_supervisor: "bg-sky-100 text-sky-800",
  aprobado: "bg-emerald-100 text-emerald-800",
  rechazado: "bg-rose-100 text-rose-800",
  comprado: "bg-emerald-100 text-emerald-800",
  dispatched: "bg-sky-100 text-sky-800",
  received: "bg-emerald-100 text-emerald-800",
  cancelled: "bg-slate-200 text-slate-700",
};

export function formatCLP(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  });
}

export function formatNum(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 });
}

export function formatFecha(iso) {
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

// Genera un PDF simple con el snapshot del dashboard ejecutivo.
// En una iteracion futura esto se reemplaza por un reportlab del backend.
export function downloadEjecutivoPDF(snapshot) {
  const win = window.open("", "_blank", "width=720,height=900");
  if (!win) {
    return;
  }
  const fecha = new Date().toLocaleString("es-CL");
  const safe = (v) => (v === null || v === undefined ? "-" : String(v));
  const rows = [
    ["Total productos", safe(snapshot?.total_productos)],
    ["Total stock (CLP)", formatCLP(snapshot?.total_stock_clp)],
    ["Solicitudes pendientes", safe(snapshot?.solicitudes_pendientes)],
    ["Quiebres detectados", safe(snapshot?.quiebres)],
    ["OCs enviadas", safe(snapshot?.ocs_enviadas)],
    ["OCs aprobadas", safe(snapshot?.ocs_aprobadas)],
    ["OCs rechazadas", safe(snapshot?.ocs_rechazadas)],
  ];
  const style = "font-family:system-ui;padding:24px;";
  const tableStyle = "border-collapse:collapse;width:100%;margin-top:16px;";
  const tdStyle = "border:1px solid #ccc;padding:8px;text-align:left;";
  const html = `<!doctype html>
<html><head><title>Reporte Ejecutivo - ${fecha}</title></head>
<body style="${style}">
<h1>Reporte Ejecutivo</h1>
<p style="color:#666">Generado: ${fecha}</p>
<table style="${tableStyle}">
<thead><tr style="background:#f1f5f9">
<th style="${tdStyle}">Indicador</th>
<th style="${tdStyle}">Valor</th>
</tr></thead>
<tbody>
${rows.map(([k, v]) => `<tr><td style="${tdStyle}">${k}</td><td style="${tdStyle}">${v}</td></tr>`).join("")}
</tbody>
</table>
<p style="margin-top:24px;font-size:11px;color:#999">
Snapshot generado en el cliente. Reemplazar por export PDF del backend en una iteracion futura.
</p>
</body></html>`;
  win.document.write(html);
  win.document.close();
  win.focus();
  setTimeout(() => {
    win.print();
  }, 300);
}
