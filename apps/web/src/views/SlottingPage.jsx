import { SectionCard } from "../components/SectionCard";
import { TableSimple } from "../components/TableSimple";
import { lowRotation, slottingRows } from "../data/mock";

const suggestionColumns = [
  { key: "product", label: "Producto" },
  { key: "currentSlot", label: "Ubicacion actual" },
  { key: "suggestedSlot", label: "Ubicacion sugerida" },
  { key: "reason", label: "Motivo" },
];

const rotationColumns = [
  { key: "product", label: "Producto" },
  { key: "lastSale", label: "Ultima venta" },
  { key: "action", label: "Accion sugerida" },
];

export function SlottingPage() {
  return (
    <div className="page-stack">
      <section className="page-header">
        <div>
          <p className="page-kicker">Slotting</p>
          <h2>Ubicaciones inteligentes para reducir tiempos de picking</h2>
        </div>
        <button className="primary-button">Generar sugerencias</button>
      </section>

      <div className="two-columns">
        <SectionCard
          title="Sugerencias de reubicacion"
          subtitle="Optimizadas por rotacion y criticidad"
        >
          <TableSimple columns={suggestionColumns} rows={slottingRows} />
        </SectionCard>

        <SectionCard
          title="Productos de baja rotacion"
          subtitle="Base para reordenar layout de la bodega"
        >
          <TableSimple columns={rotationColumns} rows={lowRotation} />
        </SectionCard>
      </div>
    </div>
  );
}

