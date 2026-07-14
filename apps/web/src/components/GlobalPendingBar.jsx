import { useUi } from "../context/UiContext";

export function GlobalPendingBar() {
  const { pendingLabel } = useUi();

  if (!pendingLabel) return null;

  return (
    <div className="pending-bar">
      <div className="pending-bar-spinner" />
      <span>{pendingLabel}</span>
    </div>
  );
}

