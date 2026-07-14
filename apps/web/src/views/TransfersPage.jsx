import { useState } from "react";

import { DrawerPanel } from "../components/DrawerPanel";
import { EmptyState } from "../components/EmptyState";
import { FilterBar } from "../components/FilterBar";
import { PageHeader } from "../components/PageHeader";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { TableSimple } from "../components/TableSimple";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";
import { TransferDispatchForm } from "../forms/TransferDispatchForm";
import { TransferEditForm } from "../forms/TransferEditForm";
import { TransferForm } from "../forms/TransferForm";
import { TransferReceiveForm } from "../forms/TransferReceiveForm";
import { useReviewMvpData } from "../hooks/useReviewMvpData";
import { getErrorMessage, postJson } from "../lib/api";
import { downloadCsv } from "../lib/export";

const statusTone = {
  requested: "warning",
  approved: "neutral",
  dispatched: "success",
  partially_received: "warning",
  received: "success",
  cancelled: "neutral",
};

const statusLabel = {
  requested: "Solicitada",
  approved: "Aprobada",
  dispatched: "Despachada",
  partially_received: "Recepcion parcial",
  received: "Recibida",
  cancelled: "Cancelada",
};

function buildColumns(runAction, openDrawer, userRole) {
  return [
    { key: "code", label: "Codigo" },
    { key: "from_warehouse_name", label: "Origen" },
    { key: "to_warehouse_name", label: "Destino" },
    { key: "product_sku", label: "SKU" },
    { key: "quantity", label: "Solicitada" },
    { key: "received_quantity", label: "Recibida" },
    {
      key: "status",
      label: "Estado",
      render: (value) => (
        <StatusBadge tone={statusTone[value] || "neutral"}>
          {statusLabel[value] || value}
        </StatusBadge>
      ),
    },
    { key: "priority", label: "Prioridad" },
    { key: "timeline", label: "Hitos" },
    {
      key: "actions",
      label: "Acciones",
      render: (_, row) => (
        <div className="table-actions">
          {row.status === "requested" ? (
            <>
              <button
                className="ghost-button"
                type="button"
                disabled={!["admin", "supervisor"].includes(userRole)}
                onClick={() => runAction(row, "approve")}
              >
                Aprobar
              </button>
              <button
                className="ghost-button"
                type="button"
                disabled={!["admin", "supervisor", "origin_operator"].includes(userRole)}
                onClick={() => openDrawer("edit", row)}
              >
                Editar
              </button>
              <button
                className="ghost-button"
                type="button"
                disabled={!["admin", "supervisor", "origin_operator"].includes(userRole)}
                onClick={() => runAction(row, "cancel")}
              >
                Cancelar
              </button>
            </>
          ) : null}
          {row.status === "approved" ? (
            <button
              className="ghost-button"
              type="button"
              disabled={!["admin", "supervisor", "origin_operator"].includes(userRole)}
              onClick={() => openDrawer("dispatch", row)}
            >
              Despachar
            </button>
          ) : null}
          {["dispatched", "partially_received"].includes(row.status) ? (
            <button
              className="primary-button"
              type="button"
              disabled={!["admin", "supervisor", "destination_operator"].includes(userRole)}
              onClick={() => openDrawer("receive", row)}
            >
              {row.status === "partially_received" ? "Completar recepcion" : "Recibir"}
            </button>
          ) : null}
          {row.status === "received" ? <span className="muted-copy">Flujo cerrado</span> : null}
          {row.status === "cancelled" ? <span className="muted-copy">Solicitud anulada</span> : null}
        </div>
      ),
    },
  ];
}

