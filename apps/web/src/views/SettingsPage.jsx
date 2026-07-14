import { useEffect, useState } from "react";

import { EmptyState } from "../components/EmptyState";
import { SectionCard } from "../components/SectionCard";
import { TableSimple } from "../components/TableSimple";
import { useAuth } from "../context/AuthContext";
import { getJson } from "../lib/api";

const columns = [
  { key: "action", label: "Accion" },
  { key: "entity_type", label: "Entidad" },
  { key: "entity_id", label: "ID" },
  { key: "detail", label: "Detalle" },
  { key: "created_at", label: "Fecha" },
];

export function SettingsPage() {
  const { user } = useAuth();
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getJson("/audit")
      .then(setLogs)
      .catch((auditError) => setError(auditError.message));
  }, []);

  return (
    <div className="page-stack">
      <section className="page-header">
        <div>
          <p className="page-kicker">Configuracion</p>
          <h2>Parametros de operacion y seguridad</h2>
          <p className="page-description">
            Perfil activo: {user?.full_name} ({user?.role})
          </p>
        </div>
      </section>

      <div className="two-columns">
        <SectionCard
          title="Seguridad"
          subtitle="Roles, permisos y politicas de acceso"
        >
          <ul className="plain-list">
            <li>Roles por bodega y por empresa</li>
            <li>Auditoria de ajustes y aprobaciones</li>
            <li>JWT y expiracion de sesion</li>
          </ul>
        </SectionCard>

        <SectionCard
          title="Parametros operativos"
          subtitle="Reglas de inventario y abastecimiento"
        >
          <ul className="plain-list">
            <li>Stock minimo y stock objetivo</li>
            <li>Puntos de reorden por producto</li>
            <li>Bodega abastecedora por defecto</li>
          </ul>
        </SectionCard>
      </div>

      <SectionCard
        title="Auditoria reciente"
        subtitle="Ultimas acciones relevantes registradas por la plataforma"
      >
        {error ? (
          <EmptyState title="No se pudo cargar la auditoria" description={error} />
        ) : logs.length ? (
          <TableSimple columns={columns} rows={logs} />
        ) : (
          <EmptyState
            title="Sin eventos auditados"
            description="Las acciones de login, inventario y transferencias apareceran aqui."
          />
        )}
      </SectionCard>
    </div>
  );
}
