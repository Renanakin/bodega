# Infra

Infraestructura local y de despliegue.

## Contenido

- `docker/`: entorno local con PostgreSQL, Redis, API, frontend y Nginx
- `scripts/`: arranque y parada de perfiles operativos
- `production/`: base documental de salida productiva
- `operations/`: runbooks y procedimientos
- futuro:
  `monitoring/`

## Perfiles

- `docker-compose.yml`: base comun
- `compose.local.yml`: exposicion completa para desarrollo
- `compose.staging.yml`: exposicion reducida para pre-produccion
- `compose.production.yml`: perfil de produccion con exposicion minima

## Scripts

- `scripts/start-local.ps1`
- `scripts/start-staging.ps1`
- `scripts/start-production.ps1`
- `scripts/stop.ps1`

## Cierre de esta etapa

`infra` queda preparada para:

- levantar local
- levantar staging
- tener base de produccion
- usar Nginx como punto unico de entrada
- dejar documentado despliegue y rollback

