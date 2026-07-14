import { FormField } from "../components/FormField";
import { FormGrid } from "../components/FormGrid";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";
import { getErrorMessage, postJson } from "../lib/api";

const initialValues = {
  warehouseId: "",
  productId: "",
  quantity: "",
  referenceId: "",
  notes: "",
};

function validate(values) {
  const errors = {};
  if (!values.warehouseId) errors.warehouseId = "Selecciona una bodega.";
  if (!values.productId) errors.productId = "Selecciona un producto.";
  if (!values.quantity || Number(values.quantity) <= 0) errors.quantity = "Ingresa una cantidad valida.";
  if (!values.referenceId.trim()) errors.referenceId = "Ingresa una referencia.";
  return errors;
}

export function ReceiptForm({ warehouses = [], products = [], onSuccess }) {
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, errors, setValue, reset, runValidation } = useFormState(
    initialValues,
    validate,
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!runValidation()) return;

    const selectedProduct = products.find((item) => item.id === values.productId);
    setPendingLabel("Registrando carga...");
    try {
      await postJson("/inventory/movements", {
        warehouse_id: values.warehouseId,
        product_id: values.productId,
        movement_type: "in",
        quantity: Number(values.quantity),
        reference_type: "receipt",
        reference_id: values.referenceId,
        notes: values.notes || "Carga inicial",
      });
      pushToast({
        tone: "success",
        title: "Carga registrada",
        description: `${selectedProduct?.sku || "Producto"} ya quedo disponible en bodega.`,
      });
      reset();
      onSuccess?.();
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo registrar la carga",
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
        <FormField label="Cantidad" error={errors.quantity} required>
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={values.quantity}
            onChange={(event) => setValue("quantity", event.target.value)}
          />
        </FormField>
        <FormField label="Referencia" error={errors.referenceId} required>
          <input
            placeholder="OC-0001 / GUIA-0001"
            value={values.referenceId}
            onChange={(event) => setValue("referenceId", event.target.value)}
          />
        </FormField>
      </FormGrid>

      <FormField label="Observacion">
        <textarea
          rows="4"
          value={values.notes}
          onChange={(event) => setValue("notes", event.target.value)}
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
          Registrar carga
        </button>
      </div>
    </form>
  );
}
