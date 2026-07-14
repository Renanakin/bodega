import { useMemo, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { FilterBar } from "../components/FilterBar";
import { SectionCard } from "../components/SectionCard";
import { TableSimple } from "../components/TableSimple";
import { useReviewMvpData } from "../hooks/useReviewMvpData";
import { downloadCsv } from "../lib/export";

const movementColumns = [
  { key: "product_sku", label: "SKU" },
  { key: "warehouse_code", label: "Bodega" },
  { key: "movement_type", label: "Tipo" },
  { key: "quantity", label: "Cantidad" },
  { key: "reference_id", label: "Referencia" },
  { key: "notes", label: "Detalle" },
];

export function ReportsPage() {
  const [skuFilter, setSkuFilter] = useState("");
  const [warehouseFilter, setWarehouseFilter] = useState("");
  const { stock, transfers, movements, warehouses, error, loading } = useReviewMvpData();

  const normalizedSku = skuFilter.trim().toLowerCase();
  const historyRows = useMemo(
    () =>
      movements.filter((item) => {
        const matchesSku = !normalizedSku || item.product_sku.toLowerCase().includes(normalizedSku);
        const matchesWarehouse = !warehouseFilter || item.warehouse_id === warehouseFilter;
        return matchesSku && matchesWarehouse;
      }),
    [movements, normalizedSku, warehouseFilter],
  );

  const topInventoryRows = useMemo(
    () =>
      [...stock]
        .sort((left, right) => Number(right.quantity) - Number(left.quantity))
        .slice(0, 5),
    [stock],
  );

  const openTransfers = transfers.filter((item) =>
    ["requested", "approved", "dispatched", "partially_received"].includes(item.status),
  );

  return (
    <div className="page-stack">
      <section className="page-header">
        <div>
          <p className="page-kicker">Reportes</p>
          <h2>Exportes operativos e historial consultable</h2>
          <p className="page-description">
            Descarga inventario y transferencias, o filtra la trazabilidad por bodega y SKU.
          </p>
        </div>
        <div className="inline-actions">
          <button
            className="ghost-button"
            type="button"
            onClick={() =>
              downloadCsv(
                "inventario.csv",
                [
                  { key: "warehouse_name", label: "Bodega" },
                  { key: "product_sku", label: "SKU" },
                  { key: "product_name", label: "Producto" },
                  { key: "quantity", label: "Stock" },
                  { key: "min_quantity", label: "Minimo" },
                ],
                stock,
              )
            }
          >
            Exportar inventario
          </button>
          <button
            className="ghost-button"
            type="button"
            onClick={() =>
              downloadCsv(
                "transferencias-abiertas.csv",
                [
                  { key: "code", label: "Codigo" },
                  { key: "from_warehouse_name", label: "Origen" },
                  { key: "to_warehouse_name", label: "Destino" },
                  { key: "product_sku", label: "SKU" },
                  { key: "quantity", label: "Solicitada" },
                  { key: "received_quantity", label: "Recibida" },
                  { key: "status", label: "Estado" },
                ],
                openTransfers,
              )
            }
          >
            Exportar transferencias
          </button>
        </div>
      </section>

      <div className="two-columns">
        <SectionCard title="Mayor stock visible" subtitle="Productos con mayor presencia en la demo">
          {error ? (
            <EmptyState title="No se pudo generar ranking" description={error} />
          ) : loading ? (
            <p className="muted-copy">Preparando ranking...</p>
          ) : topInventoryRows.length ? (
            <TableSimple
              columns={[
                { key: "product_sku", label: "SKU" },
                { key: "product_name", label: "Producto" },
                { key: "warehouse_name", label: "Bodega" },
                { key: "quantity", label: "Stock" },
              ]}
              rows={topInventoryRows}
            />
          ) : (
            <EmptyState title="Sin datos" description="Carga la demo para construir este ranking." />
          )}
        </SectionCard>

        <SectionCard title="Transferencias abiertas" subtitle="Backlog operativo listo para exportar">
          {openTransfers.length ? (
            <TableSimple
              columns={[
                { key: "code", label: "Codigo" },
                { key: "status", label: "Estado" },
                { key: "product_sku", label: "SKU" },
                { key: "quantity", label: "Solicitada" },
                { key: "received_quantity", label: "Recibida" },
              ]}
              rows={openTransfers}
            />
          ) : (
            <EmptyState
              title="Sin backlog operativo"
              description="Las transferencias pendientes o parciales apareceran aqui."
            />
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Historial por producto y bodega"
        subtitle="Filtra la trazabilidad para preguntas concretas del cliente"
      >
        <FilterBar>
          <input
            placeholder="Filtrar por SKU"
            value={skuFilter}
            onChange={(event) => setSkuFilter(event.target.value)}
          />
          <select value={warehouseFilter} onChange={(event) => setWarehouseFilter(event.target.value)}>
            <option value="">Todas las bodegas</option>
            {warehouses.map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.name}
              </option>
            ))}
          </select>
          <button
            className="ghost-button"
            type="button"
            onClick={() => downloadCsv("historial-filtrado.csv", movementColumns, historyRows)}
          >
            Exportar historial
          </button>
        </FilterBar>

        {historyRows.length ? (
          <TableSimple columns={movementColumns} rows={historyRows.slice(0, 20)} />
        ) : (
          <EmptyState
            title="Sin movimientos para el filtro"
            description="Prueba con otro SKU o bodega para revisar la trazabilidad."
          />
        )}
      </SectionCard>
    </div>
  );
}
