-- 0014_performance_indices.sql (Postgres + SQLite)
--
-- P1 del roadmap Big-O (docs/informe_escalabilidad_big_o.md):
-- indices que faltan para queries especificas. Con estos indices
-- las queries criticas pasan de O(n) seq scan a O(log n) index scan.
--
-- Cada indice esta documentado con:
-- - Query objetivo (endpoint que lo usa)
-- - Costo sin indice: O(n) seq scan
-- - Costo con indice: O(log n) index scan
-- - Idempotencia: usa IF NOT EXISTS
--
-- Importante: solo lectura/escritura. NO modifica datos.

BEGIN;

-- 1. audit_logs: busqueda por user_id (actor) con filtro de fecha
--    Query: GET /api/v1/audit?user_id=X&from=YYYY-MM-DD
--    Sin indice: seq scan sobre 1M filas = ~500ms
--    Con indice: O(log n) por fecha + user_id = <10ms
--    Nota: el campo se llama user_id en el schema (no actor_id).
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_created_at
    ON audit_logs (user_id, created_at DESC);

-- 2. stock_levels: bajo minimo por bodega (partial index)
--    Query: GET /api/v1/solicitudes/bajo-minimo
--    El query filtra: min_quantity > 0 AND quantity <= min_quantity
--    Partial index: solo filas donde min_quantity > 0 (subset pequeno)
--    esperado: ~5-10% del total de stock_levels
--    Sin indice: seq scan de toda la tabla
--    Con indice: O(log n) sobre el subset
CREATE INDEX IF NOT EXISTS idx_stock_levels_bajo_minimo
    ON stock_levels (warehouse_id, quantity)
    WHERE min_quantity > 0;

-- 3. solicitudes_recarga: codigo unico (LIKE prefix-friendly)
--    Query: busqueda por codigo (UI muestra SOL-2026..., etc)
--    LIKE 'prefix%' usa btree si el indice es UNIQUE
--    Ademas garantiza que no se generen codigos duplicados (defensa en profundidad)
CREATE UNIQUE INDEX IF NOT EXISTS uq_solicitudes_codigo
    ON solicitudes_recarga (codigo);

-- 4. ordenes_compra: codigo unico
--    Mismo caso que solicitudes. La UI busca por codigo.
--    Ademas previene duplicados por bug en el generador.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ordenes_codigo
    ON ordenes_compra (codigo);

-- 5. inventory_movements: busqueda por reference (OC/factura/solicitud)
--    Query: cuadre OC vs factura (test_oc_correo_flujo.py:cuadrar_oc)
--    Partial index: solo movimientos con reference_id (subset)
--    Sin indice: seq scan de toda la tabla de movimientos
--    Con indice: O(log n) por (reference_type, reference_id)
CREATE INDEX IF NOT EXISTS idx_inventory_movements_reference
    ON inventory_movements (reference_type, reference_id)
    WHERE reference_id IS NOT NULL;

-- 6. email_outbox: dedup por (to_email, subject, sent_at IS NULL) - no es UNIQUE
--    porque la tabla no tiene message_id. En su lugar, mejoramos la query
--    de "pendientes para enviar" que es la hot path del worker.
--    (Si en el futuro se agrega message_id, se puede reemplazar por UNIQUE.)
CREATE INDEX IF NOT EXISTS idx_email_outbox_pending_worker
    ON email_outbox (status, created_at)
    WHERE status IN ('pending', 'failed');

-- 7. user_sessions: busqueda por user_id (logout masivo, admin)
--    Query: GET /api/v1/admin/users/{id}/sessions
--    Sin indice: seq scan
--    Con indice: O(log n) por user_id
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id
    ON user_sessions (user_id);

-- 8. notificaciones: busqueda por destinatario y leida/no leida
--    Query: GET /api/v1/notificaciones?leida=false&limit=200
--    Sin indice: seq scan
--    Con indice: O(log n) por (user_id, leida)
--    Nota: la tabla se llama `notificaciones` (no `notifications`) y
--    el FK al usuario es `user_id` (no `recipient_id`). El campo es
--    `leida` (femenino).
CREATE INDEX IF NOT EXISTS idx_notificaciones_user_leida
    ON notificaciones (user_id, leida, created_at DESC);

COMMIT;

-- ANALYZE: actualizar estadisticas para que el planner use los nuevos indices.
-- Sin esto, los indices existen pero Postgres puede elegir seq scan pensando
-- que la tabla es pequenha. ANALYZE es la senal que el planner necesita.
ANALYZE audit_logs;
ANALYZE stock_levels;
ANALYZE solicitudes_recarga;
ANALYZE ordenes_compra;
ANALYZE inventory_movements;
ANALYZE email_outbox;
ANALYZE user_sessions;
ANALYZE notificaciones;
