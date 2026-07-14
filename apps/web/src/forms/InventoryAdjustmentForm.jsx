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
          <select
            value={values.warehouseId}
            onChange={(event) => setValue("warehouseId", event.target.value)}
          >
            <option value="">Selecciona</option>
            {warehouses.map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.name}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Producto" error={errors.productId} required>
          <select
            value={values.productId}
            onChange={(event) => setValue("productId", event.target.value)}
          >
            <option value="">Selecciona</option>
            {products.map((product) => (
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
        <FormField label="Ajuste (+/-)" error={errors.delta} required>
          <input
            type="number"
            step="0.01"
            value={values.delta}
            onChange={(event) => setValue("delta", event.target.value)}
          />
        </FormField>
      </FormGrid>
      <FormField label="Comentario">
        <textarea
          rows="4"
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
