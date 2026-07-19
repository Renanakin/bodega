// RecepcionDetallePage: escaneo por linea de una solicitud en transito (Fase 5).
//
// - Ruta: /recepciones/:id
// - Header: codigo, bodegas, estado, prioridad.
// - Tabla de lineas: SKU + nombre + solicitada/despachada + input de
//   escaneo con BarcodeInput + cantidad recibida editable + selector
//   de incidencia.
// - Banner instructivo sobre el flujo del escaneo con pistola.
// - Boton "Confirmar recepcion" -> POST /solicitudes/{id}/receive.
// - 100% Tailwind v3 (ADR-0006).

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { BarcodeInput } from "../components/BarcodeInput";
import { getErrorMessage, getJson, postJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

const INCIDENCIAS = [
  { value: "", label: "Sin incidencia" },
  { value: "faltante", label: "Faltante (no llego)" },
  { value: "dano", label: "Dano fisico" },
  { value: "documental", label: "Problema documental" },
];

const ETIQUETA_ESTADO = {
  in_transit: "En transito",
  partially_received: "Recepcion parcial",
  received: "Recibida",
  approved: "Aprobada",
  pending: "Pendiente",
};

const COLOR_ESTADO = {
  in_transit: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  partially_received: "bg-amber-100 text-amber-800 ring-1 ring-amber-300",
  received: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
  approved: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  pending: "bg-slate-100 text-slate-700 ring-1 ring-slate-300",
};

function formatNum(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 });
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

// Determina el estado visual de una linea: pendiente / parcial / completo.
function estadoLinea(linea) {
  if (linea.cantidad_recibida >= linea.cantidad_despachada) return "completo";
  if (linea.cantidad_recibida > 0) return "parcial";
  return "pendiente";
}

const COLOR_LINEA = {
  pendiente: "bg-slate-50 text-slate-500",
  parcial: "bg-amber-50 text-amber-800",
  completo: "bg-emerald-50 text-emerald-800",
};

const ETIQUETA_LINEA = {
  pendiente: "Pendiente",
  parcial: "Parcial",
  completo: "Recibido",
};

