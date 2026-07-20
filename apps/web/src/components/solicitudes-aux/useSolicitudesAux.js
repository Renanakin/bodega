// Hook con toda la logica de estado + handlers de SolicitudesAuxPage.
// Mantiene la pagina como composicion pura de UI; el estado vive aca.
import { useCallback, useEffect, useMemo, useState } from "react";
import { getErrorMessage, getJson, postJson } from "../../lib/api";
import { useUi } from "../../context/UiContext";
import { PAGE_SIZE } from "./constants";
import { toIsoDate } from "./formatters";

export function useSolicitudesAux(user) {
  const { pushToast, setPendingLabel, clearPending } = useUi();

  const [solicitudes, setSolicitudes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filtros
  const [estadoFiltro, setEstadoFiltro] = useState("");
  const [bodegaFiltro, setBodegaFiltro] = useState("");
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");

  // Drawer
  const [detalle, setDetalle] = useState(null);
  const [detalleLoading, setDetalleLoading] = useState(false);

  // Paginacion
  const [skip, setSkip] = useState(0);
  const total = solicitudes.length;
  const itemsPagina = useMemo(
    () => solicitudes.slice(skip, skip + PAGE_SIZE),
    [solicitudes, skip],
  );

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (estadoFiltro) params.set("estado", estadoFiltro);
      if (bodegaFiltro) params.set("bodega_origen_id", bodegaFiltro);
      if (fechaDesde) params.set("fecha_desde", toIsoDate(fechaDesde));
      if (fechaHasta) params.set("fecha_hasta", toIsoDate(fechaHasta));
      params.set("limit", "200");
      const data = await getJson(`/solicitudes?${params.toString()}`);
      setSolicitudes(Array.isArray(data) ? data : []);
      setSkip(0);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar solicitudes."));
    } finally {
      setLoading(false);
    }
  }, [estadoFiltro, bodegaFiltro, fechaDesde, fechaHasta]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const bodegasUnicas = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const s of solicitudes) {
      if (seen.has(s.bodega_origen_id)) continue;
      seen.add(s.bodega_origen_id);
      out.push({
        id: s.bodega_origen_id,
        codigo: s.bodega_origen_codigo,
      });
    }
    return out.sort((a, b) => a.codigo.localeCompare(b.codigo));
  }, [solicitudes]);

  const abrirDetalle = useCallback(async (solicitudId) => {
    setDetalleLoading(true);
    try {
      const data = await getJson(`/solicitudes/${solicitudId}`);
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
  }, [pushToast]);

  const cerrarDetalle = useCallback(() => setDetalle(null), []);

  const aprobar = useCallback(
    async (id) => {
      setPendingLabel("Aprobando solicitud...");
      try {
        await postJson(`/solicitudes/${id}/approve`, {});
        pushToast({ tone: "success", title: "Solicitud aprobada" });
        await cargar();
        if (detalle?.id === id) await abrirDetalle(id);
      } catch (err) {
        pushToast({
          tone: "danger",
          title: "Error al aprobar",
          description: getErrorMessage(err),
        });
      } finally {
        clearPending();
      }
    },
    [setPendingLabel, clearPending, pushToast, cargar, detalle, abrirDetalle],
  );

  const rechazar = useCallback(
    async (id) => {
      const motivo = window.prompt(
        "Motivo de rechazo (minimo 5 caracteres):",
        "Rechazada por supervisor",
      );
      if (!motivo || motivo.length < 5) return;
      setPendingLabel("Rechazando solicitud...");
      try {
        await postJson(`/solicitudes/${id}/reject`, { motivo });
        pushToast({ tone: "info", title: "Solicitud rechazada" });
        await cargar();
        if (detalle?.id === id) await abrirDetalle(id);
      } catch (err) {
        pushToast({
          tone: "danger",
          title: "Error al rechazar",
          description: getErrorMessage(err),
        });
      } finally {
        clearPending();
      }
    },
    [setPendingLabel, clearPending, pushToast, cargar, detalle, abrirDetalle],
  );

  const limpiarFiltros = useCallback(() => {
    setEstadoFiltro("");
    setBodegaFiltro("");
    setFechaDesde("");
    setFechaHasta("");
  }, []);

  const puedeAprobar = user?.role === "admin" || user?.role === "supervisor";

  return {
    // state
    solicitudes, loading, error, total, itemsPagina,
    estadoFiltro, setEstadoFiltro,
    bodegaFiltro, setBodegaFiltro,
    fechaDesde, setFechaDesde,
    fechaHasta, setFechaHasta,
    bodegasUnicas,
    detalle, detalleLoading,
    skip, PAGE_SIZE,
    puedeAprobar,
    // handlers
    cargar, abrirDetalle, cerrarDetalle, aprobar, rechazar, limpiarFiltros,
    setSkip,
  };
}
