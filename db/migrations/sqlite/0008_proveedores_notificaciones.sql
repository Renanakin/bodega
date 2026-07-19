-- 0008_proveedores_notificaciones.sql (Fase 8).
-- Mirror SQLite-compatible de la migración Postgres correspondiente.
-- Agrega:
--   * tabla `proveedores` (catalogo de proveedores externos).
--   * tabla `notificaciones` (in-app, complementaria a `email_outbox`).
--   * columna `lead_time_dias` y `contacto_nombre` a `proveedores` (Fase 8).
-- NOTA: `stock_levels.max_quantity` ya fue agregada en 0007_stock_real.sql
-- para soportar `ReplenishmentRuleForm`. No se vuelve a agregar aca.

-- ----------------------------------------------------------------------------
-- Proveedores (Fase 8)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proveedores (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    rut TEXT NULL UNIQUE,
    email TEXT NULL,
    telefono TEXT NULL,
    direccion TEXT NULL,
    contacto_nombre TEXT NULL,
    lead_time_dias INTEGER NOT NULL DEFAULT 7,
    activo INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (length(nombre) > 0)
);

CREATE INDEX IF NOT EXISTS idx_proveedores_activo
    ON proveedores (activo);

-- ----------------------------------------------------------------------------
-- Notificaciones in-app (Fase 8)
-- Complementa al `email_outbox` (Fase 7) que sigue siendo el transporte async
-- de emails. Esta tabla es el "inbox" del usuario dentro de la app web.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notificaciones (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    mensaje TEXT NULL,
    payload TEXT NULL,
    leida INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    read_at TEXT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CHECK (length(tipo) > 0),
    CHECK (length(titulo) > 0)
);

CREATE INDEX IF NOT EXISTS idx_notificaciones_user_leida
    ON notificaciones (user_id, leida, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notificaciones_tipo
    ON notificaciones (tipo);

