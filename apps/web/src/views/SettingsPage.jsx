// SettingsPage: configuracion del sistema (Fase 8).
//
// Ruta: /settings
//
// Pagina de composicion con 3 tabs:
//   - Reglas de Reabastecimiento (stock_levels + min/max por bodega).
//   - Proveedores (CRUD).
//   - Parametros de Stock (edicion inline de min).
//
// Toda la logica vive en components/settings/*.
import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { TabButton } from "../components/settings/TabButton";
import { TabReglas } from "../components/settings/TabReglas";
import { TabProveedores } from "../components/settings/TabProveedores";
import { TabStock } from "../components/settings/TabStock";

const TABS = [
  { id: "reglas", label: "Reglas de Reabastecimiento" },
  { id: "proveedores", label: "Proveedores" },
  { id: "stock", label: "Parametros de Stock" },
];

export function SettingsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("reglas");

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Configuracion
        </p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">
          Parametros del sistema
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Sesion activa: {user?.full_name} ({user?.role}). Cambios en
          parametros afectan directamente al Evaluator y a la generacion
          automatica de solicitudes.
        </p>
      </header>

      <div className="border-b border-slate-200" role="tablist" aria-label="Tabs de configuracion">
        <nav className="flex flex-wrap space-x-2">
          {TABS.map((t) => (
            <TabButton key={t.id} active={tab === t.id} onClick={() => setTab(t.id)}>
              {t.label}
            </TabButton>
          ))}
        </nav>
      </div>

      <div role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "reglas" ? <TabReglas /> : tab === "proveedores" ? <TabProveedores /> : <TabStock />}
      </div>
    </div>
  );
}
