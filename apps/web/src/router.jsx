import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./context/AuthContext";
import { AppShell } from "./shell/AppShell";
import { DashboardPage } from "./views/DashboardPage";
import { InventoryPage } from "./views/InventoryPage";
import { LoginPage } from "./views/LoginPage";
import { ProductsPage } from "./views/ProductsPage";
import { ReplenishmentPage } from "./views/ReplenishmentPage";
import { ReceiptsPage } from "./views/ReceiptsPage";
import { ReportsPage } from "./views/ReportsPage";
import { SettingsPage } from "./views/SettingsPage";
import { ChatPage } from "./views/ChatPage";
import { SlottingPage } from "./views/SlottingPage";
import { TransfersPage } from "./views/TransfersPage";
import { WarehousesPage } from "./views/WarehousesPage";

function ProtectedLayout() {
  const location = useLocation();
  const { ready, isAuthenticated } = useAuth();

  if (!ready) {
    return <div className="loading-screen">Cargando sesion...</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedLayout />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/warehouses" element={<WarehousesPage />} />
          <Route path="/receipts" element={<ReceiptsPage />} />
          <Route path="/inventory" element={<InventoryPage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/transfers" element={<TransfersPage />} />
          <Route path="/replenishment" element={<ReplenishmentPage />} />
          <Route path="/slotting" element={<SlottingPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
