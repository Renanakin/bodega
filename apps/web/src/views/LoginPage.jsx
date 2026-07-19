import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { useUi } from "../context/UiContext";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated, ready, getErrorMessage } = useAuth();
  const { pushToast, setPendingLabel, clearPending } = useUi();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");

  if (ready && isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    setPendingLabel("Iniciando sesion...");
    try {
      await login(username, password);
      navigate(location.state?.from?.pathname || "/dashboard", { replace: true });
      pushToast({
        tone: "success",
        title: "Sesion iniciada",
        description: `Bienvenido, ${username}.`,
      });
    } catch (error) {
      pushToast({
        tone: "danger",
        title: "No se pudo iniciar sesion",
        description: getErrorMessage(error),
      });
    } finally {
      clearPending();
    }
  };

  return (
    <div className="login-shell">
      <section className="login-card">
        <p className="page-kicker">Acceso demo</p>
        <h1>Ingresa a la operacion multi-bodega</h1>
        <p className="page-description">
          Usa uno de los perfiles demo para probar permisos, flujo y auditoria.
        </p>
        <form className="form-stack" onSubmit={handleSubmit}>
          <label className="form-field">
            <span className="form-label">Usuario</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label className="form-field">
            <span className="form-label">Contrasena</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button className="primary-button" type="submit">
            Entrar
          </button>
        </form>
        {import.meta.env.DEV && (
          <div className="plain-list">
            <div>`admin` / `demo123`</div>
            <div>`supervisor` / `demo123`</div>
            <div>`origen` / `demo123`</div>
            <div>`destino` / `demo123`</div>
          </div>
        )}
      </section>
    </div>
  );
}
