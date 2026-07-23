import { useEffect, useState } from "react";

import { useSearchParams } from "react-router-dom";

import { DrawerPanel } from "../components/DrawerPanel";
import { EmptyState } from "../components/EmptyState";
import { FilterBar } from "../components/FilterBar";
import { PageHeader } from "../components/PageHeader";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { TableSimple } from "../components/TableSimple";
import { InventoryAdjustmentForm } from "../forms/InventoryAdjustmentForm";
import { useReviewMvpData } from "../hooks/useReviewMvpData";

const columns = [
  { key: "product_sku", label: "SKU" },
  { key: "product_name", label: "Producto" },
  { key: "warehouse_name", label: "Bodega" },
  { key: "quantity", label: "Stock actual" },
  { key: "min_quantity", label: "Minimo" },
  {
    key: "status",
    label: "Estado",
    render: (value) => (
      <StatusBadge tone={value === "Bajo minimo" ? "warning" : "success"}>{value}</StatusBadge>
    ),
  },
];

const movementColumns = [
  { key: "product_sku", label: "SKU" },
  { key: "warehouse_code", label: "Bodega" },
  { key: "movement_type", label: "Tipo" },
  { key: "quantity", label: "Cantidad" },
  { key: "reference_id", label: "Referencia" },
  { key: "notes", label: "Detalle" },
];

export function InventoryPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [warehouseFilter, setWarehouseFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("Todos");
  const { stock, movements, warehouses, products, loading, error, refresh } =
    useReviewMvpData();
  const [searchParams, setSearchParams] = useSearchParams();

  // Si llega con ?new=movement, abre el drawer automaticamente.
  // Esto es lo que dispara el boton "Nuevo movimiento" del topbar.
  useEffect(() => {
    if (searchParams.get("new") === "movement") {
      setDrawerOpen(true);
      const next = new URLSearchParams(searchParams);
      next.delete("new");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const normalizedQuery = query.trim().toLowerCase();
  const stockRows = stock
    .map((item) => ({
      ...item,
      status:
        Number(item.min_quantity) > 0 && Number(item.quantity) <= Number(item.min_quantity)
          ? "Bajo minimo"
          : "Disponible",
    }))
    .filter((item) => {
      const matchesQuery =
        !normalizedQuery ||
        item.product_sku.toLowerCase().includes(normalizedQuery) ||
        item.product_name.toLowerCase().includes(normalizedQuery);
      const matchesWarehouse = !warehouseFilter || item.warehouse_id === warehouseFilter;
      const matchesStatus = statusFilter === "Todos" || item.status === statusFilter;
      return matchesQuery && matchesWarehouse && matchesStatus;
    });

  return (
    <div className="page-stack">
      <PageHeader
        kicker="Inventario"
        title="Stock por bodega y disponibilidad operativa"
        description="Controla existencias, ajustes y disponibilidad para picking y despacho."
        actions={
          <>
            <button className="ghost-button">Importar conteo</button>
            <button className="primary-button" onClick={() => setDrawerOpen(true)}>
              Nuevo ajuste
            </button>
          </>
        }
      />

      <FilterBar>
        <input
          placeholder="Filtrar por SKU o producto"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select value={warehouseFilter} onChange={(event) => setWarehouseFilter(event.target.value)}>
          <option value="">Todas</option>
          {warehouses.map((warehouse) => (
            <option key={warehouse.id} value={warehouse.id}>
              {warehouse.name}
            </option>
          ))}
        </select>
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option>Todos</option>
          <option>Bajo minimo</option>
          <option>Disponible</option>
        </select>
      </FilterBar>

      <SectionCard
        title="Resumen de stock"
        subtitle="Visibilidad consolidada para recepcion, picking y despacho"
      >
        {error ? (
          <EmptyState title="No se pudo cargar el inventario" description={error} />
        ) : loading ? (
          <p className="muted-copy">Cargando stock...</p>
        ) : stockRows.length ? (
          <TableSimple columns={columns} rows={stockRows} />
        ) : (
          <EmptyState
            title="Sin inventario visible"
            description="Carga datos demo o registra movimientos para ver stock consolidado."
          />
        )}
      </SectionCard>

      <SectionCard
        title="Ultimos movimientos"
        subtitle="Trazabilidad de entradas, salidas y ajustes"
      >
        {movements.length ? (
          <TableSimple columns={movementColumns} rows={movements.slice(0, 8)} />
        ) : (
          <EmptyState
            title="Sin movimientos registrados"
            description="Los movimientos apareceran aqui apenas exista actividad en la API."
          />
        )}
      </SectionCard>

      <DrawerPanel
        title="Registrar ajuste"
        description="Deja trazabilidad del conteo, merma o correccion operativa."
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <InventoryAdjustmentForm
          warehouses={warehouses}
          products={products}
          onCreated={refresh}
          onSuccess={() => setDrawerOpen(false)}
        />
      </DrawerPanel>
    </div>
  );
}
