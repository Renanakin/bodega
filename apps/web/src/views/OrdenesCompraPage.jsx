// OrdenesCompraPage: gestion de Ordenes de Compra externas (Fase 6).
//
// Ruta: /ordenes-compra
//
// Pagina de composicion. Toda la logica vive en:
// - useOrdenesCompra (hook con estado + handlers).
// - components/ordenes-compra/* (filtros, tabla, drawers, timeline, form).
import { useAuth } from "../context/AuthContext";
import { Drawer } from "../components/ordenes-compra/Drawer";
import { NuevaOCForm } from "../components/ordenes-compra/NuevaOCForm";
import { OrdenesFilters } from "../components/ordenes-compra/OrdenesFilters";
import { OrdenesTable } from "../components/ordenes-compra/OrdenesTable";
import { OrdenDetailDrawer } from "../components/ordenes-compra/OrdenDetailDrawer";
import { useOrdenesCompra } from "../components/ordenes-compra/useOrdenesCompra";

export function OrdenesCompraPage() {
  const { user } = useAuth();
  const {
    ordenes, loading, error,
    estadoFiltro, setEstadoFiltro,
    proveedorFiltro, setProveedorFiltro,
    fechaDesde, setFechaDesde,
    fechaHasta, setFechaHasta,
    drawerMode, detalle, detalleLoading,
    bodegas, supervisores, productos,
    formError, submitting,
    esAdminOSupervisor,
    abrirDetalle, abrirCrear, cerrarDrawer,
    onCrear, enviarCorreo, aprobar, rechazar, marcarComprada,
  } = useOrdenesCompra(user);

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

      <OrdenesFilters
        estadoFiltro={estadoFiltro}
        setEstadoFiltro={setEstadoFiltro}
        proveedorFiltro={proveedorFiltro}
        setProveedorFiltro={setProveedorFiltro}
        fechaDesde={fechaDesde}
        setFechaDesde={setFechaDesde}
        fechaHasta={fechaHasta}
        setFechaHasta={setFechaHasta}
      />

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <OrdenesTable
          loading={loading}
          error={error}
          ordenes={ordenes}
          esAdminOSupervisor={esAdminOSupervisor}
          abrirDetalle={abrirDetalle}
          enviarCorreo={enviarCorreo}
        />
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
        <OrdenDetailDrawer
          detalle={detalle}
          loading={detalleLoading}
          esAdminOSupervisor={esAdminOSupervisor}
          enviarCorreo={enviarCorreo}
          aprobar={aprobar}
          rechazar={rechazar}
          marcarComprada={marcarComprada}
        />
      </Drawer>
    </div>
  );
}
