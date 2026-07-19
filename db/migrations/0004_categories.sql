-- 0004_categories.sql
-- Categorías de productos con jerarquía opcional (parent_id self-FK).
-- Aterrizaje §3.1 / Fase 2.

create table if not exists categories (
    id uuid primary key,
    nombre varchar(100) not null unique,
    descripcion varchar(500),
    parent_id uuid,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint fk_categories_parent foreign key (parent_id) references categories(id) on delete set null,
    constraint chk_categories_nombre_not_blank check (btrim(nombre) <> '')
);

create unique index if not exists uq_categories_nombre_normalized
    on categories (lower(btrim(nombre)));

create index if not exists idx_categories_parent_id on categories (parent_id);
