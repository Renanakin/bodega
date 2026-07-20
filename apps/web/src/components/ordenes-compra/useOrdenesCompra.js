// Hook con toda la logica de estado + handlers de OrdenesCompraPage.
// Mantiene la pagina como composicion pura de UI; el estado vive aca.
import { useCallback, useEffect, useState } from "react";
import { getErrorMessage, getJson, postJson } from "../../lib/api";
import { useUi } from "../../context/UiContext";

export function useOrdenesCompra(user) {
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

  const rechazar = async (oc, motivo) => {
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

  return {
    // state
    ordenes, loading, error,
    estadoFiltro, setEstadoFiltro,
    proveedorFiltro, setProveedorFiltro,
    fechaDesde, setFechaDesde,
    fechaHasta, setFechaHasta,
    drawerMode, detalle, detalleLoading,
    bodegas, supervisores, productos,
    formError, submitting,
    esAdminOSupervisor,
    // handlers
    abrirDetalle, abrirCrear, cerrarDrawer,
    onCrear, enviarCorreo, aprobar, rechazar, marcarComprada,
  };
}
