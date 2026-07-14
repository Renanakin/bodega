import { Link } from "react-router-dom";

import { ActivityFeed } from "../components/ActivityFeed";
import { KpiStrip } from "../components/KpiStrip";
import { SectionCard } from "../components/SectionCard";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { TableSimple } from "../components/TableSimple";
import { EmptyState } from "../components/EmptyState";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";
import { getErrorMessage } from "../lib/api";
import { useReviewMvpData } from "../hooks/useReviewMvpData";

const lowStockColumns = [
  { key: "product_sku", label: "SKU" },
  { key: "product_name", label: "Producto" },
  { key: "warehouse_name", label: "Bodega" },
  { key: "quantity", label: "Disponible" },
  { key: "min_quantity", label: "Minimo" },
  {
    key: "status",
    label: "Estado",
    render: (value) => (
      <StatusBadge tone={value === "Critico" ? "danger" : "warning"}>
        {value}
      </StatusBadge>
    ),
  },
];

const transferColumns = [
  { key: "product_sku", label: "SKU" },
  { key: "warehouse_code", label: "Bodega" },
  {
    key: "movement_type",
    label: "Tipo",
    render: (value) => (
      <StatusBadge tone={value.includes("out") ? "warning" : "success"}>
        {value}
      </StatusBadge>
    ),
  },
  { key: "quantity", label: "Cantidad" },
  { key: "reference_id", label: "Referencia" },
];

