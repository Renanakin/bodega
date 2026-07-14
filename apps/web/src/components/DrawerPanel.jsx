export function DrawerPanel({ title, description, isOpen, onClose, children }) {
  return (
    <div className={isOpen ? "drawer drawer-open" : "drawer"}>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer-panel">
        <header className="drawer-header">
          <div>
            <h3>{title}</h3>
            {description ? <p>{description}</p> : null}
          </div>
          <button className="ghost-button" type="button" onClick={onClose}>
            Cerrar
          </button>
        </header>
        <div className="drawer-content">{children}</div>
      </aside>
    </div>
  );
}

