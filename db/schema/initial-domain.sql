-- Modelo base del MVP de inventario para el sistema multi-bodega.
-- Este archivo funciona como referencia legible del dominio y refleja
-- la misma estructura de la migracion inicial versionada.

create table if not exists warehouses (
    id uuid primary key,
    code varchar(50) not null unique,
    name varchar(150) not null,
    warehouse_type varchar(30) not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_warehouses_code_not_blank check (btrim(code) <> ''),
    constraint chk_warehouses_name_not_blank check (btrim(name) <> ''),
    constraint chk_warehouses_type_not_blank check (btrim(warehouse_type) <> '')
);

create table if not exists products (
    id uuid primary key,
    sku varchar(80) not null unique,
    name varchar(150) not null,
    unit varchar(20) not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_products_sku_not_blank check (btrim(sku) <> ''),
    constraint chk_products_name_not_blank check (btrim(name) <> ''),
    constraint chk_products_unit_not_blank check (btrim(unit) <> '')
);

create table if not exists inventory_movements (
    id uuid primary key,
    warehouse_id uuid not null,
    product_id uuid not null,
    movement_type varchar(30) not null,
    quantity numeric(14, 2) not null,
    reference_type varchar(50),
    reference_id varchar(100),
    notes text,
    created_at timestamptz not null default now(),
    constraint fk_inventory_movements_warehouse foreign key (warehouse_id) references warehouses(id),
    constraint fk_inventory_movements_product foreign key (product_id) references products(id),
    constraint chk_inventory_movements_type check (
        movement_type in ('in', 'out', 'adjustment_in', 'adjustment_out')
    ),
    constraint chk_inventory_movements_quantity_positive check (quantity > 0)
);

create table if not exists stock_levels (
    id uuid primary key,
    warehouse_id uuid not null,
    product_id uuid not null,
    quantity numeric(14, 2) not null default 0,
    min_quantity numeric(14, 2) not null default 0,
    updated_at timestamptz not null default now(),
    constraint fk_stock_warehouse foreign key (warehouse_id) references warehouses(id),
    constraint fk_stock_product foreign key (product_id) references products(id),
    constraint uq_stock unique (warehouse_id, product_id),
    constraint chk_stock_quantity_non_negative check (quantity >= 0),
    constraint chk_stock_min_quantity_non_negative check (min_quantity >= 0)
);

create index if not exists idx_inventory_movements_warehouse_product_created_at
    on inventory_movements (warehouse_id, product_id, created_at desc);

create index if not exists idx_inventory_movements_product_created_at
    on inventory_movements (product_id, created_at desc);

create index if not exists idx_stock_levels_product
    on stock_levels (product_id);

create table if not exists transfers (
    id uuid primary key,
    code varchar(50) not null unique,
    from_warehouse_id uuid not null,
    to_warehouse_id uuid not null,
    product_id uuid not null,
    quantity numeric(14, 2) not null,
    received_quantity numeric(14, 2) not null default 0,
    status varchar(30) not null,
    priority varchar(30),
    notes text,
    dispatch_notes text,
    receive_notes text,
    incident_type varchar(30),
    incident_notes text,
    created_at timestamptz not null default now(),
    approved_at timestamptz,
    dispatched_at timestamptz,
    received_at timestamptz,
    constraint fk_transfers_from_warehouse foreign key (from_warehouse_id) references warehouses(id),
    constraint fk_transfers_to_warehouse foreign key (to_warehouse_id) references warehouses(id),
    constraint fk_transfers_product foreign key (product_id) references products(id),
    constraint chk_transfers_quantity_positive check (quantity > 0),
    constraint chk_transfers_status check (
        status in ('requested', 'approved', 'dispatched', 'partially_received', 'received', 'cancelled')
    ),
    constraint chk_transfers_distinct_warehouses check (from_warehouse_id <> to_warehouse_id),
    constraint chk_transfers_received_quantity check (received_quantity >= 0 and received_quantity <= quantity)
);

create index if not exists idx_transfers_status_created_at
    on transfers (status, created_at desc);

create table if not exists users (
    id uuid primary key,
    username varchar(60) not null unique,
    full_name varchar(150) not null,
    role varchar(40) not null,
    password_hash text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    constraint chk_users_username_not_blank check (btrim(username) <> ''),
    constraint chk_users_full_name_not_blank check (btrim(full_name) <> ''),
    constraint chk_users_role check (
        role in ('admin', 'supervisor', 'origin_operator', 'destination_operator')
    )
);

create table if not exists user_sessions (
    id uuid primary key,
    user_id uuid not null references users(id),
    token text not null unique,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);

create table if not exists audit_logs (
    id uuid primary key,
    user_id uuid references users(id),
    action varchar(80) not null,
    entity_type varchar(80) not null,
    entity_id varchar(80),
    detail text,
    created_at timestamptz not null default now()
);
