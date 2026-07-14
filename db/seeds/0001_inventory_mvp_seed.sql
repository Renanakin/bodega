-- Minimal seed set for local verification of the inventory MVP.

insert into warehouses (
    id,
    code,
    name,
    warehouse_type,
    is_active
) values (
    '11111111-1111-1111-1111-111111111111',
    'CENTRAL',
    'Bodega Central',
    'central',
    true
)
on conflict (code) do nothing;

insert into products (
    id,
    sku,
    name,
    unit,
    is_active
) values (
    '22222222-2222-2222-2222-222222222222',
    'SKU-001',
    'Producto Inicial',
    'unit',
    true
)
on conflict (sku) do nothing;

insert into inventory_movements (
    id,
    warehouse_id,
    product_id,
    movement_type,
    quantity,
    reference_type,
    reference_id,
    notes
) values (
    '33333333-3333-3333-3333-333333333333',
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
    'in',
    10.00,
    'seed',
    'seed-in-001',
    'Carga inicial para validacion local'
)
on conflict (id) do nothing;

insert into stock_levels (
    id,
    warehouse_id,
    product_id,
    quantity,
    min_quantity
) values (
    '44444444-4444-4444-4444-444444444444',
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
    10.00,
    2.00
)
on conflict (warehouse_id, product_id) do nothing;
