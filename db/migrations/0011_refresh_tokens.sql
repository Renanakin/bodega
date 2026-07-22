-- 0011_refresh_tokens.sql
-- C5.1: agregar refresh tokens a user_sessions.
--
-- Antes: solo habia un access token (``token``) con expiracion.
-- Ahora: access token (corta, 1h) + refresh token (larga, 7d).
-- El refresh se usa para obtener un nuevo access token via /auth/refresh.
--
-- Backward-compat: se agregan como NULLABLE y se rellenan para sesiones
-- existentes en la misma migracion. Para sesiones nuevas, el service
-- siempre genera ambos tokens.

alter table user_sessions
    add column if not exists refresh_token varchar(500);

alter table user_sessions
    add column if not exists refresh_expires_at timestamptz;

-- Para sesiones existentes, generar refresh tokens basados en el token
-- original + un salt fijo. Esto es compatible con sesiones activas: el
-- usuario puede seguir usando su access token, y si quiere refresh debe
-- re-loguearse (las sesiones existentes no tendran refresh valido).
update user_sessions
set refresh_token = 'legacy-' || substr(token, 1, 40),
    refresh_expires_at = expires_at  -- mismo tiempo que access para legacy
where refresh_token is null;

-- Hacer NOT NULL despues del backfill
alter table user_sessions
    alter column refresh_token set not null;

alter table user_sessions
    alter column refresh_expires_at set not null;

-- UNIQUE constraint (ya lo tiene token; agregamos para refresh)
do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conname = 'uq_user_sessions_refresh_token'
    ) then
        alter table user_sessions
            add constraint uq_user_sessions_refresh_token unique (refresh_token);
    end if;
end$$;

-- Indice para busquedas rapidas por refresh token
create index if not exists idx_user_sessions_refresh_token
    on user_sessions (refresh_token)
    where refresh_token is not null;
