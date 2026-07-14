import { useState } from "react";

import { DrawerPanel } from "../components/DrawerPanel";
import { PageHeader } from "../components/PageHeader";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { ReplenishmentRuleForm } from "../forms/ReplenishmentRuleForm";

const alerts = [
  {
    title: "Sucursal Norte requiere 8 filtros adicionales",
    note: "Regla: reorden automatico por bajo stock",
    tone: "danger",
  },
  {
    title: "Central puede abastecer 2 solicitudes hoy",
    note: "Stock disponible antes de generar compra",
    tone: "success",
  },
  {
    title: "5 productos sin proveedor preferente",
    note: "Bloquea automatizacion completa de OC",
    tone: "warning",
  },
];

export function ReplenishmentPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="page-stack">
      <PageHeader
        kicker="Reposicion"
        title="Alertas, reglas y abastecimiento automatico"
        description="Define umbrales y decide si el sistema transfiere o compra."
        actions={
          <button className="primary-button" onClick={() => setDrawerOpen(true)}>
            Nueva regla
          </button>
        }
      />

      <div className="insight-grid">
        {alerts.map((alert) => (
          <SectionCard
            key={alert.title}
            title={alert.title}
            subtitle={alert.note}
            actions={<StatusBadge tone={alert.tone}>Activo</StatusBadge>}
          >
            <p className="muted-copy">
              Este bloque es la base para solicitudes automaticas, ordenes de
              compra y derivacion a transferencias internas.
            </p>
          </SectionCard>
        ))}
      </div>

      <DrawerPanel
        title="Nueva regla de reposicion"
        description="Configura stock minimo, objetivo y modo de abastecimiento."
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <ReplenishmentRuleForm onSuccess={() => setDrawerOpen(false)} />
      </DrawerPanel>
    </div>
  );
}
