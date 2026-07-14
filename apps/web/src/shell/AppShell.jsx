import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { GlobalPendingBar } from "../components/GlobalPendingBar";
import { ToastViewport } from "../components/ToastViewport";
import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

const navigation = [
  { to: "/dashboard", label: "Dashboard", presentation: true },
  { to: "/warehouses", label: "Bodegas", presentation: false },
  { to: "/receipts", label: "Recepciones", presentation: false },
  { to: "/inventory", label: "Inventario", presentation: true },
  { to: "/products", label: "Productos", presentation: false },
  { to: "/transfers", label: "Transferencias", presentation: true },
  { to: "/replenishment", label: "Reposicion", presentation: false },
  { to: "/slotting", label: "Slotting", presentation: false },
  { to: "/chat", label: "Chat", presentation: false },
  { to: "/reports", label: "Reportes", presentation: true },
  { to: "/settings", label: "Configuracion", presentation: true },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    presentationMode,
    presentationStepIndex,
    presentationSteps,
    togglePresentationMode,
    nextPresentationStep,
    previousPresentationStep,
    setPresentationStep,
  } = useUi();
  const currentStep =
    presentationSteps.find((step) => step.path === location.pathname) ||
    presentationSteps[presentationStepIndex];
  const visibleNavigation = presentationMode
    ? navigation.filter((item) => item.presentation)
    : navigation;

  const handleNextStep = () => {
    const currentIndex = presentationSteps.findIndex((step) => step.path === location.pathname);
    const nextIndex =
      currentIndex >= 0 ? Math.min(currentIndex + 1, presentationSteps.length - 1) : presentationStepIndex + 1;
    setPresentationStep(nextIndex);
    navigate(presentationSteps[nextIndex].path);
  };

  const handlePreviousStep = () => {
    const currentIndex = presentationSteps.findIndex((step) => step.path === location.pathname);
    const previousIndex = currentIndex >= 0 ? Math.max(currentIndex - 1, 0) : presentationStepIndex - 1;
    setPresentationStep(previousIndex);
    navigate(presentationSteps[previousIndex].path);
  };

  return (
    <div className={presentationMode ? "app-shell app-shell-presentation" : "app-shell"}>
      <ToastViewport />
      <GlobalPendingBar />
      <aside className="sidebar">
        <div className="brand-block">
          <p className="brand-overline">Hackteck SpA</p>
          <h1>Bodegaje</h1>
          <p className="brand-copy">
            Plataforma operativa para control multi-bodega en tiempo real.
          </p>
        </div>

        <nav className="sidebar-nav">
          {visibleNavigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? "nav-link nav-link-active" : "nav-link"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <p>Operacion actual</p>
          <strong>{user?.full_name}</strong>
          <p>{user?.role}</p>
          <button className="ghost-button" type="button" onClick={logout}>
            Cerrar sesion
          </button>
        </div>
      </aside>

      <div className="main-column">
        {presentationMode ? (
          <>
            <section className="presentation-banner">
              <strong>Modo presentacion activo</strong>
              <p>La navegacion se redujo a las pantallas con mayor impacto comercial.</p>
            </section>
            <section className="presentation-guide">
              <div className="presentation-guide-copy">
                <p className="page-kicker">Paso {presentationStepIndex + 1}</p>
                <h2>{currentStep?.title}</h2>
                <p>{currentStep?.description}</p>
                <p className="muted-copy">{currentStep?.pitch}</p>
              </div>
              <div className="presentation-guide-actions">
                <button
                  className="ghost-button"
                  type="button"
                  disabled={presentationStepIndex === 0}
                  onClick={handlePreviousStep}
                >
                  Paso anterior
                </button>
                <button
                  className="primary-button"
                  type="button"
                  disabled={presentationStepIndex === presentationSteps.length - 1}
                  onClick={handleNextStep}
                >
                  Siguiente paso
                </button>
              </div>
            </section>
          </>
        ) : null}
        <header className="topbar">
          <div className="topbar-meta">
            <p className="topbar-label">Ambiente</p>
            <strong>Local / Pre-produccion</strong>
            <p className="muted-copy">Rol activo: {user?.role}</p>
          </div>
          <div className="topbar-search">
            <input
              className="search-input"
              type="search"
              placeholder="Buscar producto, SKU o transferencia"
            />
          </div>
          <div className="topbar-actions">
            <button className="ghost-button" type="button" onClick={togglePresentationMode}>
              {presentationMode ? "Salir presentacion" : "Modo presentacion"}
            </button>
            <button className="ghost-button" type="button">
              Exportar
            </button>
            <button className="primary-button" type="button">
              Nuevo movimiento
            </button>
          </div>
        </header>

        <main className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
