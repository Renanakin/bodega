// Tab de navegacion para la pagina de Settings.
export function TabButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
        active
          ? "border-indigo-600 text-indigo-700"
          : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-800"
      }`}
    >
      {children}
    </button>
  );
}
