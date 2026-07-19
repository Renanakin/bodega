-- 0007_stock_real.sqlite.sql
-- Mirror SQLite de 0007_stock_real.sql (Postgres).

CREATE TABLE IF NOT EXISTS inventario_stock_real (
    id_producto TEXT NOT NULL,
    id_ubicacion TEXT NOT NULL,
    cantidad NUMERIC NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (id_producto, id_ubicacion),
    FOREIGN KEY (id_producto) REFERENCES products(id) ON DELETE CASCADE,
    FOREIGN KEY (id_ubicacion) REFERENCES ubicaciones_estanteria(id) ON DELETE CASCADE,
    CHECK (cantidad >= 0)
);

ALTER TABLE stock_levels ADD COLUMN max_quantity NUMERIC;

CREATE INDEX IF NOT EXISTS idx_inventario_stock_real_ubicacion
    ON inventario_stock_real (id_ubicacion);
