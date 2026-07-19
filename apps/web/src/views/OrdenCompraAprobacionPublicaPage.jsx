// OrdenCompraAprobacionPublicaPage: vista publica (sin auth) para aprobar
// o rechazar una Orden de Compra usando un token HMAC (ADR-0005).
//
// Ruta: /ordenes-compra/aprobar/:token
//
// Disenada 100% con Tailwind v3 (sin CSS plano legacy). El supervisor
// llega aqui desde el link del email; NO tiene cuenta en el sistema, asi
// que la pagina es self-contained y no usa AuthContext.
//
// Flujo:
// 1. Lee `token` de useParams.
// 2. Llama a GET /api/v1/public/ordenes-compra/aprobar/{token} (sin auth).
// 3. Muestra OC + tabla de lineas + total.
// 4. Boton Aprobar (POST .../aprobar/{token}) o Rechazar (POST .../rechazar/{token}).
// 5. Despues de aprobar/rechazar: oculta botones, muestra confirmacion.
// 6. Si token invalido/expirado: mensaje claro (401/410).
// 7. Si rate limited (429): mensaje con retry-after.
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError } from "../lib/api";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";

async function publicGet(path) {
  // El endpoint publico NO requiere auth; usar fetch crudo para no
  // adjuntar Authorization (la pagina es accessible sin sesion).
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return parseResponse(response);
}

async function publicPost(path, body) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return parseResponse(response);
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message =
      payload?.detail?.message ||
      payload?.detail?.code ||
      payload?.detail ||
      `Request failed: ${response.status}`;
    const error = new ApiError(message, response.status, payload);
    error.status = response.status;
    if (response.status === 429) {
      const retryAfter = payload?.detail?.extra?.retry_after;
      if (retryAfter) error.retryAfter = retryAfter;
    }
    throw error;
  }
  return payload;
}

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
      dateStyle: "long",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

const ESTADO_BADGE = {
  borrador: "bg-slate-100 text-slate-700 ring-1 ring-slate-300",
  enviado_a_supervisor: "bg-sky-100 text-sky-800 ring-1 ring-sky-300",
  aprobado: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
  rechazado: "bg-rose-100 text-rose-800 ring-1 ring-rose-300",
  comprado: "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-300",
};

