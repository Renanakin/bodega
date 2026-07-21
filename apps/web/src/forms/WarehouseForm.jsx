import { FormField } from "../components/FormField";
import { FormGrid } from "../components/FormGrid";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";
import { getErrorMessage, postJson } from "../lib/api";

const initialValues = {
  code: "",
  name: "",
  warehouse_type: "principal",
};

function validate(values) {
  const errors = {};
  if (!values.code.trim()) errors.code = "Ingresa un codigo.";
  if (!values.name.trim()) errors.name = "Ingresa un nombre.";
  if (!values.warehouse_type.trim()) errors.warehouse_type = "Selecciona un tipo.";
  return errors;
}

export function WarehouseForm({ onSuccess }) {
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, errors, setValue, reset, runValidation } = useFormState(
    initialValues,
    validate,
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!runValidation()) return;

    setPendingLabel("Creando bodega...");
    try {
      const warehouse = await postJson("/warehouses", values);
      pushToast({
        tone: "success",
        title: "Bodega creada",
        description: `${warehouse.code} ya puede recibir y transferir stock.`,
      });
      reset();
      onSuccess?.(warehouse);
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo crear la bodega",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <form className="form-stack" onSubmit={handleSubmit}>
      <FormGrid>
        <FormField label="Codigo" error={errors.code} required>
          <input
            placeholder="CENTRAL"
            value={values.code}
            onChange={(event) => setValue("code", event.target.value)}
          />
        </FormField>
        <FormField label="Nombre" error={errors.name} required>
          <input
            placeholder="Bodega Central"
            value={values.name}
            onChange={(event) => setValue("name", event.target.value)}
          />
        </FormField>
        <FormField label="Tipo" error={errors.warehouse_type} required>
          <select
            value={values.warehouse_type}
            onChange={(event) => setValue("warehouse_type", event.target.value)}
          >
            <option value="principal">Principal</option>
            <option value="auxiliar">Auxiliar</option>
            <option value="mecanico_box">Caja de mecanico</option>
          </select>
        </FormField>
      </FormGrid>

      <div className="form-actions">
        <button className="ghost-button" type="button" onClick={reset}>
          Limpiar
        </button>
        <button className="primary-button" type="submit">
          Guardar bodega
        </button>
      </div>
    </form>
  );
}
