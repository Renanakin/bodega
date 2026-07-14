import { useState } from "react";

import { DrawerPanel } from "../components/DrawerPanel";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { TableSimple } from "../components/TableSimple";
import { useAuth } from "../context/AuthContext";
import { ProductForm } from "../forms/ProductForm";
import { useReviewMvpData } from "../hooks/useReviewMvpData";

const columns = [
  { key: "sku", label: "SKU" },
  { key: "name", label: "Producto" },
  { key: "unit", label: "Unidad" },
  {
    key: "is_active",
    label: "Estado",
    render: (value) => (
      <StatusBadge tone={value ? "success" : "neutral"}>
        {value ? "Activo" : "Inactivo"}
      </StatusBadge>
    ),
  },
];

export function ProductsPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { user } = useAuth();
  const { products, loading, error, refresh } = useReviewMvpData();

  return (
    <div className="page-stack">
      <PageHeader
        kicker="Catalogo"
        title="Productos operativos del MVP"
        description="Alta y consulta del catalogo base para movimientos, stock y trazabilidad."
        actions={
          <button
            className="primary-button"
            disabled={!["admin", "supervisor"].includes(user?.role)}
            onClick={() => setDrawerOpen(true)}
          >
            Nuevo producto
          </button>
        }
      />

      <SectionCard
        title="Catalogo activo"
        subtitle="Productos listos para movimientos de inventario"
      >
        {error ? (
          <EmptyState title="No se pudo cargar el catalogo" description={error} />
        ) : loading ? (
          <p className="muted-copy">Cargando productos...</p>
        ) : products.length ? (
          <TableSimple columns={columns} rows={products} />
        ) : (
          <EmptyState
            title="No hay productos creados"
            description="Crea el primer producto o carga datos demo desde el dashboard."
          />
        )}
      </SectionCard>

      <DrawerPanel
        title="Nuevo producto"
        description="Ingresa un SKU, nombre y unidad para dejarlo operativo de inmediato."
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <ProductForm
          onSuccess={async () => {
            await refresh();
            setDrawerOpen(false);
          }}
        />
      </DrawerPanel>
    </div>
  );
}