function ErrorCard({ status, title, message, retryAfter }) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-6 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600">
          <span className="text-xl font-bold" aria-hidden="true">!</span>
        </div>
        <div className="flex-1">
          <h2 className="text-base font-semibold text-rose-900">
            {title}
          </h2>
          <p className="mt-1 text-sm text-rose-700">{message}</p>
          {retryAfter ? (
            <p className="mt-2 text-xs text-rose-600">
              Reintente en {retryAfter} segundo{retryAfter === 1 ? "" : "s"}.
            </p>
          ) : null}
          {status === 410 ? (
            <p className="mt-2 text-xs text-rose-600">
              El enlace ha expirado. Contacte al bodeguero central para
              que reenvie la solicitud.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function OrdenCompraAprobacionPublicaPage() {
  const { token } = useParams();
  const [orden, setOrden] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [showRejectDialog, setShowRejectDialog] = useState(false);
  const [motivo, setMotivo] = useState("");

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await publicGet(`/public/ordenes-compra/aprobar/${token}`);
      setOrden(data);
    } catch (err) {
      setError({
        status: err.status || 0,
        message: err.message || "Error desconocido",
        retryAfter: err.retryAfter,
      });
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const aprobar = useCallback(async () => {
    setSubmitting(true);
    try {
      const data = await publicPost(
        `/public/ordenes-compra/aprobar/${token}`,
      );
      setOrden(data);
    } catch (err) {
      setError({
        status: err.status || 0,
        message: err.message || "Error al aprobar",
        retryAfter: err.retryAfter,
      });
    } finally {
      setSubmitting(false);
    }
  }, [token]);

  const rechazar = useCallback(async () => {
    if (!motivo.trim()) return;
    setSubmitting(true);
    try {
      const data = await publicPost(
        `/public/ordenes-compra/rechazar/${token}`,
        { motivo: motivo.trim() },
      );
      setOrden(data);
      setShowRejectDialog(false);
    } catch (err) {
      setError({
        status: err.status || 0,
        message: err.message || "Error al rechazar",
        retryAfter: err.retryAfter,
      });
    } finally {
      setSubmitting(false);
    }
  }, [token, motivo]);

  const estado = orden?.estado;
  const esTerminal =
    estado === "aprobado" || estado === "rechazado" || estado === "comprado";

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-3xl px-4 py-4 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-indigo-600 text-white">
              <span className="text-lg font-bold" aria-hidden="true">B</span>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Bodegaje
              </p>
              <h1 className="text-lg font-bold text-slate-900">
                Aprobacion de Orden de Compra
              </h1>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
        {loading ? (
          <div className="rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
            <p className="text-sm text-slate-500">Cargando orden de compra...</p>
          </div>
        ) : error ? (
          <ErrorCard
            status={error.status}
            title={
              error.status === 401
                ? "Token invalido"
                : error.status === 410
                ? "Enlace expirado"
                : error.status === 404
                ? "Orden no encontrada"
                : error.status === 429
                ? "Demasiados intentos"
                : "Error al cargar"
            }
            message={error.message}
            retryAfter={error.retryAfter}
          />
        ) : !orden ? (
          <div className="rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
            <p className="text-sm text-slate-500">Sin datos.</p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Codigo
                  </p>
                  <p className="mt-1 font-mono text-lg font-bold text-slate-900">
                    {orden.codigo}
                  </p>
                  <p className="mt-2 text-sm text-slate-600">
                    <span className="font-medium">Proveedor:</span>{" "}
                    {orden.proveedor_nombre}
                    {orden.proveedor_contacto ? (
                      <span className="text-slate-500">
                        {" "}({orden.proveedor_contacto})
                      </span>
                    ) : null}
                  </p>
                  <p className="mt-1 text-sm text-slate-600">
                    <span className="font-medium">Creada:</span>{" "}
                    {formatFecha(orden.created_at)}
                  </p>
                  {orden.email_enviado_at ? (
                    <p className="mt-1 text-sm text-slate-600">
                      <span className="font-medium">Email enviado:</span>{" "}
                      {formatFecha(orden.email_enviado_at)}
                    </p>
                  ) : null}
                </div>
                <div>
                  <span
                    className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
                      ESTADO_BADGE[orden.estado] || ESTADO_BADGE.borrador
                    }`}
                  >
                    {orden.estado === "enviado_a_supervisor"
                      ? "Pendiente de aprobacion"
                      : orden.estado === "aprobado"
                      ? "Aprobada"
                      : orden.estado === "rechazado"
                      ? "Rechazada"
                      : orden.estado === "comprado"
                      ? "Comprada"
                      : "Borrador"}
                  </span>
                </div>
              </div>
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50">
                  <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                    <th scope="col" className="px-4 py-2">SKU</th>
                    <th scope="col" className="px-4 py-2">Producto</th>
                    <th scope="col" className="px-4 py-2 text-right">Cantidad</th>
                    <th scope="col" className="px-4 py-2 text-right">Costo unit.</th>
                    <th scope="col" className="px-4 py-2 text-right">Subtotal</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(orden.detalles || []).map((d, idx) => {
                    const subtotal =
                      Number(d.cantidad_pedida) * Number(d.costo_unitario_pactado);
                    return (
                      <tr key={`${d.id_producto}-${idx}`}>
                        <td className="px-4 py-2 font-mono text-xs text-slate-600">
                          {d.product_sku || d.id_producto.slice(0, 8)}
                        </td>
                        <td className="px-4 py-2 text-slate-800">
                          {d.product_name || "(producto)"}
                        </td>
                        <td className="px-4 py-2 text-right text-slate-700">
                          {Number(d.cantidad_pedida).toLocaleString("es-CL")}
                        </td>
                        <td className="px-4 py-2 text-right text-slate-700">
                          {formatCLP(d.costo_unitario_pactado)}
                        </td>
                        <td className="px-4 py-2 text-right font-semibold text-slate-900">
                          {formatCLP(subtotal)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="bg-slate-50">
                    <td colSpan={4} className="px-4 py-3 text-right text-sm font-semibold text-slate-700">
                      Total estimado
                    </td>
                    <td className="px-4 py-3 text-right text-base font-bold text-indigo-700">
                      {formatCLP(orden.total_estimado)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>

            {orden.notas ? (
              <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Notas
                </p>
                <p className="mt-1 text-sm text-slate-700">{orden.notas}</p>
              </div>
            ) : null}

            {esTerminal ? (
              <div
                className={`rounded-lg border p-5 shadow-sm ${
                  orden.estado === "aprobado"
                    ? "border-emerald-200 bg-emerald-50"
                    : orden.estado === "rechazado"
                    ? "border-rose-200 bg-rose-50"
                    : "border-slate-200 bg-slate-50"
                }`}
              >
                <h2
                  className={`text-base font-semibold ${
                    orden.estado === "aprobado"
                      ? "text-emerald-900"
                      : orden.estado === "rechazado"
                      ? "text-rose-900"
                      : "text-slate-900"
                  }`}
                >
                  {orden.estado === "aprobado"
                    ? "Aprobacion registrada"
                    : orden.estado === "rechazado"
                    ? "Rechazo registrado"
                    : "OC ya procesada"}
                </h2>
                <p
                  className={`mt-1 text-sm ${
                    orden.estado === "aprobado"
                      ? "text-emerald-700"
                      : orden.estado === "rechazado"
                      ? "text-rose-700"
                      : "text-slate-700"
                  }`}
                >
                  {orden.estado === "aprobado"
                    ? "Gracias por su confirmacion. El bodeguero central recibira la notificacion."
                    : orden.estado === "rechazado"
                    ? `El rechazo ha sido registrado${
                        orden.motivo_rechazo ? `: ${orden.motivo_rechazo}` : "."
                      }`
                    : "Esta orden ya no se puede modificar."}
                </p>
              </div>
            ) : (
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-slate-900">
                  Decida el curso de la compra
                </h2>
                <p className="mt-1 text-sm text-slate-600">
                  Al aprobar, el bodeguero central procedera a emitir la
                  orden al proveedor. Al rechazar, debera indicar el motivo.
                </p>
                {showRejectDialog ? (
                  <div className="mt-4 space-y-3">
                    <label
                      htmlFor="motivo"
                      className="block text-sm font-medium text-slate-700"
                    >
                      Motivo del rechazo
                    </label>
                    <textarea
                      id="motivo"
                      rows={3}
                      value={motivo}
                      onChange={(e) => setMotivo(e.target.value)}
                      placeholder="Ej: Monto excede presupuesto del mes"
                      className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={rechazar}
                        disabled={submitting || !motivo.trim()}
                        className="rounded-md bg-rose-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {submitting ? "Enviando..." : "Confirmar rechazo"}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setShowRejectDialog(false);
                          setMotivo("");
                        }}
                        disabled={submitting}
                        className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Cancelar
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={aprobar}
                      disabled={submitting}
                      className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {submitting ? "Procesando..." : "Aprobar orden"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowRejectDialog(true)}
                      disabled={submitting}
                      className="rounded-md bg-rose-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Rechazar
                    </button>
                  </div>
                )}
              </div>
            )}

            {error && error.status !== 401 && error.status !== 410 ? (
              <ErrorCard
                status={error.status}
                title="Error al procesar"
                message={error.message}
                retryAfter={error.retryAfter}
              />
            ) : null}
          </div>
        )}
      </main>

      <footer className="mx-auto max-w-3xl px-4 py-4 text-center text-xs text-slate-500 sm:px-6">
        Bodegaje &middot; Esta accion quedara registrada con su decision.
      </footer>
    </div>
  );
}
