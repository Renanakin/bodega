// Drawer de detalle de una OC: info, timeline, lineas y acciones por estado.
import { useState } from "react";
import { Timeline } from "./Timeline";
import { formatCLP } from "./formatters";

export function OrdenDetailDrawer({
  detalle,
  loading,
  esAdminOSupervisor,
  enviarCorreo,
  aprobar,
  rechazar,
  marcarComprada,
}) {
  const [showRechazo, setShowRechazo] = useState(false);
  const [motivo, setMotivo] = useState("");

  if (loading || !detalle) {
    return <p className="text-sm text-slate-500">Cargando detalle...</p>;
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
        <p className="text-sm text-slate-700">
          <span className="font-semibold">Proveedor:</span>{" "}
          {detalle.proveedor_nombre}
        </p>
        {detalle.proveedor_contacto ? (
          <p className="text-sm text-slate-600">
            <span className="font-semibold">Contacto:</span>{" "}
            {detalle.proveedor_contacto}
          </p>
        ) : null}
        <p className="text-sm text-slate-700">
          <span className="font-semibold">Supervisor:</span>{" "}
          {detalle.supervisor_nombre || "-"} ({detalle.supervisor_email || "-"})
        </p>
        {detalle.notas ? (
          <p className="mt-2 text-sm text-slate-600">
            <span className="font-semibold">Notas:</span> {detalle.notas}
          </p>
        ) : null}
        {detalle.motivo_rechazo ? (
          <p className="mt-2 text-sm text-rose-700">
            <span className="font-semibold">Motivo rechazo:</span>{" "}
            {detalle.motivo_rechazo}
          </p>
        ) : null}
      </div>

      <Timeline
        estado={detalle.estado}
        email_enviado_at={detalle.email_enviado_at}
        aprobado_at={detalle.aprobado_at}
        comprado_at={detalle.comprado_at}
      />

      <div className="overflow-x-auto rounded-md border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
              <th className="px-3 py-1.5">SKU</th>
              <th className="px-3 py-1.5">Producto</th>
              <th className="px-3 py-1.5 text-right">Cant.</th>
              <th className="px-3 py-1.5 text-right">Costo</th>
              <th className="px-3 py-1.5 text-right">Subtotal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(detalle.detalles || []).map((d, i) => (
              <tr key={i}>
                <td className="px-3 py-1.5 font-mono text-xs text-slate-600">
                  {d.product_sku || d.id_producto.slice(0, 8)}
                </td>
                <td className="px-3 py-1.5 text-slate-800">
                  {d.product_name || "-"}
                </td>
                <td className="px-3 py-1.5 text-right text-slate-700">
                  {Number(d.cantidad_pedida).toLocaleString("es-CL")}
                </td>
                <td className="px-3 py-1.5 text-right text-slate-700">
                  {formatCLP(d.costo_unitario_pactado)}
                </td>
                <td className="px-3 py-1.5 text-right font-semibold text-slate-900">
                  {formatCLP(
                    Number(d.cantidad_pedida) * Number(d.costo_unitario_pactado),
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-slate-50">
              <td colSpan={4} className="px-3 py-2 text-right text-sm font-semibold text-slate-700">
                Total
              </td>
              <td className="px-3 py-2 text-right text-sm font-bold text-indigo-700">
                {formatCLP(detalle.total_estimado)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {esAdminOSupervisor ? (
        <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-3">
          {detalle.estado === "borrador" ? (
            <button
              type="button"
              onClick={() => enviarCorreo(detalle)}
              className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
            >
              Enviar correo al supervisor
            </button>
          ) : null}
          {detalle.estado === "enviado_a_supervisor" ? (
            <>
              <button
                type="button"
                onClick={() => aprobar(detalle)}
                className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500"
              >
                Aprobar
              </button>
              <button
                type="button"
                onClick={() => setShowRechazo((v) => !v)}
                className="rounded-md bg-rose-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-rose-500"
              >
                Rechazar
              </button>
            </>
          ) : null}
          {detalle.estado === "aprobado" ? (
            <button
              type="button"
              onClick={() => marcarComprada(detalle)}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500"
            >
              Marcar como comprada
            </button>
          ) : null}
        </div>
      ) : null}

      {showRechazo ? (
        <div className="space-y-2 rounded-md border border-rose-200 bg-rose-50 p-3">
          <label htmlFor="motivo" className="block text-sm font-medium text-rose-900">
            Motivo del rechazo
          </label>
          <textarea
            id="motivo"
            rows={2}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            className="block w-full rounded-md border border-rose-300 px-2 py-1.5 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setShowRechazo(false);
                setMotivo("");
              }}
              className="rounded-md border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-100"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={() => rechazar(detalle, motivo)}
              disabled={!motivo.trim()}
              className="rounded-md bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Confirmar rechazo
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
