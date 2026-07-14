# Migrations

Migraciones SQL versionadas del sistema.

## Regla general

Todo cambio relevante de esquema debe entrar por esta carpeta y ser revisable.

## Estado al 17-03-2026

Ya existe una migracion formal del MVP en `0001_inventory_mvp.sql`. El archivo `db/schema/initial-domain.sql` se mantiene como referencia legible del dominio.

## Lineamientos para la primera migracion del MVP

La primera migracion cubre:

- `warehouses`
- `products`
- `inventory_movements`
- `stock_levels`
- restricciones de unicidad y llaves foraneas necesarias

## Convencion sugerida

Usar nombres ordenables y descriptivos, por ejemplo:

- `0001_inventory_mvp.sql`
- `0002_add_stock_indexes.sql`

Si en el futuro se adopta una herramienta formal de migraciones, la nomenclatura puede ajustarse, pero la trazabilidad debe mantenerse.
