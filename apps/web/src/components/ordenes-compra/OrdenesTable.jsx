// Tabla de Ordenes de Compra con badges de estado y acciones por fila.
import { ESTADO_BADGE, ESTADOS } from "./constants";
import { formatCLP, formatFecha } from "./formatters";

export function OrdenesTable({
  loading,
  error,
  ordenes,
  esAdminOSupervisor,
  abrirDetalle,
  enviarCorreo,
}) {
  if (loading) {
    return <p className="p-6 text-sm text-slate-500">Cargando ordenes...</p>;
  }
  if (error) {
    return <p className="p-6 text-sm text-rose-600">Error: {error}</p>;
  }
  if (ordenes.length === 0) {
    return (
      <div className="p-8 text-center">
        <p className="text-base font-semibold text-slate-700">
          Sin ordenes de compra
        </p>
        <p className="mt-1 text-sm text-slate-500">
          Cree la primera OC con el boton "Nueva OC" arriba.
        </p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            <th scope="col" className="px-4 py-2">Codigo</th>
            <th scope="col" className="px-4 py-2">Proveedor</th>
            <th scope="col" className="px-4 py-2">Supervisor</th>
            <th scope="col" className="px-4 py-2 text-right">Items</th>
            <th scope="col" className="px-4 py-2 text-right">Total</th>
            <th scope="col" className="px-4 py-2 text-center">Estado</th>
            <th scope="col" className="px-4 py-2">Fecha</th>
            <th scope="col" className="px-4 py-2 text-right">Acciones</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {ordenes.map((o) => (
            <tr key={o.id} className="hover:bg-slate-50">
              <td className="px-4 py-2">
                <button
                  type="button"
                  onClick={() => abrirDetalle(o)}
                  className="font-mono text-sm font-semibold text-indigo-700 hover:underline"
                >
                  {o.codigo}
                </button>
              </td>
              <td className="px-4 py-2 text-slate-800">{o.proveedor_nombre}</td>
              <td className="px-4 py-2 text-slate-700">
                {o.supervisor_nombre ? (
                  <span>
                    {o.supervisor_nombre}
                    <span className="block text-xs text-slate-500">
                      {o.supervisor_email}
                    </span>
                  </span>
                ) : (
                  <span className="text-slate-400">-</span>
                )}
              </td>
              <td className="px-4 py-2 text-right text-slate-700">
                {o.detalles?.length || 0}
              </td>
              <td className="px-4 py-2 text-right font-mono text-sm text-slate-900">
                {formatCLP(o.total_estimado)}
              </td>
              <td className="px-4 py-2 text-center">
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                    ESTADO_BADGE[o.estado] || "bg-slate-100 text-slate-700"
                  }`}
                >
                  {ESTADOS.find((e) => e.value === o.estado)?.label || o.estado}
                </span>
              </td>
              <td className="px-4 py-2 text-xs text-slate-500">
                {formatFecha(o.created_at)}
              </td>
              <td className="px-4 py-2 text-right">
                <div className="flex flex-wrap justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => abrirDetalle(o)}
                    className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Ver
                  </button>
                  {esAdminOSupervisor && o.estado === "borrador" ? (
                    <button
                      type="button"
                      onClick={() => enviarCorreo(o)}
                      className="rounded border border-indigo-300 px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                      title="Genera token + encola email al supervisor"
                    >
                      Enviar correo
                    </button>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
