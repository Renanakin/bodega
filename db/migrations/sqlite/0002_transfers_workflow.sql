CREATE TABLE IF NOT EXISTS transfers (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    from_warehouse_id TEXT NOT NULL,
    to_warehouse_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    quantity NUMERIC NOT NULL,
    received_quantity NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    priority TEXT,
    notes TEXT,
    dispatch_notes TEXT,
    receive_notes TEXT,
    incident_type TEXT,
    incident_notes TEXT,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    dispatched_at TEXT,
    received_at TEXT,
    FOREIGN KEY (from_warehouse_id) REFERENCES warehouses(id),
    FOREIGN KEY (to_warehouse_id) REFERENCES warehouses(id),
    FOREIGN KEY (product_id) REFERENCES products(id),
    CHECK (quantity > 0),
    CHECK (status IN ('requested', 'approved', 'dispatched', 'partially_received', 'received', 'cancelled')),
    CHECK (from_warehouse_id <> to_warehouse_id),
    CHECK (received_quantity >= 0 AND received_quantity <= quantity)
);

CREATE INDEX IF NOT EXISTS idx_transfers_status_created_at
    ON transfers (status, created_at DESC);
