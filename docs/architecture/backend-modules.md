# Backend modules

## Estado al 17-03-2026

El backend existe como una base FastAPI modular con tres modulos visibles en codigo:

- `warehouses`
- `products`
- `inventory`

Actualmente estos modulos ya tienen separacion por:

- `router.py`
- `schemas.py`
- `service.py`
- `repository.py`

La persistencia actual es en memoria, lo que permite validar reglas de dominio y contratos HTTP sin acoplar todavia el backend a una libreria o motor de base de datos concreto.

## Objetivo de crecimiento inmediato

Cada modulo del MVP ya consolido la siguiente estructura:

- `router.py`: contratos HTTP y traduccion de errores
- `schemas.py`: modelos de entrada y salida
- `service.py`: reglas de negocio
- `repository.py`: acceso a datos y consultas SQL

## Modulos del MVP actual

### `warehouses`
Responsable del catalogo de bodegas.

**Estado actual:** alta, listado y consulta por identificador usando servicio y repositorio en memoria.  
**Objetivo inmediato:** conectar a persistencia real.

### `products`
Responsable del catalogo de productos.

**Estado actual:** alta, listado y consulta por identificador usando servicio y repositorio en memoria.  
**Objetivo inmediato:** conectar a persistencia real.

### `inventory`
Responsable del stock y de los movimientos auditables.

**Estado actual:** consulta de stock, consulta de movimientos y registro transaccional de movimientos en memoria.  
**Objetivo inmediato:** conectar a persistencia real sin romper invariantes.

## Modulos futuros

Los siguientes modulos pertenecen a la vision de producto, pero **no forman parte del MVP actual**:

- `replenishment`
- `transfers`
- `purchasing`
- `chat`
- `notifications`
- `reports`
- `auth`
- `users`

## Regla de arquitectura

Los modulos deben crecer por dominio y no por tipo tecnico global. La logica de negocio no debe desplazarse a routers ni a utilitarios genericos sin dueno de dominio.
