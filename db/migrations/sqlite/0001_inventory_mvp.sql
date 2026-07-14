CREATE TABLE IF NOT EXISTS warehouses (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    warehouse_type TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id TEXT PRIMARY KEY,
    warehouse_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    movement_type TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    reference_type TEXT,
    reference_id TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    CHECK (movement_type IN ('in', 'out', 'adjustment_in', 'adjustment_out')),
    CHECK (quantity > 0)
);

CREATE TABLE IF NOT EXISTS stock_levels (
    id TEXT PRIMARY KEY,
    warehouse_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity NUMERIC NOT NULL DEFAULT 0,
    min_quantity NUMERIC NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE (warehouse_id, product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    CHECK (quantity >= 0),
    CHECK (min_quantity >= 0)
);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_warehouse_product_created_at
    ON inventory_movements (warehouse_id, product_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_inventory_movements_product_created_at
    ON inventory_movements (product_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_stock_levels_product
    ON stock_levels (product_id);
