-- 0004_categories.sqlite.sql
-- Mirror SQLite-compatible de 0004_categories.sql (Postgres).
-- Categorías de productos con jerarquía opcional (parent_id self-FK).

CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    parent_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_categories_nombre_unique
    ON categories (nombre);

CREATE INDEX IF NOT EXISTS idx_categories_parent_id
    ON categories (parent_id);
