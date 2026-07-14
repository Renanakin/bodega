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

create index if not exists idx_user_sessions_token
    on user_sessions (token);

create index if not exists idx_audit_logs_created_at
    on audit_logs (created_at desc);
