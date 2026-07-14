import { FormField } from "../components/FormField";
import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";
import { getErrorMessage, postJson } from "../lib/api";

export function TransferDispatchForm({ transfer, onSuccess }) {
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const { values, setValue } = useFormState({ notes: transfer.dispatch_notes || "" });

  const handleSubmit = async (event) => {
    event.preventDefault();
    setPendingLabel(`Despachando ${transfer.code}...`);
    try {
      await postJson(`/transfers/${transfer.id}/dispatch`, { notes: values.notes });
      pushToast({
        tone: "success",
        title: "Despacho registrado",
        description: `${transfer.code} quedo en transito con observacion operacional.`,
      });
      onSuccess?.();
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo despachar",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <form className="form-stack" onSubmit={handleSubmit}>
      <FormField label="Observacion de despacho">
        <textarea
          rows="4"
          value={values.notes}
          onChange={(event) => setValue("notes", event.target.value)}
        />
      </FormField>
      <div className="form-actions">
        <button className="primary-button" type="submit">
          Confirmar despacho
        </button>
      </div>
    </form>
  );
}
