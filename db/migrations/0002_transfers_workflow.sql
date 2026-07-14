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
