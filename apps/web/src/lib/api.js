const API_BASE_URL = import.meta.env.VITE_API_URL || "/api/v1";
const AUTH_TOKEN_KEY = "bodegaje_auth_token";

function readStoredToken() {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(readStoredToken() ? { Authorization: `Bearer ${readStoredToken()}` } : {}),
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch (error) {
    throw new ApiError("No se pudo conectar con la API.", 0, error);
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      payload?.detail?.message ||
      payload?.detail?.code ||
      payload?.detail ||
      `Request failed: ${response.status}`;
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

export function clearStoredToken() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
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
