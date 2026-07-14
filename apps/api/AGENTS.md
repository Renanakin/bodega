# AGENTS

## Folder

`apps/api`

## Objetivo

Construir y mantener el backend FastAPI del sistema multi-bodega.

## Skills del area

- modelado de dominio logistico
- APIs REST
- validacion de esquemas
- seguridad backend
- transacciones y consistencia de inventario
- modularizacion por dominio

## Agente ideal

- backend engineer
- API designer
- especialista en concurrencia y reglas de negocio

## Plugins recomendados

- Python
- Pylance
- Ruff
- Docker

## Reglas

- el stock nunca se modifica fuera de servicios de dominio
- toda operacion critica debe ser transaccional
- los modulos deben crecer por dominio y no por tipo tecnico
- las rutas son livianas; la logica vive en servicios

