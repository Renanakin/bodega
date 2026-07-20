// ReportsPage: reportes operativos, ejecutivo y auditoria.
//
// Ruta: /reports
//
// Pagina de composicion con 3 tabs:
//   - Operacional: historial de movimientos + exports CSV.
//   - Ejecutivo: snapshot con KPIs + export PDF.
//   - Auditoria: ultimos 200 eventos + export CSV.
//
// Toda la logica vive en components/reports/*.
import { useEffect, useState } from "react";
import { getErrorMessage, getJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { TABS } from "../components/reports/helpers";
import { TabButton } from "../components/reports/TabButton";
import { TabOperacional } from "../components/reports/TabOperacional";
import { TabEjecutivo } from "../components/reports/TabEjecutivo";
import { TabAuditoria } from "../components/reports/TabAuditoria";

export function ReportsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("operacional");
  const [stock, setStock] = useState([]);
  const [transfers, setTransfers] = useState([]);
  const [movements, setMovements] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelado = false;
    async function cargar() {
      setLoading(true);
      setError(null);
      try {
        const [s, t, m, w] = await Promise.all([
          getJson("/inventory/stock"),
          getJson("/transfers"),
          getJson("/inventory/movements?limit=200"),
          getJson("/warehouses"),
        ]);
        if (!cancelado) {
          setStock(Array.isArray(s) ? s : []);
          setTransfers(Array.isArray(t) ? t : []);
          setMovements(Array.isArray(m) ? m : []);
          setWarehouses(Array.isArray(w) ? w : []);
        }
      } catch (err) {
        if (!cancelado) {
          setError(getErrorMessage(err, "No se pudo cargar los datos operativos."));
        }
      } finally {
        if (!cancelado) setLoading(false);
      }
    }
    cargar();
    return () => {
      cancelado = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          Reportes
        </p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">Reportes</h1>
        <p className="mt-1 text-sm text-slate-600">
          Exportes operativos (CSV), snapshot ejecutivo (PDF) y auditoria
          reciente. Sesion activa: {user?.full_name} ({user?.role}).
        </p>
      </header>

      <div className="border-b border-slate-200" role="tablist" aria-label="Tabs de reportes">
        <nav className="flex space-x-2">
          {TABS.map((t) => (
            <TabButton key={t.id} active={tab === t.id} onClick={() => setTab(t.id)}>
              {t.label}
            </TabButton>
          ))}
        </nav>
      </div>

      <div role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "operacional" ? (
          <TabOperacional
            stock={stock}
            transfers={transfers}
            movements={movements}
            warehouses={warehouses}
            error={error}
            loading={loading}
          />
        ) : tab === "ejecutivo" ? (
          <TabEjecutivo />
        ) : (
          <TabAuditoria />
        )}
      </div>
    </div>
  );
}
