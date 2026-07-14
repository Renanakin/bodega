import { FormField } from "../components/FormField";
import { FormGrid } from "../components/FormGrid";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";

const initialValues = {
  warehouse: "",
  product: "",
  minStock: "",
  targetStock: "",
  sourceMode: "Transferencia interna",
};

function validate(values) {
  const errors = {};
  if (!values.warehouse) errors.warehouse = "Selecciona una bodega.";
  if (!values.product) errors.product = "Indica el producto.";
  if (!values.minStock) errors.minStock = "Ingresa stock minimo.";
  if (!values.targetStock) errors.targetStock = "Ingresa stock objetivo.";
  return errors;
}

export function ReplenishmentRuleForm({ onSuccess }) {
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, errors, setValue, reset, runValidation } = useFormState(
    initialValues,
    validate,
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!runValidation()) return;
    setPendingLabel("Guardando regla de reposicion...");
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    clearPending();
    pushToast({
      tone: "success",
      title: "Regla guardada",
      description: `${values.product} se controlara automaticamente en ${values.warehouse}.`,
    });
    reset();
    onSuccess?.();
  };

  return (
    <form className="form-stack" onSubmit={handleSubmit}>
      <FormGrid>
        <FormField label="Bodega" error={errors.warehouse} required>
          <select
            value={values.warehouse}
            onChange={(event) => setValue("warehouse", event.target.value)}
          >
            <option value="">Selecciona</option>
            <option value="Central">Central</option>
            <option value="Sucursal Norte">Sucursal Norte</option>
          </select>
        </FormField>
        <FormField label="Producto" error={errors.product} required>
          <input
            value={values.product}
            onChange={(event) => setValue("product", event.target.value)}
          />
        </FormField>
        <FormField label="Stock minimo" error={errors.minStock} required>
          <input
            type="number"
            min="0"
            value={values.minStock}
            onChange={(event) => setValue("minStock", event.target.value)}
          />
        </FormField>
        <FormField label="Stock objetivo" error={errors.targetStock} required>
          <input
            type="number"
            min="0"
            value={values.targetStock}
            onChange={(event) => setValue("targetStock", event.target.value)}
          />
        </FormField>
        <FormField label="Modo de abastecimiento">
          <select
            value={values.sourceMode}
            onChange={(event) => setValue("sourceMode", event.target.value)}
          >
            <option>Transferencia interna</option>
            <option>Orden de compra</option>
            <option>Mixto</option>
          </select>
        </FormField>
      </FormGrid>
      <div className="form-actions">
        <button className="ghost-button" type="button" onClick={reset}>
          Limpiar
        </button>
        <button className="primary-button" type="submit">
          Guardar regla
        </button>
      </div>
    </form>
  );
}

