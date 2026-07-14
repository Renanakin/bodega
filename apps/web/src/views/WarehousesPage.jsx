import { useState } from "react";

import { DrawerPanel } from "../components/DrawerPanel";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { TableSimple } from "../components/TableSimple";
import { useAuth } from "../context/AuthContext";
import { WarehouseForm } from "../forms/WarehouseForm";
import { useReviewMvpData } from "../hooks/useReviewMvpData";

const columns = [
  { key: "code", label: "Codigo" },
  { key: "name", label: "Bodega" },
  { key: "warehouse_type", label: "Tipo" },
  {
    key: "is_active",
    label: "Estado",
    render: (value) => (
      <StatusBadge tone={value ? "success" : "neutral"}>
        {value ? "Activa" : "Inactiva"}
      </StatusBadge>
    ),
  },
];

export function WarehousesPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { user } = useAuth();
  const { warehouses, loading, error, refresh } = useReviewMvpData();

  return (
    <div className="page-stack">
      <PageHeader
        kicker="Bodegas"
        title="Estructura operativa del flujo logístico"
        description="Crea las bodegas de origen y destino antes de cargar stock o transferir."
        actions={
          <button
            className="primary-button"
            disabled={user?.role !== "admin"}
            onClick={() => setDrawerOpen(true)}
          >
            Nueva bodega
          </button>
        }
      />

      <SectionCard
        title="Bodegas habilitadas"
        subtitle="Base del flujo desde recepcion hasta movimiento interno"
      >
        {error ? (
          <EmptyState title="No se pudieron cargar las bodegas" description={error} />
        ) : loading ? (
          <p className="muted-copy">Cargando bodegas...</p>
        ) : warehouses.length ? (
          <TableSimple columns={columns} rows={warehouses} />
        ) : (
          <EmptyState
            title="Aun no hay bodegas"
            description="Crea al menos una bodega central y una sucursal para iniciar el flujo."
          />
        )}
      </SectionCard>

      <DrawerPanel
        title="Nueva bodega"
        description="Define codigo, nombre y tipo para habilitarla operativamente."
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <WarehouseForm
          onSuccess={async () => {
            await refresh();
            setDrawerOpen(false);
          }}
        />
      </DrawerPanel>
    </div>
  );
}
