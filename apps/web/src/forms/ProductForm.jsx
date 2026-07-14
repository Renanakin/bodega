import { FormField } from "../components/FormField";
import { FormGrid } from "../components/FormGrid";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";
import { getErrorMessage, postJson } from "../lib/api";

const initialValues = {
  sku: "",
  name: "",
  unit: "unidad",
};

function validate(values) {
  const errors = {};
  if (!values.sku.trim()) errors.sku = "Ingresa un SKU.";
  if (!values.name.trim()) errors.name = "Ingresa un nombre.";
  if (!values.unit.trim()) errors.unit = "Ingresa una unidad.";
  return errors;
}

export function ProductForm({ onSuccess }) {
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, errors, setValue, reset, runValidation } = useFormState(
    initialValues,
    validate,
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!runValidation()) return;

    setPendingLabel("Creando producto...");

    try {
      const product = await postJson("/products", values);
      pushToast({
        tone: "success",
        title: "Producto creado",
        description: `${product.sku} ya forma parte del catalogo operativo.`,
      });
      reset();
      onSuccess?.(product);
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo crear el producto",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <form className="form-stack" onSubmit={handleSubmit}>
      <FormGrid>
        <FormField label="SKU" error={errors.sku} required>
          <input
            placeholder="SKU-001"
            value={values.sku}
            onChange={(event) => setValue("sku", event.target.value)}
          />
        </FormField>
        <FormField label="Nombre" error={errors.name} required>
          <input
            placeholder="Producto de revision"
            value={values.name}
            onChange={(event) => setValue("name", event.target.value)}
          />
        </FormField>
        <FormField label="Unidad" error={errors.unit} required>
          <input
            placeholder="unidad"
            value={values.unit}
            onChange={(event) => setValue("unit", event.target.value)}
          />
        </FormField>
      </FormGrid>

      <div className="form-actions">
        <button className="ghost-button" type="button" onClick={reset}>
          Limpiar
        </button>
        <button className="primary-button" type="submit">
          Guardar producto
        </button>
      </div>
    </form>
  );
}
