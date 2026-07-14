# Bodegaje

Monorepo del sistema de inventario multi-bodega, organizado como workspace multi-raiz para separar frontend, backend, base de datos, infraestructura y documentacion.

## Estructura

- `docs/`: documentacion funcional, tecnica y operativa
- `apps/api/`: backend FastAPI
- `apps/web/`: frontend React + Vite
- `db/`: esquema, semillas y diagramas
- `infra/`: Docker, Nginx y despliegue local
- `.vscode/`: configuracion compartida del workspace

## Estado actual

- `apps/web`: panel operacional React con dashboard, inventario, transferencias, reposicion, slotting, chat y reportes
- `apps/api`: backend FastAPI en desarrollo por otro agente
- `db`: esquema y migraciones en desarrollo por otro agente
- `infra`: perfiles `local`, `staging` y `production` con Nginx y Docker Compose
- `docs`: documentacion funcional, tecnica y operativa del proyecto

## Restriccion actual de trabajo

- `db` y `apps/api` tienen trabajo concurrente de otro agente
- los cambios recientes se concentran en `apps/web` e `infra`

## Frontend

El frontend ya incluye:

- layout principal y navegacion lateral
- formularios operativos
- drawers, filtros, empty states y feedback visual
- toasts y estado global de carga
- integracion preparada hacia `/api/v1`
- build validada dentro del contenedor Docker

## Infraestructura

La infraestructura ya incluye:

- Compose base comun
- perfil `local` con todos los puertos expuestos
- perfil `staging`
- perfil `production` con `nginx` como unica entrada publica
- scripts PowerShell de arranque y parada
- runbook de despliegue y rollback

### Levantar local

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.local.yml up --build
```

### Entradas utiles

- app: `http://localhost`
- api: `http://localhost/api/v1/health`
- docs api: `http://localhost/docs`

## Workspace

Abrir [bodegaje.code-workspace](/C:/Users/HackBook/Documents/desarrollos/bodegaje/bodegaje.code-workspace) en VS Code para trabajar el proyecto con configuracion multi-raiz.
