// ReplenishmentRuleForm: form (drawer) para parametrizar reglas de
// reabastecimiento por producto x bodega (Fase 8).
//
// Uso:
//   <ReplenishmentRuleForm
//     initial={...}            // opcional, edicion
//     onSubmit={async (data) => ...}
//     onCancel={() => ...}
//     submitting={boolean}
//     error={string|null}
//   />
//
// Campos:
//   - producto (SearchSku)
//   - bodega (select)
//   - stock_minimo (number, >= 0)
//   - stock_maximo (number, >= stock_minimo)
//   - lead_time_dias (number, default 7, > 0)
//   - supplier_preferred_id (select, opcional)
//
// Endpoint consumido:
//   PUT /api/v1/inventory/parametros/{producto_id}/{bodega_id}
//   Body: { stock_minimo, stock_maximo, lead_time_dias, supplier_preferred_id }
//
// Disenada 100% con Tailwind v3 (ADR-0006).
import { useEffect, useState } from "react";

import { SearchSku } from "./SearchSku";
import { getErrorMessage, getJson, putJson } from "../lib/api";
import { useAuth } from "../context/AuthContext";

const initialValues = {
  producto: null, // { id, sku, name }
  bodega_id: "",
  stock_minimo: "",
  stock_maximo: "",
  lead_time_dias: 7,
  supplier_preferred_id: "",
};

function validate(values) {
  const errors = {};
  if (!values.producto && !values.existing_product_id) {
    errors.producto = "Selecciona un producto.";
  }
  if (!values.bodega_id) {
    errors.bodega_id = "Selecciona una bodega.";
  }
  const min = Number(values.stock_minimo);
  const max = Number(values.stock_maximo);
  const lead = Number(values.lead_time_dias);
  if (values.stock_minimo === "" || Number.isNaN(min) || min < 0) {
    errors.stock_minimo = "Ingresa un minimo valido (>= 0).";
  }
  if (values.stock_maximo === "" || Number.isNaN(max) || max < 0) {
    errors.stock_maximo = "Ingresa un maximo valido (>= 0).";
  }
  if (!Number.isNaN(min) && !Number.isNaN(max) && max < min) {
    errors.stock_maximo = "El maximo debe ser mayor o igual al minimo.";
  }
  if (Number.isNaN(lead) || lead < 0) {
    errors.lead_time_dias = "El lead time debe ser >= 0.";
  }
  return errors;
}

