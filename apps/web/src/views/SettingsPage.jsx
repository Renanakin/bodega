// SettingsPage: configuracion del sistema (Fase 8).
//
// Ruta: /settings
//
// Tabs (Tailwind v3, sin CSS plano legacy):
//   - Reglas de Reabastecimiento: tabla CRUD de reglas (usa
//     ReplenishmentRuleForm para crear/editar).
//   - Proveedores: tabla CRUD de proveedores.
//   - Parametros de Stock: tabla de stock_levels con filtros por bodega
//     y edicion inline de min/max.
//
// La version anterior usaba CSS plano legacy + TableSimple/EmptyState.
// Este refactor es 100% Tailwind v3 (ADR-0006) y mantiene la
// compatibilidad funcional con el codigo legacy.
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  deleteJson,
  getErrorMessage,
  getJson,
  patchJson,
  postJson,
  putJson,
} from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";
import { ReplenishmentRuleForm } from "../components/ReplenishmentRuleForm";

const TABS = [
  { id: "reglas", label: "Reglas de Reabastecimiento" },
  { id: "proveedores", label: "Proveedores" },
  { id: "stock", label: "Parametros de Stock" },
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
      <div className="flex w-full max-w-lg flex-col bg-white shadow-xl">
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

function ProveedorForm({ initial, onSubmit, onCancel, submitting, error }) {
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

function TabReglas() {
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const [stockLevels, setStockLevels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drawerMode, setDrawerMode] = useState(null);
  const [editingRule, setEditingRule] = useState(null);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const esAdmin = user?.role === "admin" || user?.role === "supervisor";

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJson("/inventory/stock");
      setStockLevels(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar los parametros de stock."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const abrirCrear = () => {
    setEditingRule(null);
    setFormError(null);
    setDrawerMode("create");
  };
  const abrirEditar = (rule) => {
    setEditingRule({
      ...rule,
      existing_product_id: rule.product_id,
      existing_product_sku: rule.product_sku,
      existing_product_name: rule.product_name,
    });
    setFormError(null);
    setDrawerMode("edit");
  };
  const cerrarDrawer = () => {
    setDrawerMode(null);
    setEditingRule(null);
    setFormError(null);
  };

  const onSubmit = async ({ producto_id, bodega_id, payload }) => {
    setSubmitting(true);
    setFormError(null);
    setPendingLabel(drawerMode === "create" ? "Creando regla..." : "Guardando cambios...");
    try {
      await putJson(
        `/inventory/parametros/${producto_id}/${bodega_id}`,
        payload,
      );
      pushToast({
        tone: "success",
        title: "Regla guardada",
        description: "Parametros actualizados correctamente.",
      });
      cerrarDrawer();
      await cargar();
    } catch (err) {
      const code = err instanceof ApiError ? err.detail?.detail?.code : null;
      if (code === "invalid_stock_parameter") {
        setFormError(err.detail?.detail?.message || "Parametros invalidos.");
      } else {
        setFormError(getErrorMessage(err, "No se pudo guardar la regla."));
      }
    } finally {
      clearPending();
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          Las reglas de reabastecimiento parametrizan los umbrales min/max
          por (producto x bodega). El Evaluator las consulta cada 5 minutos
          para generar solicitudes automaticas.
        </p>
        {esAdmin ? (
          <button
            type="button"
            onClick={abrirCrear}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
          >
            Nueva regla
          </button>
        ) : null}
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-4 text-sm text-slate-500">Cargando reglas...</p>
        ) : error ? (
          <p className="p-4 text-sm text-rose-600">Error: {error}</p>
        ) : stockLevels.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">
            Sin reglas configuradas. Cree la primera para empezar.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2">SKU</th>
                  <th className="px-3 py-2">Producto</th>
                  <th className="px-3 py-2">Bodega</th>
                  <th className="px-3 py-2 text-right">Stock actual</th>
                  <th className="px-3 py-2 text-right">Min.</th>
                  <th className="px-3 py-2 text-right">Max.</th>
                  {esAdmin ? <th className="px-3 py-2 text-right">Acciones</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {stockLevels.slice(0, 50).map((s) => (
                  <tr key={`${s.warehouse_id}-${s.product_id}`} className="hover:bg-slate-50">
                    <td className="px-3 py-1.5 font-mono text-xs text-slate-700">
                      {s.product_sku}
                    </td>
                    <td className="px-3 py-1.5 text-slate-800">{s.product_name}</td>
                    <td className="px-3 py-1.5 text-slate-700">
                      <span className="font-mono text-xs">{s.warehouse_code}</span>{" "}
                      {s.warehouse_name}
                    </td>
                    <td className="px-3 py-1.5 text-right font-semibold text-slate-800">
                      {s.quantity}
                    </td>
                    <td className="px-3 py-1.5 text-right text-slate-600">
                      {s.min_quantity}
                    </td>
                    <td className="px-3 py-1.5 text-right text-slate-500">-</td>
                    {esAdmin ? (
                      <td className="px-3 py-1.5 text-right">
                        <button
                          type="button"
                          onClick={() => abrirEditar(s)}
                          className="rounded border border-indigo-300 px-2 py-0.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                        >
                          Editar
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
            {stockLevels.length > 50 ? (
              <p className="mt-2 px-3 text-xs text-slate-500">
                Mostrando 50 de {stockLevels.length}.
              </p>
            ) : null}
          </div>
        )}
      </div>

      <Drawer
        open={drawerMode !== null}
        onClose={cerrarDrawer}
        title={drawerMode === "create" ? "Nueva regla" : "Editar regla"}
      >
        <ReplenishmentRuleForm
          initial={editingRule}
          onSubmit={onSubmit}
          onCancel={cerrarDrawer}
          submitting={submitting}
          error={formError}
        />
      </Drawer>
    </div>
  );
}

function TabProveedores() {
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

function TabStock() {
  const { user } = useAuth();
  const { pushToast } = useUi();
  const [stockLevels, setStockLevels] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filtroBodega, setFiltroBodega] = useState("");
  const [busqueda, setBusqueda] = useState("");

  const esAdmin = user?.role === "admin" || user?.role === "supervisor";

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, w] = await Promise.all([getJson("/inventory/stock"), getJson("/warehouses")]);
      setStockLevels(Array.isArray(s) ? s : []);
      setWarehouses(Array.isArray(w) ? w : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar el stock."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const itemsFiltrados = useMemo(() => {
    return stockLevels.filter((s) => {
      if (filtroBodega && s.warehouse_id !== filtroBodega) return false;
      if (busqueda.trim()) {
        const q = busqueda.toLowerCase();
        if (
          !s.product_sku?.toLowerCase().includes(q) &&
          !s.product_name?.toLowerCase().includes(q)
        ) return false;
      }
      return true;
    });
  }, [stockLevels, filtroBodega, busqueda]);

  const updateMin = async (s, newMin) => {
    try {
      await putJson(
        `/inventory/parametros/${s.product_id}/${s.warehouse_id}`,
        {
          stock_minimo: Number(newMin),
          stock_maximo: Number(s.max_quantity || newMin),
          lead_time_dias: 7,
        },
      );
      pushToast({ tone: "success", title: "Minimo actualizado", description: s.product_sku });
      await cargar();
    } catch (err) {
      pushToast({ tone: "danger", title: "Error al actualizar", description: getErrorMessage(err) });
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={filtroBodega}
          onChange={(e) => setFiltroBodega(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          aria-label="Filtrar por bodega"
        >
          <option value="">Todas las bodegas</option>
          {warehouses.map((w) => (
            <option key={w.id} value={w.id}>
              {w.code} — {w.name}
            </option>
          ))}
        </select>
        <input
          type="search"
          placeholder="Buscar SKU o nombre..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          className="flex-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          aria-label="Buscar stock"
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
          <p className="p-4 text-sm text-slate-500">Cargando stock...</p>
        ) : error ? (
          <p className="p-4 text-sm text-rose-600">Error: {error}</p>
        ) : itemsFiltrados.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">
            Sin resultados para el filtro aplicado.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2">SKU</th>
                  <th className="px-3 py-2">Producto</th>
                  <th className="px-3 py-2">Bodega</th>
                  <th className="px-3 py-2 text-right">Stock</th>
                  <th className="px-3 py-2 text-right">Min (editable)</th>
                  <th className="px-3 py-2 text-center">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {itemsFiltrados.slice(0, 50).map((s) => {
                  const bajo = Number(s.min_quantity) > 0 && Number(s.quantity) <= Number(s.min_quantity);
                  return (
                    <tr key={`${s.warehouse_id}-${s.product_id}`} className="hover:bg-slate-50">
                      <td className="px-3 py-1.5 font-mono text-xs text-slate-700">
                        {s.product_sku}
                      </td>
                      <td className="px-3 py-1.5 text-slate-800">{s.product_name}</td>
                      <td className="px-3 py-1.5 text-slate-700">
                        <span className="font-mono text-xs">{s.warehouse_code}</span>
                      </td>
                      <td className="px-3 py-1.5 text-right font-semibold text-slate-800">
                        {s.quantity}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        {esAdmin ? (
                          <input
                            type="number"
                            min="0"
                            defaultValue={s.min_quantity}
                            onBlur={(e) => {
                              const val = e.target.value;
                              if (val !== String(s.min_quantity)) {
                                updateMin(s, val);
                              }
                            }}
                            className="w-20 rounded-md border border-slate-300 px-1 py-0.5 text-right text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                            aria-label={`Editar minimo de ${s.product_sku}`}
                          />
                        ) : (
                          <span className="text-slate-600">{s.min_quantity}</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-center">
                        {bajo ? (
                          <span className="inline-flex items-center rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-800 ring-1 ring-rose-300">
                            Bajo minimo
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800 ring-1 ring-emerald-300">
                            OK
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {itemsFiltrados.length > 50 ? (
              <p className="mt-2 px-3 text-xs text-slate-500">
                Mostrando 50 de {itemsFiltrados.length}.
              </p>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

export function SettingsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("reglas");

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Configuracion
        </p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">
          Parametros del sistema
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Sesion activa: {user?.full_name} ({user?.role}). Cambios en
          parametros afectan directamente al Evaluator y a la generacion
          automatica de solicitudes.
        </p>
      </header>

      <div className="border-b border-slate-200" role="tablist" aria-label="Tabs de configuracion">
        <nav className="flex flex-wrap space-x-2">
          {TABS.map((t) => (
            <TabButton key={t.id} active={tab === t.id} onClick={() => setTab(t.id)}>
              {t.label}
            </TabButton>
          ))}
        </nav>
      </div>

      <div role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "reglas" ? <TabReglas /> : tab === "proveedores" ? <TabProveedores /> : <TabStock />}
      </div>
    </div>
  );
}
