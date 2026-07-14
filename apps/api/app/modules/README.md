# Modules

Los modulos del backend crecen por dominio y no por tipo tecnico global.

## Estado actual

### `warehouses`
- existen `router.py`, `schemas.py`, `service.py` y `repository.py`
- ya soporta alta, listado y consulta por identificador
- hoy persiste en memoria y luego debe conectarse a BD real

### `products`
- existen `router.py`, `schemas.py`, `service.py` y `repository.py`
- ya soporta alta, listado y consulta por identificador
- hoy persiste en memoria y luego debe conectarse a BD real

### `inventory`
- existen `router.py`, `schemas.py`, `service.py` y `repository.py`
- ya soporta consulta de stock, historial y registro de movimientos
- hoy persiste en memoria y luego debe conectarse a BD real

## Estructura objetivo por modulo

Cada modulo del MVP contiene:

- `router.py`
- `schemas.py`
- `service.py`
- `repository.py`

## Modulos futuros

Los siguientes dominios pertenecen a la vision del sistema, pero no deben presentarse como implementados mientras no exista codigo y validacion asociados:

- `replenishment`
- `transfers`
- `purchasing`
- `chat`
- `notifications`
- `reports`
- `auth`
- `users`
