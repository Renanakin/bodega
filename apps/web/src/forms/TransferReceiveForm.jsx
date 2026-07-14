import { FormField } from "../components/FormField";
import { FormGrid } from "../components/FormGrid";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";
import { getErrorMessage, postJson } from "../lib/api";

function validate(values) {
  const errors = {};
  if (!values.quantity || Number(values.quantity) <= 0) errors.quantity = "Indica una cantidad valida.";
  return errors;
}

export function TransferReceiveForm({ transfer, onSuccess }) {
  const pendingQuantity = Number(transfer.quantity) - Number(transfer.received_quantity || 0);
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, errors, setValue, runValidation } = useFormState(
    {
      quantity: String(pendingQuantity),
      notes: "",
      incident_type: "",
      incident_notes: "",
    },
    validate,
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!runValidation()) return;
    setPendingLabel(`Recibiendo ${transfer.code}...`);
    try {
      await postJson(`/transfers/${transfer.id}/receive`, {
        quantity: Number(values.quantity),
        notes: values.notes,
        incident_type: values.incident_type || null,
        incident_notes: values.incident_notes || null,
      });
      pushToast({
        tone: "success",
        title: Number(values.quantity) < pendingQuantity ? "Recepcion parcial registrada" : "Recepcion registrada",
        description: `${transfer.code} actualizo el stock de destino con trazabilidad completa.`,
      });
      onSuccess?.();
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo registrar la recepcion",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <form className="form-stack" onSubmit={handleSubmit}>
      <p className="muted-copy">Pendiente por recibir: {pendingQuantity}</p>
      <FormGrid>
        <FormField label="Cantidad recibida" error={errors.quantity} required>
          <input
            type="number"
            min="0.01"
            step="0.01"
            max={pendingQuantity}
            value={values.quantity}
            onChange={(event) => setValue("quantity", event.target.value)}
          />
        </FormField>
        <FormField label="Incidencia">
          <select
            value={values.incident_type}
            onChange={(event) => setValue("incident_type", event.target.value)}
          >
            <option value="">Sin incidencia</option>
            <option value="faltante">Faltante</option>
            <option value="danio">Danio</option>
            <option value="documentacion">Documentacion</option>
          </select>
        </FormField>
      </FormGrid>
      <FormField label="Observacion de recepcion">
        <textarea
          rows="3"
          value={values.notes}
          onChange={(event) => setValue("notes", event.target.value)}
        />
      </FormField>
      <FormField label="Detalle de incidencia">
        <textarea
          rows="3"
          value={values.incident_notes}
          onChange={(event) => setValue("incident_notes", event.target.value)}
        />
      </FormField>
      <div className="form-actions">
        <button className="primary-button" type="submit">
          Confirmar recepcion
        </button>
      </div>
    </form>
  );
}
