-- 0012_single_principal_warehouse.sql (Postgres + SQLite)
--
-- BUG 7 (fix 2026-07-22): el sistema tenia 6 bodegas marcadas como
-- ``warehouse_type='principal'`` (la correcta + 5 heredadas de seeds y
-- tests). Esto ensuciaba el Consolidador de Quiebres y cualquier logica
-- que asume UNA sola principal activa. Esta migracion reasigna las
-- 5 bodegas "principal" sobrantes a 'auxiliar'.
--
-- Reglas aplicadas:
-- - Solo se tocan bodegas que actualmente son 'principal' Y NO son la
--   principal canonica 'BOD-PPAL-E52D7888' (id a96d195d-58c2-4a5c-97d8-df333f44dab1).
--   Si en el futuro se designa una nueva principal, esta migracion no
--   la va a tocar (es idempotente y conservadora).
-- - El CHECK constraint ``ck_warehouses_parent_warehouse_required_for_box``
--   exige que ``auxiliar`` tenga ``parent_warehouse_id IS NULL``. Las 5
--   bodegas reasignadas ya cumplen esto (todas tienen parent NULL).
-- - updated_at se actualiza para reflejar la operacion.
--
-- Idempotente: si las 5 bodegas ya son 'auxiliar' (ej. BD de un env
-- que ya corrio este fix), el UPDATE no afecta ninguna fila.
--
-- Espejo SQLite: la migracion es 100% SQL portable, sirve en ambos backends.

BEGIN;

UPDATE warehouses
SET warehouse_type = 'auxiliar',
    updated_at = NOW()
WHERE warehouse_type = 'principal'
  AND code <> 'BOD-PPAL-E52D7888';

COMMIT;
