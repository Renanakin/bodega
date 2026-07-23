const API_BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";
const AUTH_TOKEN_KEY = "bodegaje_auth_token";
const REFRESH_TOKEN_KEY = "bodegaje_refresh_token";

function readStoredToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

function readStoredRefreshToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(REFRESH_TOKEN_KEY) || "";
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// BUG 8 (fix 2026-07-23): cuando el access token expira o el backend lo
// rechaza con 401, intentamos refresh con el refresh_token una vez y
// reintentamos el request original. Si el refresh tambien falla, limpiamos
// la sesion y dejamos que el caller muestre el error (el AuthContext
// detecta la falta de token y redirige a /login).
let refreshInFlight = null;

async function tryRefresh() {
  const refreshToken = readStoredRefreshToken();
  if (!refreshToken) return false;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!resp.ok) {
        clearStoredToken();
        return false;
      }
      const data = await resp.json();
      if (data.token && data.refresh_token) {
        setStoredToken(data.token);
        setStoredRefreshToken(data.refresh_token);
        return true;
      }
      return false;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

async function request(path, options = {}, _retried = false) {
  let response;

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  const token = readStoredToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  } catch (error) {
    throw new ApiError("No se pudo conectar con la API.", 0, error);
  }

  // Si recibimos 401 y no hemos reintentado, intentar refresh una vez.
  // Excluir solo los endpoints de autenticacion propiamente dichos
  // (login, refresh, logout) para evitar loops infinitos. /auth/me
  // SÍ entra al refresh, porque es el endpoint que el AuthContext
  // usa para validar la sesion y donde la mayoria de los 401
  // "fantasma" aparecen al cargar la pagina con token expirado.
  const isAuthSelfCall =
    path.startsWith("/auth/login") ||
    path.startsWith("/auth/refresh") ||
    path.startsWith("/auth/logout");
  if (response.status === 401 && !_retried && !isAuthSelfCall) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      // Reintentar el request original con el nuevo token.
      return request(path, options, true);
    }
    // Refresh fallo: limpiar sesion y dejar que el caller muestre el error.
    clearStoredToken();
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    // Normalizar siempre a string para que React no renderice "[object Object]"
    // cuando el backend devuelve arrays/objetos en `detail` (ej. 422 de FastAPI).
    let message;
    if (typeof payload?.detail === "string") {
      message = payload.detail;
    } else if (Array.isArray(payload?.detail) && payload.detail[0]?.msg) {
      // FastAPI 422: [{type, loc, msg, ...}, ...]
      message = payload.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    } else if (typeof payload?.detail?.message === "string") {
      message = payload.detail.message;
    } else if (typeof payload?.detail?.code === "string") {
      message = payload.detail.code;
    } else {
      message = `Request failed: ${response.status}`;
    }
    throw new ApiError(message, response.status, payload);
  }

  return payload;
}

export function getStoredToken() {
  return readStoredToken();
}

export function setStoredToken(token) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token);
  }
}

export function getStoredRefreshToken() {
  return readStoredRefreshToken();
}

export function setStoredRefreshToken(token) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(REFRESH_TOKEN_KEY, token);
  }
}

export function clearStoredToken() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
}

export async function fetchJson(path, fallback) {
  try {
    return await request(path);
  } catch (error) {
    if (typeof fallback === "function") {
      return fallback();
    }
    return fallback;
  }
}

export function getJson(path, options = {}) {
  return request(path, options);
}

export function postJson(path, body) {
  return request(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function patchJson(path, body) {
  return request(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteJson(path) {
  return request(path, { method: "DELETE" });
}

export function putJson(path, body) {
  return request(path, {
    method: "PUT",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function getErrorMessage(error, fallback = "Ocurrio un error inesperado.") {
  if (error instanceof ApiError) {
    if (typeof error.detail?.detail?.message === "string") {
      return error.detail.detail.message;
    }
    if (typeof error.detail?.detail?.code === "string") {
      return error.detail.detail.code;
    }
    if (typeof error.message === "string" && error.message) {
      return error.message;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}
