/**
 * MultibodegaGrid: muestra la distribucion de un producto en todas las bodegas
 * (Fase 2 / spec §4.1).
 *
 * Formato exacto del spec:
 *   Bodega Principal: 140 unidades (Ubicación: P-01/E-02/A-01)
 *   Bodega Aux 1:     12 unidades  (Ubicación: A-04/E-01/A-01)
 *   Bodega Aux 2:     3 unidades   (Estado: ALERTA - Bajo Mínimo)
 *   Bodega Aux 3:     15 unidades
 *
 * Cuando una bodega tiene multiples ubicaciones, se muestra la primera
 * (la de mayor cantidad) como representativa, y un sublistado con el resto
 * al hacer hover / focus.
 *
 * Props:
 * - distribucion: DistribucionMultibodegaResponse del backend.
 *   Si es null, se muestra el empty state.
 * - onSelectBodega(bodega): callback opcional al hacer click en una fila.
 * - loading: muestra skeleton.
 * - error: muestra mensaje de error.
 */
function formatQty(qty) {
  return new Intl.NumberFormat("es-CL", { maximumFractionDigits: 2 }).format(qty);
}

function pickRepresentanteUbicacion(ubicaciones) {
  if (!ubicaciones || ubicaciones.length === 0) return null;
  // Ubicacion con mayor cantidad
  return [...ubicaciones].sort((a, b) => Number(b.cantidad) - Number(a.cantidad))[0];
}

function getBadge(estado) {
  if (estado === "critico") {
    return { label: "CRITICO - Sin stock", className: "bg-bodega-danger-soft text-bodega-danger" };
  }
  if (estado === "alerta") {
    return { label: "ALERTA - Bajo Mínimo", className: "bg-bodega-warning-soft text-bodega-warning" };
  }
  return { label: "OK", className: "bg-bodega-success-soft text-bodega-success" };
}

export function MultibodegaGrid({ distribucion, onSelectBodega, loading = false, error = null }) {
  if (error) {
    return (
      <div className="rounded-md border border-bodega-danger-soft bg-bodega-danger-soft/30 p-4 text-sm text-bodega-danger">
        <strong className="font-semibold">Error:</strong> {error}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-md border border-gray-200 bg-white p-4">
        <div className="animate-pulse space-y-2">
          <div className="h-4 w-1/3 rounded bg-gray-200"></div>
          <div className="h-4 w-1/2 rounded bg-gray-200"></div>
          <div className="h-4 w-2/5 rounded bg-gray-200"></div>
        </div>
      </div>
    );
  }

  if (!distribucion) {
    return (
      <div className="rounded-md border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-bodega-muted">
        Selecciona un producto para ver su distribución multibodega.
      </div>
    );
  }

  if (!distribucion.bodegas || distribucion.bodegas.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-bodega-muted">
        El producto <span className="font-mono font-semibold">{distribucion.sku}</span>{" "}
        no tiene stock registrado en ninguna bodega.
      </div>
    );
  }

  return (
    <section
      role="region"
      aria-label={`Distribución multibodega de ${distribucion.sku}`}
      className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-bodega-ink">
            <span className="font-mono">{distribucion.sku}</span>
          </h2>
          <p className="text-sm text-bodega-muted">{distribucion.name}</p>
        </div>
        <div className="text-sm">
          <span className="text-bodega-muted">Total global: </span>
          <strong className="font-mono text-bodega-ink">
            {formatQty(distribucion.total_global)}
          </strong>
        </div>
      </header>

      <ul className="divide-y divide-gray-100 font-mono text-sm">
        {distribucion.bodegas.map((bodega) => {
          const rep = pickRepresentanteUbicacion(bodega.ubicaciones);
          const badge = getBadge(bodega.estado);
          const isLowStock = bodega.estado === "alerta" || bodega.estado === "critico";
          return (
            <li
              key={bodega.bodega_id}
              onClick={onSelectBodega ? () => onSelectBodega(bodega) : undefined}
              onKeyDown={
                onSelectBodega
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectBodega(bodega);
                      }
                    }
                  : undefined
              }
              tabIndex={onSelectBodega ? 0 : -1}
              role={onSelectBodega ? "button" : undefined}
              aria-label={`${bodega.bodega_code}: ${formatQty(bodega.total_quantity)} unidades`}
              className={
                onSelectBodega
                  ? "flex cursor-pointer items-center gap-3 px-2 py-2 hover:bg-bodega-accent/5 focus:bg-bodega-accent/10 focus:outline-none"
                  : "flex items-center gap-3 px-2 py-2"
              }
            >
              <span
                className="min-w-[14ch] truncate text-bodega-ink"
                title={bodega.bodega_name}
              >
                {bodega.bodega_code}
              </span>
              <span className="min-w-[12ch] text-right font-semibold text-bodega-ink">
                {formatQty(bodega.total_quantity)} unid.
              </span>
              <span className="flex-1 truncate text-bodega-muted">
                {rep
                  ? `(Ubicación: ${rep.code})`
                  : bodega.estado === "critico"
                  ? "(Sin stock)"
                  : ""}
              </span>
              {isLowStock && (
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${badge.className}`}
                  aria-label={badge.label}
                >
                  {bodega.estado === "critico" ? "CRITICO" : "ALERTA"}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      {distribucion.bodegas.some((b) => b.ubicaciones.length > 1) && (
        <details className="mt-3 text-xs text-bodega-muted">
          <summary className="cursor-pointer hover:text-bodega-ink">
            Ver todas las ubicaciones por bodega
          </summary>
          <div className="mt-2 space-y-1">
            {distribucion.bodegas
              .filter((b) => b.ubicaciones.length > 0)
              .map((b) => (
                <div key={b.bodega_id} className="font-mono">
                  <strong>{b.bodega_code}:</strong>{" "}
                  {b.ubicaciones
                    .map(
                      (u) =>
                        `${u.code} (${formatQty(u.cantidad)})`,
                    )
                    .join(", ")}
                </div>
              ))}
          </div>
        </details>
      )}
    </section>
  );
}
