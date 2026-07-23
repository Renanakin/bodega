-- 0013_unique_stock_levels.sql (SQLite mirror)
--
-- BUG 9 (fix 2026-07-23): ver db/migrations/0013_unique_stock_levels.sql
-- para la documentacion completa.
--
-- En SQLite, ALTER TABLE no soporta ADD CONSTRAINT directamente, asi que
-- esta migracion es para referencia historica. En SQLite el constraint
-- UNIQUE se declara en el CREATE TABLE de la migracion 0007.
-- Esta migracion solo se ejecuta contra Postgres; en el runner legacy
-- SQLite (que crea la BD desde cero via migraciones SQL) la unicidad
-- ya esta aplicada via el schema base.

-- No-op en SQLite (la unicidad se aplica via el CREATE TABLE en
-- 0007_stock_levels.sql al crear la BD desde cero). Tests del
-- runner legacy usan la BD con datos limpios, asi que no hay
-- duplicados residuales.
SELECT 1;
