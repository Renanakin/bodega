// Tab "Proveedores" de la pagina de Settings.
// CRUD con filtros (todos/activo/inactivo) y busqueda.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  deleteJson,
  getErrorMessage,
  getJson,
  patchJson,
  postJson,
} from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { useUi } from "../../context/UiContext";
import { Drawer } from "./Drawer";
import { ProveedorForm } from "./ProveedorForm";

export function TabProveedores() {
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const [proveedores, setProveedores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busqueda, setBusqueda] = useState("");
  const [filtro, setFiltro] = useState("todos");
  const [drawerMode, setDrawerMode] = useState(null);
  const [editing, setEditing] = useState(null);
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
      const data = await getJson(`/proveedores${query}`);
      setProveedores(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar los proveedores."));
    } finally {
      setLoading(false);
    }
  }, [filtro]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const itemsFiltrados = useMemo(() => {
    if (!busqueda.trim()) return proveedores;
    const q = busqueda.toLowerCase();
    return proveedores.filter(
      (p) =>
        p.nombre.toLowerCase().includes(q) ||
        (p.rut || "").toLowerCase().includes(q) ||
        (p.email || "").toLowerCase().includes(q),
    );
  }, [proveedores, busqueda]);

  const onSubmit = async (payload) => {
    setSubmitting(true);
    setFormError(null);
    setPendingLabel(drawerMode === "create" ? "Creando..." : "Guardando...");
    try {
      if (drawerMode === "create") {
        await postJson("/proveedores", payload);
        pushToast({ tone: "success", title: "Proveedor creado", description: payload.nombre });
      } else if (drawerMode === "edit" && editing) {
        await patchJson(`/proveedores/${editing.id}`, payload);
        pushToast({ tone: "success", title: "Proveedor actualizado", description: payload.nombre });
      }
      cerrarDrawer();
      await cargar();
    } catch (err) {
      const code = err instanceof ApiError ? err.detail?.detail?.code : null;
      if (code === "duplicate_proveedor_nombre") {
        setFormError("Ya existe un proveedor con ese nombre.");
      } else if (code === "duplicate_proveedor_rut") {
        setFormError("Ya existe un proveedor con ese RUT.");
      } else {
        setFormError(getErrorMessage(err, "No se pudo guardar el proveedor."));
      }
    } finally {
      clearPending();
      setSubmitting(false);
    }
  };

  const eliminar = async (p) => {
    setConfirmDelete(null);
    setPendingLabel("Desactivando...");
    try {
      await deleteJson(`/proveedores/${p.id}`);
      pushToast({ tone: "info", title: "Proveedor desactivado", description: p.nombre });
      await cargar();
    } catch (err) {
      pushToast({ tone: "danger", title: "Error al desactivar", description: getErrorMessage(err) });
    } finally {
      clearPending();
    }
  };

  const cerrarDrawer = () => {
    setDrawerMode(null);
    setEditing(null);
    setFormError(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {esAdmin ? (
          <button
            type="button"
            onClick={() => {
              setEditing(null);
              setFormError(null);
              setDrawerMode("create");
            }}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
          >
            Nuevo proveedor
          </button>
        ) : null}
        <select
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          aria-label="Filtrar proveedores por estado"
        >
          <option value="todos">Todos</option>
          <option value="activo">Solo activos</option>
          <option value="inactivo">Solo inactivos</option>
        </select>
        <input
          type="search"
          placeholder="Buscar por nombre, RUT o email..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          className="flex-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          aria-label="Buscar proveedores"
        />
        <button
          type="button"
          onClick={cargar}
          className="rounded-md border border-slate-300 bg-white px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Refrescar
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-4 text-sm text-slate-500">Cargando proveedores...</p>
        ) : error ? (
          <p className="p-4 text-sm text-rose-600">Error: {error}</p>
        ) : itemsFiltrados.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">
            Sin proveedores para los filtros aplicados.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2">Nombre</th>
                  <th className="px-3 py-2">RUT</th>
                  <th className="px-3 py-2">Email</th>
                  <th className="px-3 py-2 text-right">Lead time</th>
                  <th className="px-3 py-2 text-center">Estado</th>
                  {esAdmin ? <th className="px-3 py-2 text-right">Acciones</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {itemsFiltrados.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50">
                    <td className="px-3 py-1.5 text-slate-800">
                      {p.nombre}
                      {p.contacto_nombre ? (
                        <p className="text-xs text-slate-500">Contacto: {p.contacto_nombre}</p>
                      ) : null}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-xs text-slate-700">
                      {p.rut || "-"}
                    </td>
                    <td className="px-3 py-1.5 text-slate-700">{p.email || "-"}</td>
                    <td className="px-3 py-1.5 text-right text-slate-700">
                      {p.lead_time_dias} d
                    </td>
                    <td className="px-3 py-1.5 text-center">
                      {p.activo ? (
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
                      <td className="px-3 py-1.5 text-right">
                        <div className="flex justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => {
                              setEditing(p);
                              setFormError(null);
                              setDrawerMode("edit");
                            }}
                            className="rounded border border-indigo-300 px-2 py-0.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                          >
                            Editar
                          </button>
                          {p.activo ? (
                            <button
                              type="button"
                              onClick={() => setConfirmDelete(p)}
                              className="rounded border border-rose-300 px-2 py-0.5 text-xs font-medium text-rose-700 hover:bg-rose-50"
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

      <Drawer
        open={drawerMode !== null}
        onClose={cerrarDrawer}
        title={drawerMode === "create" ? "Nuevo proveedor" : "Editar proveedor"}
      >
        <ProveedorForm
          initial={editing}
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
              El proveedor <span className="font-semibold">{confirmDelete.nombre}</span>{" "}
              quedara inactivo. Las OCs que ya lo referencian conservan su
              nombre (snapshot), pero no podra ser seleccionado en OCs nuevas.
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
                onClick={() => eliminar(confirmDelete)}
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
