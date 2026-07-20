// Formulario de creacion de una nueva Orden de Compra.
//
// Props:
// - bodegas: lista de bodegas tipo "principal".
// - supervisores: lista de supervisores activos.
// - productos: catalogo de productos para elegir lineas.
// - onCreate: callback(payload) con el shape del endpoint POST /ordenes-compra.
// - onCancel: callback para cerrar el drawer sin crear.
// - submitting: bool que deshabilita los botones mientras se crea.
// - error: mensaje de error a mostrar arriba del footer del form.
import { useState } from "react";
import { formatCLP } from "./formatters";

export function NuevaOCForm({
  initial,
  bodegas,
  supervisores,
  productos,
  onCreate,
  onCancel,
  submitting,
  error,
}) {
  const [proveedorNombre, setProveedorNombre] = useState(initial?.proveedor_nombre || "");
  const [proveedorContacto, setProveedorContacto] = useState(initial?.proveedor_contacto || "");
  const [idBodega, setIdBodega] = useState(initial?.id_bodega_principal || (bodegas[0]?.id ?? ""));
  const [idSupervisor, setIdSupervisor] = useState(initial?.id_supervisor || "");
  const [notas, setNotas] = useState(initial?.notas || "");
  const [lineas, setLineas] = useState(
    initial?.lineas || [{ id_producto: "", cantidad_pedida: 1, costo_unitario_pactado: 0 }],
  );

  const bodegaOk = idBodega;
  const supervisorOk = idSupervisor;
  const lineasOk =
    lineas.length > 0 &&
    lineas.every(
      (l) => l.id_producto && Number(l.cantidad_pedida) > 0 && Number(l.costo_unitario_pactado) >= 0,
    );
  const formOk = proveedorNombre.trim() && bodegaOk && supervisorOk && lineasOk;

  const agregarLinea = () => {
    setLineas((ls) => [
      ...ls,
      { id_producto: "", cantidad_pedida: 1, costo_unitario_pactado: 0 },
    ]);
  };
  const quitarLinea = (idx) => {
    setLineas((ls) => ls.filter((_, i) => i !== idx));
  };
  const actualizarLinea = (idx, campo, valor) => {
    setLineas((ls) =>
      ls.map((l, i) => (i === idx ? { ...l, [campo]: valor } : l)),
    );
  };

  const totalEstimado = lineas.reduce(
    (acc, l) =>
      acc + Number(l.cantidad_pedida || 0) * Number(l.costo_unitario_pactado || 0),
    0,
  );

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formOk) return;
    onCreate({
      id_bodega_principal: idBodega,
      id_supervisor: idSupervisor,
      proveedor_nombre: proveedorNombre.trim(),
      proveedor_contacto: proveedorContacto.trim() || null,
      notas: notas.trim() || null,
      lineas: lineas.map((l) => ({
        id_producto: l.id_producto,
        cantidad_pedida: Number(l.cantidad_pedida),
        costo_unitario_pactado: Number(l.costo_unitario_pactado),
      })),
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="prov-nombre" className="block text-sm font-medium text-slate-700">
            Nombre del proveedor
          </label>
          <input
            id="prov-nombre"
            type="text"
            required
            value={proveedorNombre}
            onChange={(e) => setProveedorNombre(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label htmlFor="prov-contacto" className="block text-sm font-medium text-slate-700">
            Contacto (opcional)
          </label>
          <input
            id="prov-contacto"
            type="text"
            value={proveedorContacto || ""}
            onChange={(e) => setProveedorContacto(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="bodega" className="block text-sm font-medium text-slate-700">
            Bodega principal
          </label>
          <select
            id="bodega"
            required
            value={idBodega}
            onChange={(e) => setIdBodega(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Seleccionar...</option>
            {bodegas.map((b) => (
              <option key={b.id} value={b.id}>
                {b.codigo} - {b.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="supervisor" className="block text-sm font-medium text-slate-700">
            Supervisor autorizador
          </label>
          <select
            id="supervisor"
            required
            value={idSupervisor}
            onChange={(e) => setIdSupervisor(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="">Seleccionar supervisor...</option>
            {supervisores.map((s) => (
              <option key={s.id} value={s.id}>
                {s.nombre} ({s.email})
              </option>
            ))}
          </select>
          {supervisores.length === 0 ? (
            <p className="mt-1 text-xs text-rose-600">
              No hay supervisores activos. Cree uno en /supervisores.
            </p>
          ) : null}
        </div>
      </div>
      <div>
        <label htmlFor="notas" className="block text-sm font-medium text-slate-700">
          Notas (opcional)
        </label>
        <textarea
          id="notas"
          rows={2}
          value={notas}
          onChange={(e) => setNotas(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>

      <div>
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-slate-700">Lineas</p>
          <button
            type="button"
            onClick={agregarLinea}
            className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            + Agregar linea
          </button>
        </div>
        <div className="mt-2 space-y-2">
          {lineas.map((l, idx) => (
            <div
              key={idx}
              className="grid grid-cols-12 items-end gap-2 rounded-md border border-slate-200 bg-slate-50 p-2"
            >
              <div className="col-span-6">
                <label className="text-xs text-slate-600">Producto</label>
                <select
                  value={l.id_producto}
                  onChange={(e) => actualizarLinea(idx, "id_producto", e.target.value)}
                  required
                  className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
                >
                  <option value="">Seleccionar SKU...</option>
                  {productos.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku} - {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-xs text-slate-600">Cantidad</label>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  value={l.cantidad_pedida}
                  onChange={(e) =>
                    actualizarLinea(idx, "cantidad_pedida", e.target.value)
                  }
                  className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                />
              </div>
              <div className="col-span-3">
                <label className="text-xs text-slate-600">Costo unit. (CLP)</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  required
                  value={l.costo_unitario_pactado}
                  onChange={(e) =>
                    actualizarLinea(idx, "costo_unitario_pactado", e.target.value)
                  }
                  className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
                />
              </div>
              <div className="col-span-1">
                {lineas.length > 1 ? (
                  <button
                    type="button"
                    onClick={() => quitarLinea(idx)}
                    className="rounded p-1 text-rose-600 hover:bg-rose-50"
                    aria-label="Quitar linea"
                    title="Quitar"
                  >
                    <span aria-hidden="true">x</span>
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-2 flex justify-end text-sm">
          <p className="font-semibold text-slate-700">
            Total estimado:{" "}
            <span className="text-indigo-700">
              {formatCLP(totalEstimado)}
            </span>
          </p>
        </div>
      </div>

      {error ? (
        <p className="rounded-md border border-rose-200 bg-rose-50 p-2 text-sm text-rose-700">
          {error}
        </p>
      ) : null}

      <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={submitting || !formOk}
          className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Creando..." : "Crear borrador"}
        </button>
      </div>
    </form>
  );
}