export function RecepcionDetallePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();

  const [solicitud, setSolicitud] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [confirming, setConfirming] = useState(false);

  // Estado de escaneo por linea: { [producto_id]: { cantidad, barcode, incidencia, notas } }
  const [estadoLineas, setEstadoLineas] = useState({});

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJson(`/solicitudes/${id}`);
      setSolicitud(data);
      // Inicializar estado de escaneo: cantidad = pendiente por default.
      const inicial = {};
      for (const l of data.lineas || []) {
        const pendiente = Math.max(
          0,
          Number(l.cantidad_despachada) - Number(l.cantidad_recibida),
        );
        inicial[l.producto_id] = {
          cantidad: pendiente,
          barcode: "",
          incidencia: "",
          notas: "",
        };
      }
      setEstadoLineas(inicial);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar la solicitud."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const handleScan = useCallback((productoId) => (barcode) => {
    setEstadoLineas((prev) => ({
      ...prev,
      [productoId]: {
        ...(prev[productoId] || {
          cantidad: 0,
          barcode: "",
          incidencia: "",
          notas: "",
        }),
        barcode,
      },
    }));
  }, []);

  const updateLinea = useCallback((productoId, field, value) => {
    setEstadoLineas((prev) => ({
      ...prev,
      [productoId]: {
        ...(prev[productoId] || {
          cantidad: 0,
          barcode: "",
          incidencia: "",
          notas: "",
        }),
        [field]: value,
      },
    }));
  }, []);

  const lineasPayload = useMemo(() => {
    if (!solicitud) return [];
    const out = [];
    for (const l of solicitud.lineas || []) {
      const st = estadoLineas[l.producto_id];
      if (!st) continue;
      // Solo enviamos lineas con cantidad > 0 o barcode presente.
      const cantidad = Number(st.cantidad) || 0;
      const barcode = (st.barcode || "").trim();
      if (cantidad === 0 && !barcode) continue;
      out.push({
        producto_id: l.producto_id,
        cantidad_recibida: cantidad,
        barcode: barcode || null,
        incidencia: st.incidencia || st.notas || null,
      });
    }
    return out;
  }, [solicitud, estadoLineas]);

  const totalARecibir = useMemo(
    () => lineasPayload.reduce((acc, l) => acc + Number(l.cantidad_recibida || 0), 0),
    [lineasPayload],
  );

  const puedeConfirmar = useMemo(() => {
    if (!solicitud) return false;
    if (solicitud.estado !== "in_transit" && solicitud.estado !== "partially_received") {
      return false;
    }
    return lineasPayload.length > 0;
  }, [solicitud, lineasPayload]);

  const handleConfirmar = useCallback(async () => {
    if (!solicitud) return;
    if (lineasPayload.length === 0) {
      pushToast({
        tone: "warning",
        title: "Nada para confirmar",
        description: "Escaneá al menos un producto antes de confirmar.",
      });
      return;
    }
    const resumen = lineasPayload
      .map(
        (l) =>
          `${l.cantidad_recibida} x ${l.producto_id.slice(0, 8)}${l.barcode ? ` (${l.barcode})` : ""}`,
      )
      .join(", ");
    const ok = window.confirm(
      `Vas a confirmar la recepcion de:\n${resumen}\n\n¿Continuar?`,
    );
    if (!ok) return;

    setConfirming(true);
    setPendingLabel("Confirmando recepcion...");
    try {
      await postJson(`/solicitudes/${solicitud.id}/receive`, {
        lineas: lineasPayload,
      });
      pushToast({
        tone: "success",
        title: "Recepcion confirmada",
        description: `${lineasPayload.length} linea(s) procesada(s).`,
      });
      navigate("/recepciones/en-transito");
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al confirmar",
        description: getErrorMessage(err, "Recepcion rechazada por el servidor."),
      });
    } finally {
      setConfirming(false);
      clearPending();
    }
  }, [solicitud, lineasPayload, pushToast, setPendingLabel, clearPending, navigate]);

  if (loading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
        Cargando solicitud {id?.slice(0, 8)}...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 shadow-sm">
        <p className="font-semibold">No se pudo cargar la solicitud</p>
        <p className="mt-1">{error}</p>
        <button
          type="button"
          onClick={() => navigate("/recepciones/en-transito")}
          className="mt-3 rounded-md border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50"
        >
          Volver a la bandeja
        </button>
      </div>
    );
  }

  if (!solicitud) return null;

  return (
    <div className="space-y-4">
      {/* Header */}
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Recepcion
          </p>
          <h1 className="mt-1 flex items-center gap-2 font-mono text-2xl font-bold text-slate-900">
            {solicitud.codigo}
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                COLOR_ESTADO[solicitud.estado] || "bg-slate-100 text-slate-700"
              }`}
            >
              {ETIQUETA_ESTADO[solicitud.estado] || solicitud.estado}
            </span>
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            {solicitud.bodega_origen_codigo} &rarr; {solicitud.bodega_destino_codigo}
            {" - "}
            {solicitud.total_productos} productos /{" "}
            {formatNum(solicitud.total_unidades)} unidades
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate("/recepciones/en-transito")}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          &larr; Bandeja
        </button>
      </header>

      {/* Banner instructivo */}
      <div
        role="status"
        className="rounded-md border border-indigo-200 bg-indigo-50 p-3 text-sm text-indigo-800"
      >
        <p className="font-semibold">Como escanear</p>
        <p className="mt-1 text-xs">
          Apuntá la pistola al codigo de barras de cada producto. Cada
          escaneo se asocia a la linea correspondiente. Al terminar,
          ajustá las cantidades si hay faltantes y presioná{" "}
          <span className="font-semibold">Confirmar recepcion</span>.
        </p>
      </div>

      {/* Tabla de lineas */}
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                <th className="px-3 py-2">SKU / Producto</th>
                <th className="px-3 py-2 text-right">Solicitado</th>
                <th className="px-3 py-2 text-right">Despachado</th>
                <th className="px-3 py-2 text-right">Recibido</th>
                <th className="px-3 py-2">Escaneo</th>
                <th className="px-3 py-2">Incidencia</th>
                <th className="px-3 py-2 text-right">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(solicitud.lineas || []).map((l) => {
                const st = estadoLineas[l.producto_id] || {
                  cantidad: 0,
                  barcode: "",
                  incidencia: "",
                  notas: "",
                };
                const estadoL = estadoLinea(l);
                const editable =
                  solicitud.estado === "in_transit" ||
                  solicitud.estado === "partially_received";
                return (
                  <tr key={l.producto_id} data-testid={`linea-${l.producto_id}`}>
                    <td className="px-3 py-2">
                      <div className="font-mono text-xs font-semibold text-slate-800">
                        {l.producto_sku}
                      </div>
                      <div className="text-xs text-slate-500">{l.producto_nombre}</div>
                    </td>
                    <td className="px-3 py-2 text-right text-slate-700">
                      {formatNum(l.cantidad_solicitada)}
                    </td>
                    <td className="px-3 py-2 text-right text-slate-700">
                      {formatNum(l.cantidad_despachada)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <input
                        type="number"
                        min="0"
                        max={Number(l.cantidad_despachada)}
                        step="1"
                        value={st.cantidad}
                        onChange={(e) =>
                          updateLinea(l.producto_id, "cantidad", e.target.value)
                        }
                        disabled={!editable}
                        aria-label={`Cantidad recibida para ${l.producto_sku}`}
                        className="w-20 rounded-md border border-slate-300 bg-white px-2 py-1 text-right text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                      />
                    </td>
                    <td className="px-3 py-2">
                      {editable ? (
                        <div>
                          <BarcodeInput
                            onScan={handleScan(l.producto_id)}
                            autoFocus={false}
                            placeholder="Escanear..."
                            ariaLabel={`Escaner para ${l.producto_sku}`}
                            className="text-xs"
                          />
                          {st.barcode && (
                            <div
                              data-testid={`barcode-leido-${l.producto_id}`}
                              className="mt-1 truncate font-mono text-[10px] text-slate-500"
                              title={st.barcode}
                            >
                              {st.barcode}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400">N/A</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <select
                        value={st.incidencia}
                        onChange={(e) =>
                          updateLinea(l.producto_id, "incidencia", e.target.value)
                        }
                        disabled={!editable}
                        aria-label={`Incidencia para ${l.producto_sku}`}
                        className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
                      >
                        {INCIDENCIAS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                          COLOR_LINEA[estadoL] || COLOR_LINEA.pendiente
                        }`}
                      >
                        {ETIQUETA_LINEA[estadoL] || estadoL}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer de confirmacion */}
      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="text-xs text-slate-500">
          Vas a registrar{" "}
          <span className="font-semibold text-slate-800">
            {lineasPayload.length} linea(s)
          </span>{" "}
          con un total de{" "}
          <span className="font-mono font-semibold text-slate-800">
            {formatNum(totalARecibir)}
          </span>{" "}
          unidades. La solicitud quedara en estado{" "}
          <span className="font-mono">
            {totalARecibir > 0 ? "partially_received o received" : "sin cambios"}
          </span>
          .
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => cargar()}
            disabled={confirming}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Recargar
          </button>
          <button
            type="button"
            onClick={handleConfirmar}
            disabled={!puedeConfirmar || confirming}
            data-testid="boton-confirmar-recepcion"
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {confirming ? "Confirmando..." : "Confirmar recepcion"}
          </button>
        </div>
      </div>
    </div>
  );
}
