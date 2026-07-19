-- 0007_stock_real.sql
-- Stock por ubicación física (Nivel 2) + stock_min/max en Nivel 1.
-- Fase 2 / Aterrizaje §5.4.

create table if not exists inventario_stock_real (
    id_producto uuid not null
        references products(id) on delete cascade,
    id_ubicacion uuid not null
        references ubicaciones_estanteria(id) on delete cascade,
    cantidad numeric(14, 2) not null default 0,
    updated_at timestamptz not null default now(),
    primary key (id_producto, id_ubicacion),
    constraint chk_inventario_stock_real_non_negative check (cantidad >= 0)
);

-- Máximo en stock_levels (Nivel 1) para alertas de sobrecarga.
alter table stock_levels
    add column if not exists max_quantity numeric(14, 2);

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'chk_stock_max_quantity_non_negative'
    ) then
        alter table stock_levels
            add constraint chk_stock_max_quantity_non_negative
            check (max_quantity is null or max_quantity >= 0);
    end if;
end$$;

create index if not exists idx_inventario_stock_real_ubicacion
    on inventario_stock_real (id_ubicacion);
