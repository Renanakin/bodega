# Workspace Agents

Este archivo define la distribucion de responsabilidades del workspace multi-raiz.

## Raices del workspace

- `docs`: producto, arquitectura y operacion
- `apps/api`: backend FastAPI
- `apps/web`: frontend React + Vite
- `db`: modelo relacional, migraciones y semillas
- `infra`: Docker, Nginx y despliegue

## Regla general

Cada raiz tiene su propio `AGENTS.md` con:

- objetivo de la carpeta
- skill operativa esperada
- tipo de cambios permitidos
- plugins o extensiones recomendadas

La idea es que un agente o desarrollador entre a una raiz y encuentre ahi mismo el contexto de trabajo.

## Skills activas por prioridad actual

### apps/web

- formularios operativos
- validacion visual
- estados globales de UI
- integracion frontend-api
- notificaciones y feedback
- base para tiempo real

### infra

- perfiles local, staging y production
- hardening de proxy
- variables por ambiente
- healthchecks y restart policy
- despliegue y rollback
- monitoreo operativo

## Restriccion actual

- `db` y `apps/api` estan siendo trabajadas por otro agente
- los cambios actuales deben concentrarse en `apps/web` e `infra`
