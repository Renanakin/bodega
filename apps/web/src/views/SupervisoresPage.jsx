// SupervisoresPage: CRUD de la entidad de dominio Supervisores (Fase 6).
//
// Distinto de `users.role='supervisor'` (auth): esta entidad es la persona
// fisica con email que recibe la notificacion de OC y autoriza por token.
//
// Ruta: /supervisores
//
// Caracteristicas:
// - Tabla con filtros por estado (todos / activos / inactivos).
// - Boton "Nuevo supervisor" abre un drawer lateral con form.
// - Click en fila abre drawer de edicion.
// - Toggle activo/inactivo inline.
// - Soft delete con confirmacion (DELETE /api/v1/supervisores/{id}).
// - Disenada 100% con Tailwind v3 (sin CSS plano legacy).
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  getErrorMessage,
  getJson,
  patchJson,
  postJson,
  deleteJson,
} from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

const FILTROS = [
  { value: "todos", label: "Todos" },
  { value: "activo", label: "Solo activos" },
  { value: "inactivo", label: "Solo inactivos" },
];

function Drawer({ open, onClose, children, title }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <button
        type="button"
        onClick={onClose}
        className="flex-1 bg-slate-900/50 backdrop-blur-sm"
        aria-label="Cerrar"
      />
      <div className="flex w-full max-w-md flex-col bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-500 hover:bg-slate-100"
            aria-label="Cerrar"
          >
            <span aria-hidden="true">x</span>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>
  );
}

