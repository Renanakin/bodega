import { createContext, useContext, useEffect, useMemo, useState } from "react";

import {
  clearStoredToken,
  getErrorMessage,
  getJson,
  getStoredToken,
  postJson,
  setStoredRefreshToken,
  setStoredToken,
} from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  const loadUser = async () => {
    const token = getStoredToken();
    if (!token) {
      setUser(null);
      setReady(true);
      return;
    }

    try {
      const currentUser = await getJson("/auth/me");
      setUser(currentUser);
    } catch {
      clearStoredToken();
      setUser(null);
    } finally {
      setReady(true);
    }
  };

  useEffect(() => {
    loadUser();
  }, []);

  const login = async (username, password) => {
    const session = await postJson("/auth/login", { username, password });
    // BUG 8 (fix 2026-07-23): guardar AMBOS tokens (access + refresh)
    // para que el interceptor en lib/api.js pueda auto-refresh cuando
    // el access token expire (1h). El refresh token vive 7 dias.
    if (session.token) setStoredToken(session.token);
    if (session.refresh_token) setStoredRefreshToken(session.refresh_token);
    const currentUser = await getJson("/auth/me");
    setUser(currentUser);
    return currentUser;
  };

  const logout = async () => {
    try {
      if (getStoredToken()) {
        await postJson("/auth/logout");
      }
    } catch {
      // no-op on forced logout
    } finally {
      clearStoredToken();
      setUser(null);
    }
  };

  const value = useMemo(
    () => ({
      user,
      ready,
      isAuthenticated: Boolean(user),
      login,
      logout,
      refreshUser: loadUser,
      getErrorMessage,
    }),
    [ready, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
