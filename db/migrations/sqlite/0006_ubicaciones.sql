-- 0006_ubicaciones.sqlite.sql
-- Mirror SQLite de 0006_ubicaciones.sql (Postgres).

CREATE TABLE IF NOT EXISTS ubicaciones_estanteria (
    id TEXT PRIMARY KEY,
    id_bodega TEXT NOT NULL,
    pasillo INTEGER NOT NULL,
    estanteria INTEGER NOT NULL,
    altura INTEGER NOT NULL,
    descripcion TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (id_bodega, pasillo, estanteria, altura),
    FOREIGN KEY (id_bodega) REFERENCES warehouses(id) ON DELETE CASCADE,
    CHECK (pasillo > 0),
    CHECK (estanteria > 0),
    CHECK (altura > 0)
);

CREATE INDEX IF NOT EXISTS idx_ubicaciones_bodega
    ON ubicaciones_estanteria (id_bodega);

CREATE INDEX IF NOT EXISTS idx_ubicaciones_bodega_active
    ON ubicaciones_estanteria (id_bodega, is_active);
