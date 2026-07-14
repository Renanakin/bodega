import { FormField } from "../components/FormField";
import { FormGrid } from "../components/FormGrid";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";
import { getErrorMessage, patchJson } from "../lib/api";

function validate(values) {
  const errors = {};
  if (!values.quantity || Number(values.quantity) <= 0) errors.quantity = "Indica una cantidad valida.";
  return errors;
}

export function TransferEditForm({ transfer, onSuccess }) {
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, errors, setValue, runValidation } = useFormState(
    {
      quantity: String(transfer.quantity),
      priority: transfer.priority || "Media",
      notes: transfer.notes || "",
    },
    validate,
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!runValidation()) return;
    setPendingLabel(`Actualizando ${transfer.code}...`);
    try {
      await patchJson(`/transfers/${transfer.id}`, {
        quantity: Number(values.quantity),
        priority: values.priority,
        notes: values.notes,
      });
      pushToast({
        tone: "success",
        title: "Solicitud actualizada",
        description: `${transfer.code} quedo actualizada antes de la aprobacion.`,
      });
      onSuccess?.();
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo editar la transferencia",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <form className="form-stack" onSubmit={handleSubmit}>
      <FormGrid>
        <FormField label="Cantidad" error={errors.quantity} required>
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={values.quantity}
            onChange={(event) => setValue("quantity", event.target.value)}
          />
        </FormField>
        <FormField label="Prioridad">
          <select value={values.priority} onChange={(event) => setValue("priority", event.target.value)}>
            <option>Alta</option>
            <option>Media</option>
            <option>Baja</option>
          </select>
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
        <button className="primary-button" type="submit">
          Guardar cambios
        </button>
      </div>
    </form>
  );
}