export function DashboardPage() {
  const { user } = useAuth();
  const {
    pushToast,
    setPendingLabel,
    clearPending,
    presentationMode,
    presentationStepIndex,
    togglePresentationMode,
  } = useUi();
  const { summary, stock, movements, transfers, loading, error, seedDemoData } =
    useReviewMvpData();

  const requestedTransfers = transfers.filter((item) => item.status === "requested").length;
  const dispatchedTransfers = transfers.filter((item) => item.status === "dispatched").length;
  const receivedTransfers = transfers.filter((item) => item.status === "received").length;
  const lowStockRows = stock
    .filter((item) => Number(item.min_quantity) > 0 && Number(item.quantity) <= Number(item.min_quantity))
    .map((item) => ({ ...item, status: "Critico" }));
  const transferFillRate = transfers.length
    ? Math.round((receivedTransfers / transfers.length) * 100)
    : 0;
  const demoCoverage = summary?.warehouses && summary?.products && summary?.movements ? "Lista" : "Pendiente";

  const stats = [
    {
      title: "Alertas criticas",
      value: String(lowStockRows.length),
      helper: lowStockRows.length
        ? "Productos que ya exigen reposicion o traslado"
        : "Sin quiebres en el escenario cargado",
      tone: lowStockRows.length ? "danger" : "success",
    },
    {
      title: "Solicitudes pendientes",
      value: String(requestedTransfers),
      helper: "Transferencias que requieren aprobacion para no frenar operacion",
      tone: requestedTransfers ? "warning" : "success",
    },
    {
      title: "Transferencias recibidas",
      value: String(receivedTransfers),
      helper: "Cierres completos que ya actualizaron stock destino",
      tone: "success",
    },
    {
      title: "Cobertura demo",
      value: demoCoverage,
      helper: "Bodegas, productos, stock y auditoria visibles desde el primer minuto",
      tone: "default",
    },
  ];

  const recentMovements = movements.slice(0, 6);
  const activityItems = [
    ...transfers.slice(0, 3).map((item) => ({
      id: item.id,
      title: `${item.code} en estado ${item.status}`,
      detail: `${item.product_sku} desde ${item.from_warehouse_name} hacia ${item.to_warehouse_name}.`,
      time: new Date(item.created_at).toLocaleString("es-CL"),
      tone:
        item.status === "requested"
          ? "warning"
          : item.status === "received"
            ? "success"
            : "default",
    })),
    ...movements.slice(0, 2).map((item) => ({
      id: item.id,
      title: `Movimiento ${item.movement_type} de ${item.product_sku}`,
      detail: item.notes || item.reference_id || "Sin detalle adicional.",
      time: new Date(item.created_at).toLocaleString("es-CL"),
      tone: item.movement_type.includes("out") ? "warning" : "success",
    })),
  ].slice(0, 5);
  const kpiItems = [
    { label: "Bodegas visibles", value: String(summary?.warehouses ?? 0) },
    { label: "Productos activos", value: String(summary?.products ?? 0) },
    { label: "OTIF demo", value: `${transferFillRate}%` },
    { label: "Despachos en transito", value: String(dispatchedTransfers) },
  ];
  const tourSteps = [
    {
      title: "1. Revisa quiebres y backlog",
      copy: "El cliente entiende rapido si hay stock critico y cuellos de botella.",
      to: "/dashboard",
      action: "Leer resumen",
    },
    {
      title: "2. Inspecciona inventario consolidado",
      copy: "Muestra visibilidad por bodega, SKU y trazabilidad historica.",
      to: "/inventory",
      action: "Abrir inventario",
    },
    {
      title: "3. Avanza una transferencia",
      copy: "Demuestra control por etapas con permisos y auditoria.",
      to: "/transfers",
      action: "Ir a transferencias",
    },
    {
      title: "4. Cierra con auditoria",
      copy: "Refuerza confianza mostrando quien hizo cada accion.",
      to: "/settings",
      action: "Ver auditoria",
    },
  ];

  const handleSeed = async () => {
    setPendingLabel("Cargando datos demo del MVP...");
    try {
      await seedDemoData();
      pushToast({
        tone: "success",
        title: "Demo cargada",
        description: "El MVP ya tiene bodegas, productos y movimientos para revision.",
      });
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo cargar la demo",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <div className="page-grid">
      <section className="hero-panel">
        <div>
          <p className="page-kicker">Centro de control</p>
          <h2>La demo muestra control, trazabilidad y respuesta operativa</h2>
          <p>
            {user?.full_name} esta viendo una historia completa: quiebre,
            aprobacion, despacho, recepcion y auditoria final sin salir de la plataforma.
          </p>
        </div>
        <div className="hero-actions">
          <button className="primary-button" type="button" onClick={handleSeed}>
            Cargar demo
          </button>
          <button className="ghost-button" type="button" onClick={togglePresentationMode}>
            {presentationMode ? "Salir presentacion" : "Activar presentacion"}
          </button>
          <button className="ghost-button" type="button">
            API en /api/v1
          </button>
        </div>
      </section>

      <div className="stats-grid">
        {stats.map((stat) => (
          <StatCard key={stat.title} {...stat} />
        ))}
      </div>

      <KpiStrip items={kpiItems} />

      <section className="demo-story-grid">
        <SectionCard
          title="Mensaje comercial"
          subtitle="Lo que el cliente deberia notar en menos de 2 minutos"
        >
          <div className="story-points">
            <div className="story-point">
              <strong>Visibilidad inmediata</strong>
              <p>Inventario, transferencias y alertas aparecen sin preparar datos a mano.</p>
            </div>
            <div className="story-point">
              <strong>Control por rol</strong>
              <p>Origen, supervisor y destino no ven el mismo poder de accion.</p>
            </div>
            <div className="story-point">
              <strong>Trazabilidad real</strong>
              <p>Cada paso deja movimiento, cambio de estado y evento auditado.</p>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="Recorrido sugerido"
          subtitle="Guia corta para presentar valor sin improvisar"
        >
          <div className="tour-list">
            {tourSteps.map((step, index) => (
              <article key={step.title} className="tour-item">
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.copy}</p>
                </div>
                <Link
                  className={presentationMode && presentationStepIndex === index ? "primary-button" : "ghost-button"}
                  to={step.to}
                >
                  {step.action}
                </Link>
              </article>
            ))}
          </div>
        </SectionCard>
      </section>

      <div className="two-columns">
        <SectionCard
          title="Stock bajo minimo"
          subtitle="Riesgos visibles para compras, reposicion o traslado inmediato"
        >
          {error ? (
            <EmptyState title="No se pudo leer el stock" description={error} />
          ) : loading ? (
            <p className="muted-copy">Cargando resumen...</p>
          ) : lowStockRows.length ? (
            <TableSimple columns={lowStockColumns} rows={lowStockRows} />
          ) : (
            <EmptyState
              title="Sin alertas criticas"
              description="El MVP esta operativo. Puedes cargar demo o registrar ajustes para probar."
            />
          )}
        </SectionCard>

        <SectionCard
          title="Actividad reciente"
          subtitle="Eventos listos para contar la historia de la demo"
        >
          {activityItems.length ? (
            <ActivityFeed items={activityItems} />
          ) : recentMovements.length ? (
            <TableSimple columns={transferColumns} rows={recentMovements} />
          ) : (
            <EmptyState
              title="Aun no hay movimientos"
              description="Usa la carga demo o registra un ajuste para ver trazabilidad operativa."
            />
          )}
        </SectionCard>
      </div>
    </div>
  );
}