export function ReplenishmentRuleForm({
  initial,
  onSubmit,
  onCancel,
  submitting,
  error,
}) {
  const { user } = useAuth();
  const [values, setValues] = useState(() => ({
    ...initialValues,
    ...initial,
    existing_product_id: initial?.producto_id || null,
  }));
  const [errors, setErrors] = useState({});
  const [bodegas, setBodegas] = useState([]);
  const [proveedores, setProveedores] = useState([]);
  const [loadingCatalogos, setLoadingCatalogos] = useState(true);

  // Cargar bodegas + proveedores en paralelo al montar.
  useEffect(() => {
    let cancelado = false;
    async function cargar() {
      setLoadingCatalogos(true);
      try {
        const [wh, pv] = await Promise.all([
          getJson("/warehouses"),
          getJson("/proveedores?activo=true"),
        ]);
        if (!cancelado) {
          setBodegas(Array.isArray(wh) ? wh : []);
          setProveedores(Array.isArray(pv) ? pv : []);
        }
      } catch (err) {
        if (!cancelado) {
          setErrors((prev) => ({
            ...prev,
            _catalogos: getErrorMessage(err, "Error al cargar catalogos."),
          }));
        }
      } finally {
        if (!cancelado) setLoadingCatalogos(false);
      }
    }
    cargar();
    return () => {
      cancelado = true;
    };
  }, []);

  const setValue = (k, v) => setValues((prev) => ({ ...prev, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    const errs = validate(values);
    setErrors(errs);
    if (Object.keys(errs).length > 0) return;
    const productoId = values.producto?.id || values.existing_product_id;
    const payload = {
      stock_minimo: Number(values.stock_minimo),
      stock_maximo: Number(values.stock_maximo),
      lead_time_dias: Number(values.lead_time_dias),
      supplier_preferred_id: values.supplier_preferred_id || null,
    };
    await onSubmit({ producto_id: productoId, bodega_id: values.bodega_id, payload });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {/* Producto */}
      <div>
        <label htmlFor="rule-prod" className="block text-sm font-medium text-slate-700">
          Producto
        </label>
        {values.producto || values.existing_product_id ? (
          <div className="mt-1 flex items-center gap-2 rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm">
            <span className="font-mono font-semibold text-slate-800">
              {values.producto?.sku || values.existing_product_sku}
            </span>
            <span className="flex-1 truncate text-slate-600">
              {values.producto?.name || values.existing_product_name}
            </span>
            <button
              type="button"
              onClick={() =>
                setValue("producto", null) || setValue("existing_product_id", null)
              }
              className="rounded p-1 text-slate-500 hover:bg-slate-200"
              aria-label="Cambiar producto"
            >
              <span aria-hidden="true">x</span>
            </button>
          </div>
        ) : (
          <div className="mt-1">
            <SearchSku
              onSelect={(p) => setValue("producto", p)}
              placeholder="Buscar SKU o nombre..."
              autoFocus
            />
            {errors.producto ? (
              <p className="mt-1 text-xs text-rose-600">{errors.producto}</p>
            ) : null}
          </div>
        )}
      </div>

      {/* Bodega */}
      <div>
        <label htmlFor="rule-bodega" className="block text-sm font-medium text-slate-700">
          Bodega
        </label>
        <select
          id="rule-bodega"
          value={values.bodega_id}
          onChange={(e) => setValue("bodega_id", e.target.value)}
          disabled={loadingCatalogos}
          className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-100"
        >
          <option value="">Selecciona...</option>
          {bodegas.map((b) => (
            <option key={b.id} value={b.id}>
              {b.code} — {b.name}
            </option>
          ))}
        </select>
        {errors.bodega_id ? (
          <p className="mt-1 text-xs text-rose-600">{errors.bodega_id}</p>
        ) : null}
      </div>

      {/* Min / Max */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="rule-min" className="block text-sm font-medium text-slate-700">
            Stock minimo
          </label>
          <input
            id="rule-min"
            type="number"
            min="0"
            step="1"
            value={values.stock_minimo}
            onChange={(e) => setValue("stock_minimo", e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          {errors.stock_minimo ? (
            <p className="mt-1 text-xs text-rose-600">{errors.stock_minimo}</p>
          ) : null}
        </div>
        <div>
          <label htmlFor="rule-max" className="block text-sm font-medium text-slate-700">
            Stock maximo
          </label>
          <input
            id="rule-max"
            type="number"
            min="0"
            step="1"
            value={values.stock_maximo}
            onChange={(e) => setValue("stock_maximo", e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          {errors.stock_maximo ? (
            <p className="mt-1 text-xs text-rose-600">{errors.stock_maximo}</p>
          ) : null}
        </div>
      </div>

      {/* Lead time + proveedor preferido */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="rule-lead" className="block text-sm font-medium text-slate-700">
            Lead time (dias)
          </label>
          <input
            id="rule-lead"
            type="number"
            min="0"
            max="365"
            step="1"
            value={values.lead_time_dias}
            onChange={(e) => setValue("lead_time_dias", e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          {errors.lead_time_dias ? (
            <p className="mt-1 text-xs text-rose-600">{errors.lead_time_dias}</p>
          ) : null}
        </div>
        <div>
          <label htmlFor="rule-prov" className="block text-sm font-medium text-slate-700">
            Proveedor preferido
          </label>
          <select
            id="rule-prov"
            value={values.supplier_preferred_id}
            onChange={(e) => setValue("supplier_preferred_id", e.target.value)}
            disabled={loadingCatalogos}
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:bg-slate-100"
          >
            <option value="">Sin definir</option>
            {proveedores.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </select>
        </div>
      </div>

      {errors._catalogos ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
          {errors._catalogos}
        </p>
      ) : null}
      {error ? (
        <p className="rounded-md border border-rose-200 bg-rose-50 p-2 text-sm text-rose-700">
          {error}
        </p>
      ) : null}

      <div className="flex justify-end gap-2 border-t border-slate-200 pt-3">
        <button
          type="button"
          onClick={onCancel}
          disabled={submitting}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Guardando..." : "Guardar regla"}
        </button>
      </div>
    </form>
  );
}
