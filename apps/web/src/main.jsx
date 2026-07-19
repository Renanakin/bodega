import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "./context/AuthContext";
import { UiProvider } from "./context/UiContext";
import { AppRouter } from "./router";
import "./styles.css";
import "./tailwind-shim.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <UiProvider>
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
        </BrowserRouter>
      </AuthProvider>
    </UiProvider>
  </React.StrictMode>,
);
