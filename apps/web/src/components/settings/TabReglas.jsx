// Tab "Reglas de Reabastecimiento" de la pagina de Settings.
// CRUD de umbrales min/max por (producto x bodega).
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  getErrorMessage,
  getJson,
  putJson,
} from "../../lib/api";
import { useAuth } from "../../context/AuthContext";
import { useUi } from "../../context/UiContext";
import { ReplenishmentRuleForm } from "../ReplenishmentRuleForm";
import { Drawer } from "./Drawer";

export function TabReglas() {
  const { user } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const [stockLevels, setStockLevels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drawerMode, setDrawerMode] = useState(null);
  const [editingRule, setEditingRule] = useState(null);
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const esAdmin = user?.role === "admin" || user?.role === "supervisor";

  const cargar = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getJson("/inventory/stock");
      setStockLevels(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(getErrorMessage(err, "No se pudo cargar los parametros de stock."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const abrirCrear = () => {
    setEditingRule(null);
    setFormError(null);
    setDrawerMode("create");
  };
  const abrirEditar = (rule) => {
    setEditingRule({
      ...rule,
      existing_product_id: rule.product_id,
      existing_product_sku: rule.product_sku,
      existing_product_name: rule.product_name,
    });
    setFormError(null);
    setDrawerMode("edit");
  };
  const cerrarDrawer = () => {
    setDrawerMode(null);
    setEditingRule(null);
    setFormError(null);
  };

  const onSubmit = async ({ producto_id, bodega_id, payload }) => {
    setSubmitting(true);
    setFormError(null);
    setPendingLabel(drawerMode === "create" ? "Creando regla..." : "Guardando cambios...");
    try {
      await putJson(
        `/inventory/parametros/${producto_id}/${bodega_id}`,
        payload,
      );
      pushToast({
        tone: "success",
        title: "Regla guardada",
        description: "Parametros actualizados correctamente.",
      });
      cerrarDrawer();
      await cargar();
    } catch (err) {
      const code = err instanceof ApiError ? err.detail?.detail?.code : null;
      if (code === "invalid_stock_parameter") {
        setFormError(err.detail?.detail?.message || "Parametros invalidos.");
      } else {
        setFormError(getErrorMessage(err, "No se pudo guardar la regla."));
      }
    } finally {
      clearPending();
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          Las reglas de reabastecimiento parametrizan los umbrales min/max
          por (producto x bodega). El Evaluator las consulta cada 5 minutos
          para generar solicitudes automaticas.
        </p>
        {esAdmin ? (
          <button
            type="button"
            onClick={abrirCrear}
            className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500"
          >
            Nueva regla
          </button>
        ) : null}
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <p className="p-4 text-sm text-slate-500">Cargando reglas...</p>
        ) : error ? (
          <p className="p-4 text-sm text-rose-600">Error: {error}</p>
        ) : stockLevels.length === 0 ? (
          <p className="p-6 text-center text-sm text-slate-500">
            Sin reglas configuradas. Cree la primera para empezar.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
                  <th className="px-3 py-2">SKU</th>
                  <th className="px-3 py-2">Producto</th>
                  <th className="px-3 py-2">Bodega</th>
                  <th className="px-3 py-2 text-right">Stock actual</th>
                  <th className="px-3 py-2 text-right">Min.</th>
                  <th className="px-3 py-2 text-right">Max.</th>
                  {esAdmin ? <th className="px-3 py-2 text-right">Acciones</th> : null}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {stockLevels.slice(0, 50).map((s) => (
                  <tr key={`${s.warehouse_id}-${s.product_id}`} className="hover:bg-slate-50">
                    <td className="px-3 py-1.5 font-mono text-xs text-slate-700">
                      {s.product_sku}
                    </td>
                    <td className="px-3 py-1.5 text-slate-800">{s.product_name}</td>
                    <td className="px-3 py-1.5 text-slate-700">
                      <span className="font-mono text-xs">{s.warehouse_code}</span>{" "}
                      {s.warehouse_name}
                    </td>
                    <td className="px-3 py-1.5 text-right font-semibold text-slate-800">
                      {s.quantity}
                    </td>
                    <td className="px-3 py-1.5 text-right text-slate-600">
                      {s.min_quantity}
                    </td>
                    <td className="px-3 py-1.5 text-right text-slate-500">-</td>
                    {esAdmin ? (
                      <td className="px-3 py-1.5 text-right">
                        <button
                          type="button"
                          onClick={() => abrirEditar(s)}
                          className="rounded border border-indigo-300 px-2 py-0.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                        >
                          Editar
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
            {stockLevels.length > 50 ? (
              <p className="mt-2 px-3 text-xs text-slate-500">
                Mostrando 50 de {stockLevels.length}.
              </p>
            ) : null}
          </div>
        )}
      </div>

      <Drawer
        open={drawerMode !== null}
        onClose={cerrarDrawer}
        title={drawerMode === "create" ? "Nueva regla" : "Editar regla"}
      >
        <ReplenishmentRuleForm
          initial={editingRule}
          onSubmit={onSubmit}
          onCancel={cerrarDrawer}
          submitting={submitting}
          error={formError}
        />
      </Drawer>
    </div>
  );
}
