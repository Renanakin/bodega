// SlottingPage: ubicaciones inteligentes para reducir tiempos de picking.
//
// Ruta: /slotting
//
// Estado: PROXIMAMENTE. Los endpoints backend de optimizacion de
// ubicaciones (slotting engine) estan planificados para una fase futura.
// Mientras tanto, mostramos un placeholder honesto para que la
// navegacion no muestre errores 404.
export function SlottingPage() {
  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Slotting
        </p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">
          Ubicaciones inteligentes
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Optimizacion de ubicaciones en bodega por rotacion y criticidad
          para reducir tiempos de picking.
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
              d="M3 7h18M3 12h18M3 17h18"
            />
          </svg>
          <h2 className="mt-4 text-base font-semibold text-slate-900">
            Proximamente
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            El motor de optimizacion de ubicaciones (slotting) esta planificado
            para una fase futura. Por ahora esta vista muestra la ubicacion
            manual en el modulo de Stock.
          </p>
          <a
            href="/inventario/real"
            className="mt-4 inline-flex items-center rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
          >
            Ir a Stock Real
          </a>
        </div>
      </div>
    </div>
  );
}
