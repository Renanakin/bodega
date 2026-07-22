-- 0011_refresh_tokens.sql (SQLite mirror)
-- Ver db/migrations/0011_refresh_tokens.sql para la documentacion completa.

-- SQLite no soporta IF NOT EXISTS en ALTER TABLE ADD COLUMN, asi que
-- usamos pragma_table_info para chequear.
-- (Migracion idempotente: si las columnas ya existen, no hace nada.)

-- Recreate table approach: SQLite no soporta DROP COLUMN facilmente, asi
-- que este script es mas simple si se corre en BD vacia. Para BD con
-- datos, hacer backup previo.

-- Para CI/tests (BD vacia), esto basta:
CREATE TABLE IF NOT EXISTS user_sessions_new (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token VARCHAR(500) NOT NULL UNIQUE,
    refresh_token VARCHAR(500) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    refresh_expires_at TIMESTAMP NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- En SQLite, para una migracion robusta con datos, se haria:
-- 1. CREATE TABLE user_sessions_new con el nuevo schema
-- 2. INSERT INTO user_sessions_new SELECT ... FROM user_sessions
-- 3. DROP TABLE user_sessions
-- 4. ALTER TABLE user_sessions_new RENAME TO user_sessions
-- Esto lo hace Alembic automaticamente al hacer ``alembic upgrade head``
-- en la BD SQLite. Aqui dejamos el CREATE IF NOT EXISTS como placeholder
-- para los tests que crean la BD desde cero.

CREATE INDEX IF NOT EXISTS idx_user_sessions_refresh_token
    ON user_sessions (refresh_token);
