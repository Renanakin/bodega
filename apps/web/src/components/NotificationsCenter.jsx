// NotificationsCenter: campanita + drawer con la lista de notificaciones
// in-app del usuario (Fase 8).
//
// Endpoints consumidos:
//   GET  /api/v1/notificaciones?limit=50       — lista paginada
//   GET  /api/v1/notificaciones/no-leidas/count — badge counter
//   POST /api/v1/notificaciones/{id}/marcar-leida
//   POST /api/v1/notificaciones/marcar-todas-leidas
//
// Tipos manejados (campo `tipo`):
//   - solicitud.created, solicitud.approved, solicitud.dispatched,
//     solicitud.received, solicitud.rejected
//   - orden_compra.enviada, orden_compra.aprobada, orden_compra.rechazada
//   - stock.bajo_minimo
//
// Disenada 100% con Tailwind v3 (ADR-0006). Accesible:
//   - role="dialog" + aria-modal en el drawer
//   - aria-live="polite" en el badge
//   - keyboard: Escape cierra, Enter abre el detalle (link)
import { useCallback, useEffect, useRef, useState } from "react";

import { getErrorMessage, getJson, postJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

const POLLING_MS = 30_000;

const TIPO_ICONO = {
  "solicitud.created": "📝",
  "solicitud.approved": "✅",
  "solicitud.dispatched": "🚚",
  "solicitud.received": "📦",
  "solicitud.rejected": "❌",
  "orden_compra.enviada": "✉️",
  "orden_compra.aprobada": "👍",
  "orden_compra.rechazada": "👎",
  "stock.bajo_minimo": "⚠️",
};

const TIPO_TINT = {
  "solicitud.created": "bg-sky-50 text-sky-800",
  "solicitud.approved": "bg-emerald-50 text-emerald-800",
  "solicitud.dispatched": "bg-indigo-50 text-indigo-800",
  "solicitud.received": "bg-emerald-50 text-emerald-800",
  "solicitud.rejected": "bg-rose-50 text-rose-800",
  "orden_compra.enviada": "bg-amber-50 text-amber-800",
  "orden_compra.aprobada": "bg-emerald-50 text-emerald-800",
  "orden_compra.rechazada": "bg-rose-50 text-rose-800",
  "stock.bajo_minimo": "bg-amber-50 text-amber-800",
};

function formatFecha(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const ahora = new Date();
    const diff = (ahora - d) / 1000; // segundos
    if (diff < 60) return "hace instantes";
    if (diff < 3600) return `hace ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `hace ${Math.floor(diff / 3600)} h`;
    return d.toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export function NotificationsCenter() {
  const { user } = useAuth();
  const { pushToast } = useUi();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [noLeidas, setNoLeidas] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const containerRef = useRef(null);
  const buttonRef = useRef(null);

  const cargar = useCallback(async () => {
    if (!user) return;
    try {
      const [lista, count] = await Promise.all([
        getJson("/notificaciones?limit=50"),
        getJson("/notificaciones/no-leidas/count"),
      ]);
      setItems(Array.isArray(lista) ? lista : []);
      setNoLeidas(Number(count?.no_leidas || 0));
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar las notificaciones."));
    }
  }, [user]);

  // Carga inicial + polling cada 30s.
  useEffect(() => {
    cargar();
    const id = setInterval(cargar, POLLING_MS);
    return () => clearInterval(id);
  }, [cargar]);

  // Escape cierra el drawer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Click fuera cierra.
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target) &&
        buttonRef.current !== e.target
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const marcarLeida = async (n) => {
    if (n.leida) return;
    // Optimistic update
    setItems((prev) =>
      prev.map((it) => (it.id === n.id ? { ...it, leida: true } : it)),
    );
    setNoLeidas((prev) => Math.max(0, prev - 1));
    try {
      await postJson(`/notificaciones/${n.id}/marcar-leida`);
    } catch (err) {
      // Rollback si falla
      setItems((prev) =>
        prev.map((it) => (it.id === n.id ? { ...it, leida: false } : it)),
      );
      setNoLeidas((prev) => prev + 1);
      pushToast({
        tone: "danger",
        title: "No se pudo marcar como leida",
        description: getErrorMessage(err),
      });
    }
  };

  const marcarTodasLeidas = async () => {
    setLoading(true);
    try {
      await postJson("/notificaciones/marcar-todas-leidas");
      setItems((prev) => prev.map((it) => ({ ...it, leida: true })));
      setNoLeidas(0);
      pushToast({
        tone: "info",
        title: "Notificaciones marcadas como leidas",
      });
    } catch (err) {
      pushToast({
        tone: "danger",
        title: "Error al marcar todas",
        description: getErrorMessage(err),
      });
    } finally {
      setLoading(false);
    }
  };

  if (!user) return null; // No mostrar si no hay sesion.

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="relative flex h-9 w-9 items-center justify-center rounded-full border border-slate-300 bg-white text-slate-700 shadow-sm transition hover:bg-slate-50"
        aria-label={`Notificaciones${noLeidas > 0 ? ` (${noLeidas} no leidas)` : ""}`}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <span aria-hidden="true" className="text-base">🔔</span>
        {noLeidas > 0 ? (
          <span
            className="absolute -right-1 -top-1 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-rose-600 px-1 text-xs font-semibold text-white"
            aria-live="polite"
          >
            {noLeidas > 99 ? "99+" : noLeidas}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          ref={containerRef}
          role="dialog"
          aria-modal="false"
          aria-label="Centro de notificaciones"
          className="absolute right-0 z-40 mt-2 w-96 max-w-[90vw] rounded-lg border border-slate-200 bg-white shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Notificaciones</h2>
            <div className="flex items-center gap-2">
              {noLeidas > 0 ? (
                <button
                  type="button"
                  onClick={marcarTodasLeidas}
                  disabled={loading}
                  className="text-xs font-medium text-indigo-700 hover:underline disabled:opacity-50"
                >
                  Marcar todas leidas
                </button>
              ) : null}
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded p-1 text-slate-500 hover:bg-slate-100"
                aria-label="Cerrar"
              >
                <span aria-hidden="true">x</span>
              </button>
            </div>
          </div>

          <div className="max-h-[60vh] overflow-y-auto">
            {error ? (
              <p className="p-4 text-sm text-rose-600">Error: {error}</p>
            ) : items.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-sm font-semibold text-slate-700">
                  Sin notificaciones
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Te avisaremos aqui cuando haya eventos relevantes para ti.
                </p>
              </div>
            ) : (
              <ul role="list" className="divide-y divide-slate-100">
                {items.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => marcarLeida(n)}
                      className={`block w-full px-4 py-3 text-left transition hover:bg-slate-50 ${
                        n.leida ? "opacity-70" : "bg-indigo-50/40"
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <span
                          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-base ${
                            TIPO_TINT[n.tipo] || "bg-slate-100 text-slate-600"
                          }`}
                          aria-hidden="true"
                        >
                          {TIPO_ICONO[n.tipo] || "🔔"}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p
                            className={`truncate text-sm ${
                              n.leida ? "text-slate-600" : "font-semibold text-slate-900"
                            }`}
                          >
                            {n.titulo}
                          </p>
                          {n.mensaje ? (
                            <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">
                              {n.mensaje}
                            </p>
                          ) : null}
                          <p className="mt-1 text-xs text-slate-400">
                            {formatFecha(n.created_at)}
                          </p>
                        </div>
                        {!n.leida ? (
                          <span
                            className="mt-1 h-2 w-2 shrink-0 rounded-full bg-indigo-500"
                            aria-label="No leida"
                          />
                        ) : null}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
