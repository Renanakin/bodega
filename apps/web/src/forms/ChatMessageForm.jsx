import { useUi } from "../context/UiContext";
import { useFormState } from "../hooks/useFormState";

const initialValues = { message: "" };

function validate(values) {
  const errors = {};
  if (!values.message.trim()) errors.message = "Escribe un mensaje.";
  return errors;
}

export function ChatMessageForm() {
  const { pushToast } = useUi();
  const { values, errors, setValue, reset, runValidation } = useFormState(
    initialValues,
    validate,
  );

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!runValidation()) return;
    pushToast({
      tone: "neutral",
      title: "Mensaje enviado",
      description: "El mensaje se agrego al canal operativo actual.",
    });
    reset();
  };

  return (
    <form className="chat-form" onSubmit={handleSubmit}>
      <textarea
        className={errors.message ? "field-error-input" : ""}
        placeholder="Escribe un mensaje o usa una plantilla operacional..."
        rows="4"
        value={values.message}
        onChange={(event) => setValue("message", event.target.value)}
      />
      {errors.message ? <small className="form-error">{errors.message}</small> : null}
      <div className="chat-form-actions">
        <button className="ghost-button" type="button">
          Adjuntar
        </button>
        <button className="primary-button" type="submit">
          Enviar
        </button>
      </div>
    </form>
  );
}

