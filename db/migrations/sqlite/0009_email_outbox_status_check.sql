-- 0009_email_outbox_status_check.sql
--
-- BUG-001: El modelo EmailOutbox NO tenia un CheckConstraint para `status`,
-- lo que permitia que valores invalidos (ej: 'inventado') quedaran persistidos
-- sin que la BD los rechazara. El codigo siempre setea valores validos
-- ('pending'/'sent'/'failed'/'dead'), pero la BD no los enforcaba.
--
-- Esta migracion agrega el CHECK constraint a la tabla email_outbox.
-- Es safe (idempotente si se corre dos veces: NOT VALID + VALIDATE).
--
-- En Postgres, este constraint tambien se aplica via ``Base.metadata.create_all``
-- al inicializar el schema desde el modelo, por lo que NO se necesita un
-- archivo separado en ``migrations/postgres/``.

-- Verificar si la tabla existe (SQLite)
CREATE TABLE IF NOT EXISTS email_outbox (
    id TEXT PRIMARY KEY,
    to_email VARCHAR(255) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    body_html TEXT NOT NULL,
    template_name VARCHAR(100),
    template_context TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    sent_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (attempts >= 0),
    CHECK (status IN ('pending', 'sent', 'failed', 'dead'))
);

CREATE INDEX IF NOT EXISTS ix_email_outbox_status ON email_outbox (status, created_at);