function SupervisorForm({ initial, onSubmit, onCancel, submitting, error }) {
  const [nombre, setNombre] = useState(initial?.nombre || "");
  const [email, setEmail] = useState(initial?.email || "");
  const [telefono, setTelefono] = useState(initial?.telefono || "");
  const [cargo, setCargo] = useState(initial?.cargo || "");

  const esEdicion = Boolean(initial?.id);
  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({
      nombre: nombre.trim(),
      email: email.trim(),
      telefono: telefono.trim() || null,
      cargo: cargo.trim() || null,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label htmlFor="sup-nombre" className="block text-sm font-medium text-slate-700">
          Nombre completo
        </label>
        <input
          id="sup-nombre"
          type="text"
          required
          minLength={1}
          maxLength={150}
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      <div>
        <label htmlFor="sup-email" className="block text-sm font-medium text-slate-700">
          Email
        </label>
        <input
          id="sup-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={esEdicion}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-100 disabled:text-slate-500"
        />
        {esEdicion ? (
          <p className="mt-1 text-xs text-slate-500">
            El email no se puede modificar (es la credencial de contacto).
          </p>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="sup-tel" className="block text-sm font-medium text-slate-700">
            Telefono
          </label>
          <input
            id="sup-tel"
            type="text"
            maxLength={30}
            value={telefono || ""}
            onChange={(e) => setTelefono(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>
        <div>
          <label htmlFor="sup-cargo" className="block text-sm font-medium text-slate-700">
            Cargo
          </label>
          <input
            id="sup-cargo"
            type="text"
            maxLength={100}
            value={cargo || ""}
            onChange={(e) => setCargo(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
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
          disabled={submitting}
          className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Guardando..." : esEdicion ? "Guardar cambios" : "Crear supervisor"}
        </button>
      </div>
    </form>
  );
}

export function SupervisoresPage() {
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();

  const [supervisores, setSupervisores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filtro, setFiltro] = useState("todos");
  const [busqueda, setBusqueda] = useState("");

  const [drawerMode, setDrawerMode] = useState(null); // 'create' | 'edit' | null
  const [editingSupervisor, setEditingSupervisor] = useState(null);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const esAdmin = user?.role === "admin";

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filtro === "activo") params.set("activo", "true");
      if (filtro === "inactivo") params.set("activo", "false");
      const query = params.toString() ? `?${params.toString()}` : "";
      const data = await getJson(`/supervisores${query}`);
      setSupervisores(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar el catalogo de supervisores."));
    } finally {
      setLoading(false);
    }
  }, [filtro]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const itemsFiltrados = useMemo(() => {
    if (!busqueda.trim()) return supervisores;
    const q = busqueda.toLowerCase();
    return supervisores.filter(
      (s) =>
        s.nombre.toLowerCase().includes(q) ||
        s.email.toLowerCase().includes(q) ||
        (s.cargo || "").toLowerCase().includes(q),
    );
  }, [supervisores, busqueda]);

  const abrirCrear = () => {
    setEditingSupervisor(null);
    setFormError(null);
    setDrawerMode("create");
  };
  const abrirEditar = (sup) => {
    setEditingSupervisor(sup);
    setFormError(null);
    setDrawerMode("edit");
  };
  const cerrarDrawer = () => {
    setDrawerMode(null);
    setEditingSupervisor(null);
    setFormError(null);
  };

  const onSubmit = async (payload) => {
    setSubmitting(true);
    setFormError(null);
    setPendingLabel(drawerMode === "create" ? "Creando..." : "Guardando...");
    try {
      if (drawerMode === "create") {
        const nuevo = await postJson("/supervisores", payload);
        pushToast({ tone: "success", title: "Supervisor creado", description: nuevo.nombre });
      } else if (drawerMode === "edit" && editingSupervisor) {
        const actualizado = await patchJson(
          `/supervisores/${editingSupervisor.id}`,
          payload,
        );
        pushToast({ tone: "success", title: "Supervisor actualizado", description: actualizado.nombre });
      }
      cerrarDrawer();
      await cargar();
    } catch (err) {
      const code = err instanceof ApiError ? err.detail?.detail?.code : null;
      if (code === "duplicate_supervisor_email") {
        setFormError("Ya existe un supervisor con ese email.");
      } else {
        setFormError(getErrorMessage(err, "No se pudo guardar el supervisor."));
      }
    } finally {
      clearPending();
      setSubmitting(false);
    }
  };

  const toggleActivo = async (sup) => {
    setPendingLabel(sup.activo ? "Desactivando..." : "Activando...");
    try {
      await patchJson(`/supervisores/${sup.id}`, { activo: !sup.activo });
      pushToast({
        tone: "info",
        title: sup.activo ? "Supervisor desactivado" : "Supervisor activado",
        description: sup.nombre,
      });
      await cargar();
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al cambiar estado",
        description: getErrorMessage(err),
      });
    } finally {
      clearPending();
    }
  };

  const desactivar = async (sup) => {
    setConfirmDelete(null);
    setPendingLabel("Desactivando supervisor...");
    try {
      await deleteJson(`/supervisores/${sup.id}`);
      pushToast({
        tone: "info",
        title: "Supervisor desactivado",
        description: sup.nombre,
      });
      await cargar();
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al desactivar",
        description: getErrorMessage(err),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Catalogo
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Supervisores de Turno
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Personas fisicas con email que reciben las solicitudes de
            aprobacion de Ordenes de Compra externas.
          </p>
        </div>
        {esAdmin ? (
          <button
            type="button"
            onClick={abrirCrear}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
          >
            Nuevo supervisor
          </button>
        ) : null}
      </header>

      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="filtro" className="text-sm font-medium text-slate-700">
            Estado:
          </label>
          <select
            id="filtro"
            value={filtro}
            onChange={(e) => setFiltro(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            {FILTROS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <input
            type="search"
            placeholder="Buscar por nombre, email o cargo..."
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 sm:max-w-xs"
          />
        </div>
        <button
          type="button"
          onClick={cargar}
          className="self-start rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 sm:self-auto"
        >
          Refrescar
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">Cargando supervisores...</p>
        ) : error ? (
          <p className="p-6 text-sm text-rose-600">Error: {error}</p>
        ) : itemsFiltrados.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-base font-semibold text-slate-700">
              Sin supervisores para mostrar
            </p>
            <p className="mt-1 text-sm text-slate-500">
              {busqueda.trim() || filtro !== "todos"
                ? "Pruebe ajustar los filtros o la busqueda."
                : "Cree el primer supervisor para empezar a enviar ordenes de compra."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th scope="col" className="px-4 py-2">Nombre</th>
                  <th scope="col" className="px-4 py-2">Email</th>
                  <th scope="col" className="px-4 py-2">Cargo</th>
                  <th scope="col" className="px-4 py-2 text-center">Estado</th>
                  {esAdmin ? (
                    <th scope="col" className="px-4 py-2 text-right">Acciones</th>
                  ) : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {itemsFiltrados.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2 text-slate-800">
                      <button
                        type="button"
                        onClick={() => esAdmin && abrirEditar(s)}
                        className={`text-left ${
                          esAdmin
                            ? "cursor-pointer font-medium text-indigo-700 hover:underline"
                            : "cursor-default"
                        }`}
                        disabled={!esAdmin}
                      >
                        {s.nombre}
                      </button>
                      {s.telefono ? (
                        <p className="text-xs text-slate-500">{s.telefono}</p>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 text-slate-700">
                      <span className="font-mono text-xs">{s.email}</span>
                    </td>
                    <td className="px-4 py-2 text-slate-700">{s.cargo || "-"}</td>
                    <td className="px-4 py-2 text-center">
                      {s.activo ? (
                        <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-300">
                          Activo
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-700 ring-1 ring-slate-300">
                          Inactivo
                        </span>
                      )}
                    </td>
                    {esAdmin ? (
                      <td className="px-4 py-2 text-right">
                        <div className="flex flex-wrap justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => toggleActivo(s)}
                            className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                            title={s.activo ? "Desactivar" : "Activar"}
                          >
                            {s.activo ? "Desactivar" : "Activar"}
                          </button>
                          {s.activo ? (
                            <button
                              type="button"
                              onClick={() => setConfirmDelete(s)}
                              className="rounded border border-rose-300 px-2 py-1 text-xs font-medium text-rose-700 hover:bg-rose-50"
                              title="Soft delete"
                            >
                              Eliminar
                            </button>
                          ) : null}
                        </div>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-500">
        Soft delete: el supervisor desactivado se conserva en la base de
        datos para mantener el historial de Ordenes de Compra que autorizo.
        Las Ordenes de Compra nuevas no podran seleccionarlo.
      </p>

      <Drawer
        open={drawerMode !== null}
        onClose={cerrarDrawer}
        title={drawerMode === "create" ? "Nuevo supervisor" : "Editar supervisor"}
      >
        <SupervisorForm
          initial={editingSupervisor}
          onSubmit={onSubmit}
          onCancel={cerrarDrawer}
          submitting={submitting}
          error={formError}
        />
      </Drawer>

      {confirmDelete ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
            <h2 className="text-base font-semibold text-slate-900">
              Confirmar desactivacion
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              El supervisor{" "}
              <span className="font-semibold">{confirmDelete.nombre}</span>{" "}
              quedara inactivo. No podra recibir nuevas Ordenes de Compra,
              pero su historial se conserva.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmDelete(null)}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => desactivar(confirmDelete)}
                className="rounded-md bg-rose-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-rose-500"
              >
                Desactivar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
