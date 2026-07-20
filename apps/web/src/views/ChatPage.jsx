// ChatPage: coordinacion operativa entre bodegas, compras y despacho.
//
// Ruta: /chat
//
// Estado: PROXIMAMENTE. El backend actual no tiene endpoints de chat
// (mensajeria entre usuarios/roles). La coordinacion operativa se hace
// hoy via el sistema de notificaciones in-app (/notificaciones) y por
// email (workflow de OC).
export function ChatPage() {
  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Chat
        </p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">
          Coordinacion operativa
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Chat entre bodegas, compras y despacho.
        </p>
      </header>

      <div className="rounded-lg border-2 border-dashed border-slate-300 bg-white p-12 text-center">
        <div className="mx-auto max-w-md">
          <svg
            className="mx-auto h-12 w-12 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
            />
          </svg>
          <h2 className="mt-4 text-base font-semibold text-slate-900">
            Proximamente
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            El chat operativo entre usuarios no esta implementado aun.
            Hoy la coordinacion se hace via el sistema de
            notificaciones in-app y por email (ordenes de compra).
          </p>
          <a
            href="/notificaciones"
            className="mt-4 inline-flex items-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
          >
            Ir a Notificaciones
          </a>
        </div>
      </div>
    </div>
  );
}
