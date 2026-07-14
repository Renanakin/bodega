import { FormField } from "../components/FormField";
import { FormGrid } from "../components/FormGrid";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";
import { getErrorMessage, postJson } from "../lib/api";

const initialValues = {
  fromWarehouseId: "",
  toWarehouseId: "",
  priority: "Alta",
  productId: "",
  quantity: "",
  note: "",
};

function validate(values) {
  const errors = {};
  if (!values.fromWarehouseId) errors.fromWarehouseId = "Selecciona la bodega origen.";
  if (!values.toWarehouseId) errors.toWarehouseId = "Selecciona la bodega destino.";
  if (!values.productId) errors.productId = "Selecciona un producto.";
  if (!values.quantity || Number(values.quantity) <= 0) errors.quantity = "Indica una cantidad valida.";
  if (
    values.fromWarehouseId &&
    values.toWarehouseId &&
    values.fromWarehouseId === values.toWarehouseId
  ) {
    errors.toWarehouseId = "Origen y destino deben ser distintos.";
  }
  return errors;
}

export function TransferForm({ warehouses = [], products = [], onSuccess }) {
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, errors, setValue, reset, runValidation } = useFormState(
    initialValues,
    validate,
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!runValidation()) return;
    const origin = warehouses.find((item) => item.id === values.fromWarehouseId);
    const destination = warehouses.find((item) => item.id === values.toWarehouseId);
    setPendingLabel("Creando transferencia...");
    try {
      await postJson("/transfers", {
        from_warehouse_id: values.fromWarehouseId,
        to_warehouse_id: values.toWarehouseId,
        product_id: values.productId,
        quantity: Number(values.quantity),
        priority: values.priority,
        notes: values.note,
      });
      pushToast({
        tone: "success",
        title: "Transferencia solicitada",
        description: `Solicitud creada desde ${origin?.name || "origen"} hacia ${destination?.name || "destino"}.`,
      });
      reset();
      onSuccess?.();
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo crear la transferencia",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <form className="form-stack" onSubmit={handleSubmit}>
      <FormGrid>
        <FormField label="Bodega origen" error={errors.fromWarehouseId} required>
          <select
            value={values.fromWarehouseId}
            onChange={(event) => setValue("fromWarehouseId", event.target.value)}
          >
            <option value="">Selecciona</option>
            {warehouses.map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.name}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Bodega destino" error={errors.toWarehouseId} required>
          <select
            value={values.toWarehouseId}
            onChange={(event) => setValue("toWarehouseId", event.target.value)}
          >
            <option value="">Selecciona</option>
            {warehouses.map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.name}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Prioridad">
          <select
            value={values.priority}
            onChange={(event) => setValue("priority", event.target.value)}
          >
            <option>Alta</option>
            <option>Media</option>
            <option>Baja</option>
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
            min="1"
            step="0.01"
            value={values.quantity}
            onChange={(event) => setValue("quantity", event.target.value)}
          />
        </FormField>
      </FormGrid>
      <FormField label="Observacion">
        <textarea
          rows="4"
          value={values.note}
          onChange={(event) => setValue("note", event.target.value)}
        />
      </FormField>
      <div className="form-actions">
        <button className="ghost-button" type="button" onClick={reset}>
          Limpiar
        </button>
        <button
          className="primary-button"
          type="submit"
          disabled={warehouses.length < 2 || !products.length}
        >
          Crear solicitud
        </button>
      </div>
    </form>
  );
}
