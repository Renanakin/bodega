# API

Backend del sistema multi-bodega construido con FastAPI.

## Objetivo del area

Implementar el backend del sistema con modulos de dominio claros, reglas de negocio centralizadas y operaciones de inventario seguras.

## Estado al 17-03-2026

Actualmente existe un MVP funcional con:

- configuracion base en `app/core/config.py`
- aplicacion FastAPI en `app/main.py`
- router principal en `app/api/router.py`
- healthcheck en `app/api/routes/health.py`
- modulos `warehouses`, `products` e `inventory`
- manejo centralizado de errores de dominio
- persistencia en memoria por medio de `app/db/session.py`
- pruebas backend en `tests/test_api.py`

Los endpoints ya ejecutan reglas reales del dominio sobre almacenamiento en memoria. La siguiente etapa es conectar estos repositorios a persistencia real.

## Estructura

```text
apps/api/
  app/
    api/
      routes/
      router.py
    core/
      config.py
    modules/
      inventory/
      products/
      warehouses/
      README.md
    main.py
  Dockerfile
  README.md
  requirements.txt
```

## Endpoints actuales

- `GET /api/v1/health`
- `GET /api/v1/warehouses`
- `POST /api/v1/warehouses`
- `GET /api/v1/warehouses/{warehouse_id}`
- `GET /api/v1/products`
- `POST /api/v1/products`
- `GET /api/v1/products/{product_id}`
- `GET /api/v1/inventory/stock`
- `GET /api/v1/inventory/movements`
- `POST /api/v1/inventory/movements`
- `GET /api/v1/inventory/summary`

## Estado del MVP

### Alcance

- alta, listado y consulta de bodegas
- alta, listado y consulta de productos
- consulta de stock actual
- registro de movimientos de inventario
- historial de movimientos
- validacion de salidas sin stock

### Regla principal

El stock nunca debe modificarse desde una ruta HTTP. Toda alteracion de inventario debe ocurrir en servicios de dominio y bajo control transaccional.

## Estructura objetivo por modulo

Cada modulo del MVP debe evolucionar hacia:

- `router.py`
- `schemas.py`
- `service.py`
- `repository.py`

## Dependencias actuales

- `fastapi`
- `uvicorn[standard]`
- `pydantic-settings`

## Pendientes inmediatos

1. conectar repositorios a persistencia real
2. mantener las mismas reglas de dominio en esa transicion
3. ampliar cobertura de pruebas en consultas filtradas y duplicados
