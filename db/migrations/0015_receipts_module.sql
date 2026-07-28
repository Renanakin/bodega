-- 0015_receipts_module.sql (Postgres + SQLite)
--
-- FIX (FASE POST-E2E): modulo de Recepciones (manual seccion 8) que estaba
-- documentado pero no implementado. Crea:
-- 1. Tabla receipts + receipt_lines
-- 2. Columna last_approval_token en ordenes_compra (para reenviar el link
--    si el operador pierde el email).

CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY,
    codigo TEXT NOT NULL UNIQUE,
    id_bodega_destino TEXT NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
    id_proveedor TEXT REFERENCES proveedores(id) ON DELETE RESTRICT,
    id_orden_compra TEXT REFERENCES ordenes_compra(id) ON DELETE SET NULL,
    numero_documento TEXT,
    estado TEXT NOT NULL DEFAULT 'pending',
    notas TEXT,
    created_by TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP,
    confirmed_by TEXT REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_receipts_id_bodega_destino ON receipts(id_bodega_destino);
CREATE INDEX IF NOT EXISTS ix_receipts_id_proveedor ON receipts(id_proveedor);
CREATE INDEX IF NOT EXISTS ix_receipts_id_orden_compra ON receipts(id_orden_compra);
CREATE INDEX IF NOT EXISTS ix_receipts_estado ON receipts(estado);
CREATE INDEX IF NOT EXISTS ix_receipts_estado_bodega ON receipts(estado, id_bodega_destino);

CREATE TABLE IF NOT EXISTS receipt_lines (
    id TEXT PRIMARY KEY,
    id_receipt TEXT NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    id_producto TEXT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    cantidad NUMERIC(14,2) NOT NULL,
    precio_unitario NUMERIC(14,2) NOT NULL DEFAULT 0,
    movement_id TEXT
);

CREATE INDEX IF NOT EXISTS ix_receipt_lines_id_receipt ON receipt_lines(id_receipt);
CREATE INDEX IF NOT EXISTS ix_receipt_lines_id_producto ON receipt_lines(id_producto);

ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS last_approval_token TEXT;
