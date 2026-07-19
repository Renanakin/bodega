// OrdenesCompraPage: gestion de Ordenes de Compra externas (Fase 6).
//
// Ruta: /ordenes-compra
//
// Caracteristicas:
// - Tabla con filtros (estado, proveedor, rango fechas).
// - Boton "Nueva OC" abre drawer con form completo: proveedor, lineas,
//   supervisor (dropdown que carga GET /supervisores?activo=true).
// - Boton "Enviar Detalle por Correo" en OC Borrador (POST /enviar-correo).
// - Drawer de detalle con timeline de estados al click en una fila.
// - Botones internos: Aprobar, Rechazar, Marcar comprada (segun estado).
// - Disenada 100% con Tailwind v3 (sin CSS plano legacy).
import { useCallback, useEffect, useState } from "react";

import { getErrorMessage, getJson, postJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

const ESTADOS = [
  { value: "", label: "Todos" },
  { value: "borrador", label: "Borrador" },
  { value: "enviado_a_supervisor", label: "Enviado a supervisor" },
  { value: "aprobado", label: "Aprobado" },
  { value: "rechazado", label: "Rechazado" },
  { value: "comprado", label: "Comprado" },
];

const ESTADO_BADGE = {
  borrador: "bg-slate-100 text-slate-700 ring-1 ring-slate-300",
  enviado_a_supervisor: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  aprobado: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
  rechazado: "bg-rose-100 text-rose-800 ring-1 ring-rose-300",
  comprado: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
};

const ESTADO_TIMELINE = {
  borrador: ["Borrador"],
  enviado_a_supervisor: ["Borrador", "Enviado a supervisor"],
  aprobado: ["Borrador", "Enviado a supervisor", "Aprobado"],
  rechazado: ["Borrador", "Enviado a supervisor", "Rechazado"],
  comprado: ["Borrador", "Enviado a supervisor", "Aprobado", "Comprado"],
};

function formatCLP(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  });
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
      <div className="flex w-full max-w-2xl flex-col bg-white shadow-xl">
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

function Timeline({ estado, email_enviado_at, aprobado_at, comprado_at }) {
  const pasos = ESTADO_TIMELINE[estado] || ["Borrador"];
  const idxActual = pasos.length - 1;
  return (
    <ol className="space-y-1 text-sm">
      {pasos.map((p, i) => (
        <li key={p} className="flex items-center gap-2">
          <span
            className={`flex h-5 w-5 items-center justify-center rounded-full text-xs font-bold ${
              i <= idxActual
                ? "bg-indigo-600 text-white"
                : "bg-slate-200 text-slate-500"
            }`}
            aria-hidden="true"
          >
            {i + 1}
          </span>
          <span className={i <= idxActual ? "font-medium text-slate-900" : "text-slate-500"}>
            {p}
          </span>
        </li>
      ))}
      <li className="ml-7 mt-2 space-y-0.5 text-xs text-slate-500">
        {email_enviado_at ? (
          <p>Email enviado: {formatFecha(email_enviado_at)}</p>
        ) : null}
        {aprobado_at ? <p>Aprobado: {formatFecha(aprobado_at)}</p> : null}
        {comprado_at ? <p>Comprado: {formatFecha(comprado_at)}</p> : null}
      </li>
    </ol>
  );
}

