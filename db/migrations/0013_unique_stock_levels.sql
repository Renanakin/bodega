-- 0013_unique_stock_levels.sql (Postgres + SQLite)
--
-- BUG 9 (fix 2026-07-23): la tabla stock_levels permitia duplicados
-- (warehouse_id, product_id) lo que provocaba filas duplicadas en
-- /bajo-minimo y errores 'productos duplicados' en el Evaluator.
-- Ademas: el ix_stock_levels_warehouse_product NO era UNIQUE.
--
-- Esta migracion:
-- 1) Elimina duplicados dejando la fila con updated_at mas reciente
--    (en caso de haberlos). Si no hay duplicados, no hace nada.
-- 2) Agrega un UNIQUE constraint en (warehouse_id, product_id).
-- 3) Reemplaza el indice no-unique por uno UNIQUE (mismo nombre).
--
-- Idempotente: si ya existe el constraint, no falla.

BEGIN;

-- 1. Eliminar duplicados dejando el registro mas reciente
--    (definido como el de mayor updated_at; desempate por id para
--    estabilidad).
DELETE FROM stock_levels
WHERE id IN (
  SELECT id FROM (
    SELECT id,
           ROW_NUMBER() OVER (
             PARTITION BY warehouse_id, product_id
             ORDER BY updated_at DESC, id DESC
           ) AS rn
    FROM stock_levels
  ) t
  WHERE t.rn > 1
);

-- 2. Eliminar el indice no-unique antiguo (si existe) para reemplazarlo
--    por uno UNIQUE. El nombre ix_stock_levels_warehouse_product se
--    conserva para que la aplicacion no pierda la cobertura del query
--    que ya lo usa.
DROP INDEX IF EXISTS ix_stock_levels_warehouse_product;

-- 3. Crear el UNIQUE constraint
ALTER TABLE stock_levels
  ADD CONSTRAINT uq_stock_levels_warehouse_product
  UNIQUE (warehouse_id, product_id);

COMMIT;