export function TransfersPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [actionDrawer, setActionDrawer] = useState({ type: "", transfer: null });
  const [warehouseFilter, setWarehouseFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("Todas las etapas");
  const [codeFilter, setCodeFilter] = useState("");
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { transfers, warehouses, products, loading, error, refresh } = useReviewMvpData();

  const openActionDrawer = (type, transfer) => setActionDrawer({ type, transfer });
  const closeActionDrawer = () => setActionDrawer({ type: "", transfer: null });

  const runAction = async (transfer, action) => {
    const actionMeta = {
      approve: {
        pending: `Aprobando ${transfer.code}...`,
        title: "Transferencia aprobada",
        description: `${transfer.code} ya puede pasar a despacho.`,
      },
      cancel: {
        pending: `Cancelando ${transfer.code}...`,
        title: "Transferencia cancelada",
        description: `${transfer.code} fue anulada antes de comprometer stock.`,
      },
    }[action];

    setPendingLabel(actionMeta.pending);
    try {
      await postJson(`/transfers/${transfer.id}/${action}`);
      pushToast({
        tone: "success",
        title: actionMeta.title,
        description: actionMeta.description,
      });
      await refresh();
    } catch (actionError) {
      pushToast({
        tone: "danger",
        title: `No se pudo ejecutar ${action}`,
        description: getErrorMessage(actionError),
      });
    } finally {
      clearPending();
    }
  };

  const normalizedCode = codeFilter.trim().toLowerCase();
  const transferRows = transfers
    .filter((item) => {
      const matchesWarehouse =
        !warehouseFilter ||
        item.from_warehouse_id === warehouseFilter ||
        item.to_warehouse_id === warehouseFilter;
      const matchesStatus =
        statusFilter === "Todas las etapas" ||
        item.status.toLowerCase() === statusFilter.toLowerCase();
      const matchesCode = !normalizedCode || item.code.toLowerCase().includes(normalizedCode);
      return matchesWarehouse && matchesStatus && matchesCode;
    })
    .map((item) => ({
      ...item,
      timeline: [
        item.created_at ? "Solicitada" : null,
        item.approved_at ? "Aprobada" : null,
        item.dispatched_at ? "Despachada" : null,
        item.status === "partially_received" ? "Recepcion parcial" : null,
        item.received_at ? "Recibida" : null,
        item.status === "cancelled" ? "Cancelada" : null,
      ]
        .filter(Boolean)
        .join(" -> "),
    }));

  const transferStats = {
    requested: transfers.filter((item) => item.status === "requested").length,
    approved: transfers.filter((item) => item.status === "approved").length,
    dispatched: transfers.filter((item) => item.status === "dispatched").length,
    partial: transfers.filter((item) => item.status === "partially_received").length,
    received: transfers.filter((item) => item.status === "received").length,
  };

  const exportColumns = [
    { key: "code", label: "Codigo" },
    { key: "from_warehouse_name", label: "Origen" },
    { key: "to_warehouse_name", label: "Destino" },
    { key: "product_sku", label: "SKU" },
    { key: "quantity", label: "Solicitada" },
    { key: "received_quantity", label: "Recibida" },
    { key: "status", label: "Estado", value: (row) => statusLabel[row.status] || row.status },
    { key: "incident_type", label: "Incidencia" },
    { key: "incident_notes", label: "Detalle incidencia" },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        kicker="Transferencias"
        title="Orquesta movimientos internos entre bodegas"
        description="Ahora soporta edicion previa, cancelacion, despacho documentado y recepcion parcial."
        actions={
          <div className="inline-actions">
            <button
              className="ghost-button"
              type="button"
              onClick={() => downloadCsv("transferencias.csv", exportColumns, transferRows)}
            >
              Exportar CSV
            </button>
            <button
              className="primary-button"
              onClick={() => setDrawerOpen(true)}
              disabled={!["admin", "supervisor", "origin_operator"].includes(user?.role)}
            >
              Nueva transferencia
            </button>
          </div>
        }
      />

      <div className="stats-grid">
        <SectionCard title="Solicitadas" subtitle={`${transferStats.requested} esperando aprobacion`}>
          <StatusBadge tone="warning">Paso 1</StatusBadge>
        </SectionCard>
        <SectionCard title="Aprobadas" subtitle={`${transferStats.approved} listas para despacho`}>
          <StatusBadge tone="neutral">Paso 2</StatusBadge>
        </SectionCard>
        <SectionCard title="Despachadas" subtitle={`${transferStats.dispatched} en transito`}>
          <StatusBadge tone="success">Paso 3</StatusBadge>
        </SectionCard>
        <SectionCard title="Recepcion parcial" subtitle={`${transferStats.partial} con incidencia o faltante`}>
          <StatusBadge tone="warning">Paso 4a</StatusBadge>
        </SectionCard>
        <SectionCard title="Recibidas" subtitle={`${transferStats.received} cerradas`}>
          <StatusBadge tone="success">Paso 4b</StatusBadge>
        </SectionCard>
      </div>

      <FilterBar>
        <select value={warehouseFilter} onChange={(event) => setWarehouseFilter(event.target.value)}>
          <option value="">Todas las bodegas</option>
          {warehouses.map((warehouse) => (
            <option key={warehouse.id} value={warehouse.id}>
              {warehouse.name}
            </option>
          ))}
        </select>
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          <option value="Todas las etapas">Todas las etapas</option>
          <option value="requested">Solicitada</option>
          <option value="approved">Aprobada</option>
          <option value="dispatched">Despachada</option>
          <option value="partially_received">Recepcion parcial</option>
          <option value="received">Recibida</option>
          <option value="cancelled">Cancelada</option>
        </select>
        <input
          placeholder="Buscar por codigo"
          value={codeFilter}
          onChange={(event) => setCodeFilter(event.target.value)}
        />
      </FilterBar>

      <SectionCard
        title="Transferencias por etapa"
        subtitle="Solicitud, despacho, recepcion parcial y cierre con detalle de incidentes"
      >
        {error ? (
          <EmptyState title="No se pudieron cargar las transferencias" description={error} />
        ) : loading ? (
          <p className="muted-copy">Cargando transferencias...</p>
        ) : transferRows.length ? (
          <TableSimple columns={buildColumns(runAction, openActionDrawer, user?.role)} rows={transferRows} />
        ) : (
          <EmptyState
            title="Sin transferencias registradas"
            description="Carga stock, crea una solicitud y luego avanza cada etapa desde esta vista."
          />
        )}
      </SectionCard>

      <SectionCard
        title="Incidencias recientes"
        subtitle="Observaciones que muestran manejo de excepciones reales"
      >
        {transferRows.filter((item) => item.incident_type || item.status === "partially_received").length ? (
          <TableSimple
            columns={[
              { key: "code", label: "Codigo" },
              {
                key: "status",
                label: "Estado",
                render: (value) => <StatusBadge tone={statusTone[value] || "neutral"}>{statusLabel[value] || value}</StatusBadge>,
              },
              { key: "incident_type", label: "Incidencia" },
              { key: "incident_notes", label: "Detalle" },
              { key: "receive_notes", label: "Recepcion" },
            ]}
            rows={transferRows.filter((item) => item.incident_type || item.status === "partially_received")}
          />
        ) : (
          <EmptyState
            title="Sin incidencias registradas"
            description="Las recepciones parciales o con observaciones quedaran visibles aqui."
          />
        )}
      </SectionCard>

      <DrawerPanel
        title="Nueva transferencia"
        description="Crea una solicitud formal con prioridad, producto y cantidad."
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <TransferForm
          warehouses={warehouses}
          products={products}
          onSuccess={async () => {
            await refresh();
            setDrawerOpen(false);
          }}
        />
      </DrawerPanel>

      <DrawerPanel
        title={
          actionDrawer.type === "edit"
            ? "Editar solicitud"
            : actionDrawer.type === "dispatch"
              ? "Registrar despacho"
              : "Registrar recepcion"
        }
        description={
          actionDrawer.transfer
            ? `Transferencia ${actionDrawer.transfer.code}`
            : "Completa la accion seleccionada."
        }
        isOpen={Boolean(actionDrawer.type)}
        onClose={closeActionDrawer}
      >
        {actionDrawer.type === "edit" && actionDrawer.transfer ? (
          <TransferEditForm
            transfer={actionDrawer.transfer}
            onSuccess={async () => {
              await refresh();
              closeActionDrawer();
            }}
          />
        ) : null}
        {actionDrawer.type === "dispatch" && actionDrawer.transfer ? (
          <TransferDispatchForm
            transfer={actionDrawer.transfer}
            onSuccess={async () => {
              await refresh();
              closeActionDrawer();
            }}
          />
        ) : null}
        {actionDrawer.type === "receive" && actionDrawer.transfer ? (
          <TransferReceiveForm
            transfer={actionDrawer.transfer}
            onSuccess={async () => {
              await refresh();
              closeActionDrawer();
            }}
          />
        ) : null}
      </DrawerPanel>
    </div>
  );
}
