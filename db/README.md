# Database

Repositorio de esquema, migraciones, semillas y criterios de integridad del sistema multi-bodega.

## Estructura

- `schema/`: definiciones del modelo relacional y documentacion del dominio
- `migrations/`: migraciones SQL versionadas
- `seeds/`: datos base para ambientes locales y de prueba

## Estado al 17-03-2026

Actualmente existe:

- un esquema inicial en `schema/initial-domain.sql`
- una migracion formal en `migrations/0001_inventory_mvp.sql`
- una seed minima en `seeds/0001_inventory_mvp_seed.sql`
- carpetas preparadas para migraciones y semillas

## Estado del incremento actual

- consolidar tablas de `warehouses`, `products`, `inventory_movements` y `stock_levels`
- versionar el esquema desde `migrations/`
- mantener integridad referencial y unicidad de claves de negocio
- documentar semillas minimas si hacen falta para validacion local

## Reglas del area

- no agregar tablas sin justificar su lugar en el dominio
- todo cambio de esquema debe ser versionable
- evitar duplicacion de datos de referencia
- toda restriccion critica de inventario debe quedar explicita en el esquema