function NuevaOCForm({
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

export function OrdenesCompraPage() {
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();

  const [ordenes, setOrdenes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filtros
  const [estadoFiltro, setEstadoFiltro] = useState("");
  const [proveedorFiltro, setProveedorFiltro] = useState("");
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");

  // Drawers
  const [drawerMode, setDrawerMode] = useState(null); // 'create' | 'detail' | null
  const [detalle, setDetalle] = useState(null);
  const [detalleLoading, setDetalleLoading] = useState(false);

  // Catalogos
  const [bodegas, setBodegas] = useState([]);
  const [supervisores, setSupervisores] = useState([]);
  const [productos, setProductos] = useState([]);

  // Form state (create)
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Rechazo
  const [showRechazo, setShowRechazo] = useState(false);
  const [motivo, setMotivo] = useState("");

  const esAdminOSupervisor = user?.role === "admin" || user?.role === "supervisor";

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (estadoFiltro) params.set("estado", estadoFiltro);
      if (proveedorFiltro.trim()) params.set("proveedor", proveedorFiltro.trim());
      if (fechaDesde) params.set("fecha_desde", new Date(`${fechaDesde}T00:00:00`).toISOString());
      if (fechaHasta) params.set("fecha_hasta", new Date(`${fechaHasta}T23:59:59`).toISOString());
      const query = params.toString() ? `?${params.toString()}` : "";
      const data = await getJson(`/ordenes-compra${query}`);
      setOrdenes(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar las Ordenes de Compra."));
    } finally {
      setLoading(false);
    }
  }, [estadoFiltro, proveedorFiltro, fechaDesde, fechaHasta]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const cargarCatalogos = useCallback(async () => {
    try {
      const [wh, sup, prod] = await Promise.all([
        getJson("/warehouses"),
        getJson("/supervisores?activo=true"),
        getJson("/products"),
      ]);
      const allWh = Array.isArray(wh) ? wh : [];
      // El endpoint de warehouses no acepta ?type, filtramos en cliente.
      setBodegas(allWh.filter((b) => b.warehouse_type === "principal"));
      setSupervisores(Array.isArray(sup) ? sup : []);
      setProductos(Array.isArray(prod) ? prod : []);
    } catch {
      // best-effort: los catalogos se rellenaran en el proximo intento
    }
  }, []);

  useEffect(() => {
    cargarCatalogos();
  }, [cargarCatalogos]);

  const abrirDetalle = async (oc) => {
    setDrawerMode("detail");
    setDetalle(oc);
    setDetalleLoading(true);
    try {
      const data = await getJson(`/ordenes-compra/${oc.id}`);
      setDetalle(data);
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al cargar detalle",
        description: getErrorMessage(err),
      });
    } finally {
      setDetalleLoading(false);
    }
  };

  const abrirCrear = () => {
    setFormError(null);
    setDrawerMode("create");
  };
  const cerrarDrawer = () => {
    setDrawerMode(null);
    setDetalle(null);
    setShowRechazo(false);
    setMotivo("");
    setFormError(null);
  };

  const onCrear = async (payload) => {
    setSubmitting(true);
    setFormError(null);
    setPendingLabel("Creando OC...");
    try {
      const oc = await postJson("/ordenes-compra", payload);
      pushToast({ tone: "success", title: "OC creada", description: oc.codigo });
      cerrarDrawer();
      await cargar();
    } catch (err) {
      setFormError(getErrorMessage(err, "No se pudo crear la OC."));
    } finally {
      clearPending();
      setSubmitting(false);
    }
  };

  const enviarCorreo = async (oc) => {
    setPendingLabel("Encolando email al supervisor...");
    try {
      await postJson(`/ordenes-compra/${oc.id}/enviar-correo`);
      pushToast({
        tone: "success",
        title: "Email encolado",
        description: `La OC ${oc.codigo} fue encolada para envio al supervisor.`,
      });
      await cargar();
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al encolar email",
        description: getErrorMessage(err),
      });
    } finally {
      clearPending();
    }
  };

  const aprobar = async (oc) => {
    setPendingLabel("Aprobando OC...");
    try {
      await postJson(`/ordenes-compra/${oc.id}/aprobar`);
      pushToast({ tone: "success", title: "OC aprobada", description: oc.codigo });
      cerrarDrawer();
      await cargar();
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al aprobar",
        description: getErrorMessage(err),
      });
    } finally {
      clearPending();
    }
  };

  const rechazar = async (oc) => {
    if (!motivo.trim()) return;
    setPendingLabel("Rechazando OC...");
    try {
      await postJson(`/ordenes-compra/${oc.id}/rechazar`, { motivo: motivo.trim() });
      pushToast({ tone: "info", title: "OC rechazada", description: oc.codigo });
      cerrarDrawer();
      await cargar();
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al rechazar",
        description: getErrorMessage(err),
      });
    } finally {
      clearPending();
    }
  };

  const marcarComprada = async (oc) => {
    setPendingLabel("Marcando como comprada...");
    try {
      await postJson(`/ordenes-compra/${oc.id}/comprar`);
      pushToast({ tone: "success", title: "OC marcada como comprada", description: oc.codigo });
      cerrarDrawer();
      await cargar();
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al marcar comprada",
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
            Compras externas
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Ordenes de Compra
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Solicitudes a proveedores externos. Cada OC requiere aprobacion
            del supervisor via email (link con token firmado, 7 dias).
          </p>
        </div>
        {esAdminOSupervisor ? (
          <button
            type="button"
            onClick={abrirCrear}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
          >
            Nueva OC
          </button>
        ) : null}
      </header>

      <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-5">
        <div>
          <label htmlFor="estado" className="text-xs font-semibold uppercase text-slate-500">
            Estado
          </label>
          <select
            id="estado"
            value={estadoFiltro}
            onChange={(e) => setEstadoFiltro(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            {ESTADOS.map((e) => (
              <option key={e.value} value={e.value}>
                {e.label}
              </option>
            ))}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="prov" className="text-xs font-semibold uppercase text-slate-500">
            Proveedor (ILIKE)
          </label>
          <input
            id="prov"
            type="text"
            value={proveedorFiltro}
            onChange={(e) => setProveedorFiltro(e.target.value)}
            placeholder="Buscar por nombre..."
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label htmlFor="desde" className="text-xs font-semibold uppercase text-slate-500">
            Desde
          </label>
          <input
            id="desde"
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label htmlFor="hasta" className="text-xs font-semibold uppercase text-slate-500">
            Hasta
          </label>
          <input
            id="hasta"
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
          />
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-6 text-sm text-slate-500">Cargando ordenes...</p>
        ) : error ? (
          <p className="p-6 text-sm text-rose-600">Error: {error}</p>
        ) : ordenes.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-base font-semibold text-slate-700">
              Sin ordenes de compra
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Cree la primera OC con el boton "Nueva OC" arriba.
            </p>
          </div>
        ) : (
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
        )}
      </div>

      <Drawer
        open={drawerMode === "create"}
        onClose={cerrarDrawer}
        title="Nueva Orden de Compra"
      >
        <NuevaOCForm
          bodegas={bodegas}
          supervisores={supervisores}
          productos={productos}
          onCreate={onCrear}
          onCancel={cerrarDrawer}
          submitting={submitting}
          error={formError}
        />
      </Drawer>

      <Drawer
        open={drawerMode === "detail"}
        onClose={cerrarDrawer}
        title={detalle ? `Detalle OC ${detalle.codigo}` : "Detalle"}
      >
        {detalleLoading || !detalle ? (
          <p className="text-sm text-slate-500">Cargando detalle...</p>
        ) : (
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
                    onClick={() => rechazar(detalle)}
                    disabled={!motivo.trim()}
                    className="rounded-md bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Confirmar rechazo
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </Drawer>
    </div>
  );
}
