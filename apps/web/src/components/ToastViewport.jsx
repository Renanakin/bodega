import { useUi } from "../context/UiContext";

export function ToastViewport() {
  const { toasts } = useUi();

  return (
    <div className="toast-viewport" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <article
          key={toast.id}
          className={`toast-card toast-card-${toast.tone || "neutral"}`}
        >
          <strong>{toast.title}</strong>
          {toast.description ? <p>{toast.description}</p> : null}
        </article>
      ))}
    </div>
  );
}

