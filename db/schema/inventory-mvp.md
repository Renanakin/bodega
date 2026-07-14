# Modelo de datos del MVP de inventario

**Fecha:** 17-03-2026  
**Estado:** implementado a nivel de esquema y migracion

## Objetivo

Definir el modelo relacional minimo necesario para soportar catalogos, stock actual y movimientos auditables.

## Tablas del MVP

### `warehouses`

Proposito: representar bodegas fisicas o logicas del sistema.

Campos base:
- `id`
- `code` unico
- `name`
- `warehouse_type`
- `is_active`
- `created_at`
- `updated_at`

### `products`

Proposito: representar productos inventariables.

Campos base:
- `id`
- `sku` unico
- `name`
- `unit`
- `is_active`
- `created_at`
- `updated_at`

### `inventory_movements`

Proposito: registrar cada cambio de stock con trazabilidad.

Campos base:
- `id`
- `warehouse_id`
- `product_id`
- `movement_type`
- `quantity`
- `reference_type`
- `reference_id`
- `notes`
- `created_at`

Tipos de movimiento del MVP:
- `in`
- `out`
- `adjustment_in`
- `adjustment_out`

### `stock_levels`

Proposito: mantener el saldo actual por bodega y producto para lectura rapida.

Campos base:
- `id`
- `warehouse_id`
- `product_id`
- `quantity`
- `min_quantity`
- `updated_at`

## Restricciones minimas

- `warehouses.code` unico
- `products.sku` unico
- `stock_levels` unico por `(warehouse_id, product_id)`
- llaves foraneas de stock y movimientos hacia bodegas y productos

## Invariantes del dominio

1. El stock actual es una proyeccion del dominio, no una fuente editable por separado.
2. Todo cambio de stock debe quedar respaldado por un movimiento.
3. Las salidas no deben dejar saldo negativo.
4. La tabla de movimientos es la base de la trazabilidad.

## Relacion con el estado actual

`initial-domain.sql` y `migrations/0001_inventory_mvp.sql` ya contienen el modelo del MVP. El siguiente paso es conectar este esquema a la API para reemplazar los repositorios en memoria.
