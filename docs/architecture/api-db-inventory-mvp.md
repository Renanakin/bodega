# Diseno tecnico del MVP API/DB de inventario

**Fecha:** 17-03-2026  
**Estado:** implementacion en progreso

## Objetivo tecnico

Construir la primera version real del backend y de la base de datos para inventario multi-bodega manteniendo reglas de dominio claras, trazabilidad y una base extensible.

## Estado actual

- la API ya implementa el flujo del MVP con persistencia en memoria
- la base de datos ya tiene esquema de referencia, migracion `0001_inventory_mvp.sql` y semilla minima
- aun falta sustituir los repositorios en memoria por repositorios respaldados por BD real

## Carpetas involucradas

- `apps/api`
- `db`
- `docs` (solo para documentacion)

## Principios

- las rutas son livianas
- la logica de negocio vive en servicios
- el acceso a datos vive en repositorios
- el stock nunca se modifica fuera del servicio de inventario
- toda operacion critica de inventario debe ser transaccional
- se prefiere una base pequena y clara antes que capas innecesarias

## Estructura propuesta para `apps/api`

```text
app/
  api/
    routes/
    router.py
  core/
    config.py
    errors.py
  db/
    session.py
  modules/
    warehouses/
      router.py
      schemas.py
      service.py
      repository.py
    products/
      router.py
      schemas.py
      service.py
      repository.py
    inventory/
      router.py
      schemas.py
      service.py
      repository.py
```

## Contratos API del MVP

Base: `/api/v1`

### Warehouses
- `GET /warehouses`
- `POST /warehouses`
- `GET /warehouses/{warehouse_id}` (recomendado para el mismo incremento)

### Products
- `GET /products`
- `POST /products`
- `GET /products/{product_id}` (recomendado para el mismo incremento)

### Inventory
- `GET /inventory/stock`
- `GET /inventory/movements`
- `POST /inventory/movements`
- `GET /inventory/summary`

## Modelo de datos del MVP

### `warehouses`
- `id`
- `code` unico
- `name`
- `warehouse_type`
- `is_active`
- `created_at`
- `updated_at`

### `products`
- `id`
- `sku` unico
- `name`
- `unit`
- `is_active`
- `created_at`
- `updated_at`

### `inventory_movements`
Ledger auditable de inventario.

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

Tipos permitidos en el MVP:
- `in`
- `out`
- `adjustment_in`
- `adjustment_out`

### `stock_levels`
Proyeccion del saldo actual por bodega y producto.

Campos base:
- `id`
- `warehouse_id`
- `product_id`
- `quantity`
- `min_quantity`
- `updated_at`

Restriccion clave:
- unico por `(warehouse_id, product_id)`

## Flujo transaccional para registrar un movimiento

1. validar que existan bodega y producto
2. validar el tipo de movimiento y la cantidad positiva
3. leer o bloquear el stock actual de la combinacion
4. calcular el nuevo saldo
5. rechazar salidas con stock insuficiente
6. insertar el movimiento en `inventory_movements`
7. actualizar o crear la fila correspondiente en `stock_levels`
8. confirmar la transaccion

## Errores de dominio esperados

- `warehouse_not_found` -> HTTP 404
- `product_not_found` -> HTTP 404
- `duplicate_warehouse_code` -> HTTP 409
- `duplicate_sku` -> HTTP 409
- `insufficient_stock` -> HTTP 409
- payload invalido o tipo de movimiento invalido -> HTTP 422

## Orden de implementacion recomendado

### Fase 1: API
1. `schemas.py`
2. `repository.py`
3. `service.py`
4. integracion de routers reales
5. errores de dominio comunes
6. pruebas enfocadas

### Fase 2: DB
1. cierre del modelo SQL del MVP
2. migracion inicial versionada
3. semillas minimas si aportan validacion local
4. alineacion entre esquema y contratos API

### Fase 3: verificacion
1. pruebas backend
2. validacion de migraciones y restricciones
3. smoke tests de endpoints
4. confirmacion de que el stock solo cambia via movimientos
