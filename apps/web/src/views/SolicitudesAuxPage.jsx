// SolicitudesAuxPage: gestion de solicitudes de recarga (Fase 3 + Fase 4).
//
// Ruta: /solicitudes
//
// Pagina de composicion. Toda la logica de estado vive en
// useSolicitudesAux (hook). Filtros, tabla y drawer de detalle
// estan en components/solicitudes-aux/*.
import { useAuth } from "../context/AuthContext";
import { SolicitudesFilters } from "../components/solicitudes-aux/SolicitudesFilters";
import { SolicitudesTable } from "../components/solicitudes-aux/SolicitudesTable";
import { SolicitudDetailDrawer } from "../components/solicitudes-aux/SolicitudDetailDrawer";
import { useSolicitudesAux } from "../components/solicitudes-aux/useSolicitudesAux";

export function SolicitudesAuxPage() {
  const { user } = useAuth();
  const {
    loading, error, total, itemsPagina,
    estadoFiltro, setEstadoFiltro,
    bodegaFiltro, setBodegaFiltro,
    fechaDesde, setFechaDesde,
    fechaHasta, setFechaHasta,
    bodegasUnicas,
    detalle, detalleLoading,
    skip, puedeAprobar,
    cargar, abrirDetalle, cerrarDetalle,
    aprobar, rechazar, limpiarFiltros, setSkip,
  } = useSolicitudesAux(user);

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Operaciones
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Solicitudes de recarga
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Workflow completo: pendiente → aprobada → en transito → recibida.
            Click en una fila para ver el detalle y aprobar o rechazar.
          </p>
        </div>
        <button
          type="button"
          disabled
          title="Disponible en Fase 5/6"
          className="rounded-md bg-slate-200 px-3 py-2 text-sm font-semibold text-slate-500 shadow-sm cursor-not-allowed"
        >
          + Nueva solicitud manual
        </button>
      </header>

      <SolicitudesFilters
        estadoFiltro={estadoFiltro}
        setEstadoFiltro={setEstadoFiltro}
        bodegaFiltro={bodegaFiltro}
        setBodegaFiltro={setBodegaFiltro}
        fechaDesde={fechaDesde}
        setFechaDesde={setFechaDesde}
        fechaHasta={fechaHasta}
        setFechaHasta={setFechaHasta}
        bodegasUnicas={bodegasUnicas}
        cargar={cargar}
        limpiarFiltros={limpiarFiltros}
      />

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <SolicitudesTable
          loading={loading}
          error={error}
          total={total}
          itemsPagina={itemsPagina}
          abrirDetalle={abrirDetalle}
          setSkip={setSkip}
          skip={skip}
        />
      </div>

      {(detalle || detalleLoading) && (
        <SolicitudDetailDrawer
          detalle={detalle}
          loading={detalleLoading}
          puedeAprobar={puedeAprobar}
          cerrarDetalle={cerrarDetalle}
          aprobar={aprobar}
          rechazar={rechazar}
        />
      )}
    </div>
  );
}
