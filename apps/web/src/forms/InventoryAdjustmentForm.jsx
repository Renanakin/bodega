import { useMemo, useState } from "react";

import { FormField } from "../components/FormField";
import { FormGrid } from "../components/FormGrid";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";
import { getErrorMessage, postJson } from "../lib/api";

const initialValues = {
  warehouseId: "",
  productId: "",
  reason: "",
  delta: "",
  comment: "",
};

function validate(values) {
  const errors = {};
  if (!values.warehouseId) errors.warehouseId = "Selecciona una bodega.";
  if (!values.productId) errors.productId = "Selecciona un producto.";
  if (!values.reason) errors.reason = "Selecciona un motivo.";
  if (!values.delta || Number(values.delta) === 0) errors.delta = "Indica un ajuste distinto de 0.";
  return errors;
}

export function InventoryAdjustmentForm({ warehouses = [], products = [], onSuccess, onCreated }) {
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, errors, setValue, reset, runValidation } = useFormState(
    initialValues,
    validate,
  );
  // BUG 2: con 237+ bodegas el <select> nativo se vuelve inutilizable.
  // Filtro en cliente por nombre/tipo y ordeno: principales primero,
  // luego auxiliares, luego mecanico_box (inactivas al final).
  const [warehouseFilter, setWarehouseFilter] = useState("");
  const [productFilter, setProductFilter] = useState("");

  const sortedWarehouses = useMemo(() => {
    const order = { principal: 0, auxiliar: 1, mecanico_box: 2 };
    return [...warehouses].sort((a, b) => {
      const ta = order[a.warehouse_type] ?? 99;
      const tb = order[b.warehouse_type] ?? 99;
      if (ta !== tb) return ta - tb;
      // Inactivas al final del grupo
      if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
      return (a.name || "").localeCompare(b.name || "");
    });
  }, [warehouses]);

  const filteredWarehouses = useMemo(() => {
    const q = warehouseFilter.trim().toLowerCase();
    if (!q) return sortedWarehouses;
    return sortedWarehouses.filter((w) =>
      (w.name || "").toLowerCase().includes(q) ||
      (w.code || "").toLowerCase().includes(q) ||
      (w.warehouse_type || "").toLowerCase().includes(q),
    );
  }, [sortedWarehouses, warehouseFilter]);

  const sortedProducts = useMemo(() => {
    return [...products].sort((a, b) => (a.sku || "").localeCompare(b.sku || ""));
  }, [products]);

  const filteredProducts = useMemo(() => {
    const q = productFilter.trim().toLowerCase();
    if (!q) return sortedProducts;
    return sortedProducts.filter((p) =>
      (p.sku || "").toLowerCase().includes(q) ||
      (p.name || "").toLowerCase().includes(q),
    );
  }, [sortedProducts, productFilter]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!runValidation()) return;

    const delta = Number(values.delta);
    const movementType = delta > 0 ? "adjustment_in" : "adjustment_out";
    const selectedProduct = products.find((item) => item.id === values.productId);

    setPendingLabel("Registrando ajuste de inventario...");

    try {
      await postJson("/inventory/movements", {
        warehouse_id: values.warehouseId,
        product_id: values.productId,
        movement_type: movementType,
        quantity: Math.abs(delta),
        reference_type: "manual",
        reference_id: values.reason.toLowerCase().replaceAll(" ", "-"),
        notes: values.comment || values.reason,
      });

      pushToast({
        tone: "warning",
        title: "Ajuste registrado",
        description: `Se actualizo el stock de ${selectedProduct?.sku || "producto"}.`,
      });
      reset();
      onCreated?.();
      onSuccess?.();
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo registrar el ajuste",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <form className="form-stack" onSubmit={handleSubmit}>
      <FormGrid>
        <FormField label="Bodega" error={errors.warehouseId} required>
          <input
            type="search"
            placeholder={`Filtrar ${filteredWarehouses.length}/${warehouses.length} bodegas...`}
            value={warehouseFilter}
            onChange={(event) => setWarehouseFilter(event.target.value)}
          />
          <select
            size={Math.min(8, Math.max(4, filteredWarehouses.length + 1))}
            value={values.warehouseId}
            onChange={(event) => setValue("warehouseId", event.target.value)}
          >
            <option value="">Selecciona una bodega</option>
            {filteredWarehouses.map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.code} - {warehouse.name} ({warehouse.warehouse_type})
                {warehouse.is_active ? "" : " [INACTIVA]"}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Producto" error={errors.productId} required>
          <input
            type="search"
            placeholder={`Filtrar ${filteredProducts.length}/${products.length} productos...`}
            value={productFilter}
            onChange={(event) => setProductFilter(event.target.value)}
          />
          <select
            size={Math.min(8, Math.max(4, filteredProducts.length + 1))}
            value={values.productId}
            onChange={(event) => setValue("productId", event.target.value)}
          >
            <option value="">Selecciona un producto</option>
            {filteredProducts.map((product) => (
              <option key={product.id} value={product.id}>
                {product.sku} - {product.name}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Motivo" error={errors.reason} required>
          <select
            value={values.reason}
            onChange={(event) => setValue("reason", event.target.value)}
          >
            <option value="">Selecciona</option>
            <option value="Conteo ciclico">Conteo ciclico</option>
            <option value="Merma">Merma</option>
            <option value="Diferencia operativa">Diferencia operativa</option>
          </select>
        </FormField>
        <FormField label="Ajuste (+/-)" error={errors.delta} required hint="Positivo suma, negativo resta stock">
          <input
            type="number"
            step="0.01"
            placeholder="ej: 5 o -3"
            value={values.delta}
            onChange={(event) => setValue("delta", event.target.value)}
          />
        </FormField>
      </FormGrid>
      <FormField label="Comentario">
        <textarea
          rows="3"
          value={values.comment}
          onChange={(event) => setValue("comment", event.target.value)}
        />
      </FormField>
      <div className="form-actions">
        <button className="ghost-button" type="button" onClick={reset}>
          Limpiar
        </button>
        <button
          className="primary-button"
          type="submit"
          disabled={!warehouses.length || !products.length}
        >
          Registrar ajuste
        </button>
      </div>
    </form>
  );
}
