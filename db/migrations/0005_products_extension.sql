-- 0005_products_extension.sql
-- Extensión de products: codigo_barras, id_categoria, precio_costo, precio_venta.
-- Sub-recurso opt-in: detalles_neumaticos (1:1 con products).

alter table products
    add column if not exists codigo_barras varchar(100);

alter table products
    add column if not exists id_categoria uuid;

alter table products
    add column if not exists precio_costo numeric(14, 2) not null default 0;

alter table products
    add column if not exists precio_venta numeric(14, 2) not null default 0;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'uq_products_codigo_barras'
    ) then
        alter table products
            add constraint uq_products_codigo_barras unique (codigo_barras);
    end if;
end$$;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'fk_products_categoria'
    ) then
        alter table products
            add constraint fk_products_categoria
            foreign key (id_categoria) references categories(id) on delete set null;
    end if;
end$$;

create table if not exists detalles_neumaticos (
    producto_id uuid primary key
        references products(id) on delete cascade,
    ancho integer not null,
    perfil integer not null,
    aro integer not null,
    indice_carga integer,
    indice_velocidad varchar(5),
    dot varchar(20),
    constraint chk_detalles_neumaticos_ancho_positive check (ancho > 0),
    constraint chk_detalles_neumaticos_perfil_positive check (perfil > 0),
    constraint chk_detalles_neumaticos_aro_positive check (aro > 0)
);

create index if not exists idx_products_codigo_barras
    on products (codigo_barras);

create index if not exists idx_products_id_categoria
    on products (id_categoria);
