// Drawer lateral de detalle de una Solicitud de Recarga.
import { COLOR_ESTADO, COLOR_PRIORIDAD, ETIQUETA_ESTADO } from "./constants";
import { formatFecha, formatNum } from "./formatters";

export function SolicitudDetailDrawer({
  detalle,
  loading,
  puedeAprobar,
  cerrarDetalle,
  aprobar,
  rechazar,
}) {
  return (
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
        {loading || !detalle ? (
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
                  {detalle.bodega_origen_codigo} &mdash; {detalle.bodega_origen_nombre}
                </p>
              </div>
              <div>
                <p className="font-semibold text-slate-600">Destino</p>
                <p className="font-mono text-slate-800">
                  {detalle.bodega_destino_codigo} &mdash; {detalle.bodega_destino_nombre}
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
  );
}
