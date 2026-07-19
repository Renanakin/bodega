-- 0005_products_extension.sqlite.sql
-- Mirror SQLite de 0005_products_extension.sql (Postgres).
-- Añade codigo_barras, id_categoria, precio_costo, precio_venta a products.
-- Crea detalles_neumaticos (1:1 opt-in).

ALTER TABLE products ADD COLUMN codigo_barras TEXT;
ALTER TABLE products ADD COLUMN id_categoria TEXT;
ALTER TABLE products ADD COLUMN precio_costo NUMERIC NOT NULL DEFAULT 0;
ALTER TABLE products ADD COLUMN precio_venta NUMERIC NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS uq_products_codigo_barras
    ON products (codigo_barras)
    WHERE codigo_barras IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_products_id_categoria
    ON products (id_categoria);

CREATE TABLE IF NOT EXISTS detalles_neumaticos (
    producto_id TEXT PRIMARY KEY,
    ancho INTEGER NOT NULL,
    perfil INTEGER NOT NULL,
    aro INTEGER NOT NULL,
    indice_carga INTEGER,
    indice_velocidad TEXT,
    dot TEXT,
    FOREIGN KEY (producto_id) REFERENCES products(id) ON DELETE CASCADE,
    CHECK (ancho > 0),
    CHECK (perfil > 0),
    CHECK (aro > 0)
);
