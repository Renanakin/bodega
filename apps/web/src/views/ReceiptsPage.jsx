import { useState } from "react";

import { DrawerPanel } from "../components/DrawerPanel";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { TableSimple } from "../components/TableSimple";
import { ReceiptForm } from "../forms/ReceiptForm";
import { useReviewMvpData } from "../hooks/useReviewMvpData";

const columns = [
  { key: "reference_id", label: "Referencia" },
  { key: "warehouse_code", label: "Bodega" },
  { key: "product_sku", label: "SKU" },
  { key: "quantity", label: "Cantidad" },
  {
    key: "movement_type",
    label: "Tipo",
    render: () => <StatusBadge tone="success">Recepcionada</StatusBadge>,
  },
  { key: "notes", label: "Detalle" },
];

export function ReceiptsPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { movements, warehouses, products, loading, error, refresh } = useReviewMvpData();

  const receiptRows = movements.filter(
    (item) => item.movement_type === "in" && item.reference_type === "receipt",
  );

  return (
    <div className="page-stack">
      <PageHeader
        kicker="Recepciones"
        title="Carga de stock inicial y recepciones operativas"
        description="Registra ingresos para dejar disponibilidad real antes de mover stock entre bodegas."
        actions={
          <button className="primary-button" onClick={() => setDrawerOpen(true)}>
            Nueva carga
          </button>
        }
      />

      <SectionCard
        title="Recepciones registradas"
        subtitle="Ingresos que impactan el stock disponible del sistema"
      >
        {error ? (
          <EmptyState title="No se pudieron cargar las recepciones" description={error} />
        ) : loading ? (
          <p className="muted-copy">Cargando recepciones...</p>
        ) : receiptRows.length ? (
          <TableSimple columns={columns} rows={receiptRows} />
        ) : (
          <EmptyState
            title="Sin recepciones registradas"
            description="Crea una carga para habilitar existencias y continuar el flujo."
          />
        )}
      </SectionCard>

      <DrawerPanel
        title="Nueva carga"
        description="Selecciona bodega, producto, cantidad y referencia documental."
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <ReceiptForm
          warehouses={warehouses}
          products={products}
          onSuccess={async () => {
            await refresh();
            setDrawerOpen(false);
          }}
        />
      </DrawerPanel>
    </div>
  );
}
