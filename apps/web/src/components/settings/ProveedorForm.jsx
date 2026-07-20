// Formulario de creacion/edicion de un Proveedor.
import { useState } from "react";

export function ProveedorForm({ initial, onSubmit, onCancel, submitting, error }) {
  const [nombre, setNombre] = useState(initial?.nombre || "");
  const [rut, setRut] = useState(initial?.rut || "");
  const [email, setEmail] = useState(initial?.email || "");
  const [telefono, setTelefono] = useState(initial?.telefono || "");
  const [direccion, setDireccion] = useState(initial?.direccion || "");
  const [contacto, setContacto] = useState(initial?.contacto_nombre || "");
  const [leadTime, setLeadTime] = useState(initial?.lead_time_dias ?? 7);
  const esEdicion = Boolean(initial?.id);
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({
      nombre: nombre.trim(),
      rut: rut.trim() || null,
      email: email.trim() || null,
      telefono: telefono.trim() || null,
      direccion: direccion.trim() || null,
      contacto_nombre: contacto.trim() || null,
      lead_time_dias: Number(leadTime),
    });
  };
  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label htmlFor="prov-nombre" className="block text-sm font-medium text-slate-700">
          Nombre
        </label>
        <input
          id="prov-nombre"
          type="text"
          required
          maxLength={200}
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="prov-rut" className="block text-sm font-medium text-slate-700">
            RUT
          </label>
          <input
            id="prov-rut"
            type="text"
            maxLength={20}
            value={rut}
            onChange={(e) => setRut(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label htmlFor="prov-lead" className="block text-sm font-medium text-slate-700">
            Lead time (dias)
          </label>
          <input
            id="prov-lead"
            type="number"
            min="0"
            max="365"
            value={leadTime}
            onChange={(e) => setLeadTime(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
      </div>
      <div>
        <label htmlFor="prov-email" className="block text-sm font-medium text-slate-700">
          Email
        </label>
        <input
          id="prov-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="prov-tel" className="block text-sm font-medium text-slate-700">
            Telefono
          </label>
          <input
            id="prov-tel"
            type="text"
            maxLength={30}
            value={telefono}
            onChange={(e) => setTelefono(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label htmlFor="prov-contacto" className="block text-sm font-medium text-slate-700">
            Contacto
          </label>
          <input
            id="prov-contacto"
            type="text"
            maxLength={150}
            value={contacto}
            onChange={(e) => setContacto(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
      </div>
      <div>
        <label htmlFor="prov-dir" className="block text-sm font-medium text-slate-700">
          Direccion
        </label>
        <input
          id="prov-dir"
          type="text"
          maxLength={300}
          value={direccion}
          onChange={(e) => setDireccion(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
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
          disabled={submitting}
          className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Guardando..." : esEdicion ? "Guardar cambios" : "Crear proveedor"}
        </button>
      </div>
    </form>
  );
}
