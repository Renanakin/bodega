-- 0006_ubicaciones.sql
-- Ubicaciones físicas de estantería: pasillo / estantería / altura por bodega.
-- Fase 2 / Aterrizaje §5.4.

create table if not exists ubicaciones_estanteria (
    id uuid primary key,
    id_bodega uuid not null
        references warehouses(id) on delete cascade,
    pasillo integer not null,
    estanteria integer not null,
    altura integer not null,
    descripcion varchar(200),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_ubicaciones_bodega_pasillo_estanteria_altura
        unique (id_bodega, pasillo, estanteria, altura),
    constraint chk_ubicaciones_pasillo_positive check (pasillo > 0),
    constraint chk_ubicaciones_estanteria_positive check (estanteria > 0),
    constraint chk_ubicaciones_altura_positive check (altura > 0)
);

create index if not exists idx_ubicaciones_bodega
    on ubicaciones_estanteria (id_bodega);

create index if not exists idx_ubicaciones_bodega_active
    on ubicaciones_estanteria (id_bodega, is_active);
