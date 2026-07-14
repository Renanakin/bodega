# Docker

Stack local de desarrollo y pre-produccion:

- `db`: PostgreSQL
- `redis`: cache y mensajeria
- `api`: FastAPI
- `web`: frontend React compilado sobre Nginx
- `nginx`: reverse proxy frontal

## Perfiles disponibles

- base: `docker-compose.yml`
- local: `compose.local.yml`
- staging: `compose.staging.yml`
- production: `compose.production.yml`

## Levantar

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

## Levantar staging

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.staging.yml up --build -d
```

## Levantar production

```bash
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up --build -d
```

## Accesos

- app: `http://localhost`
- api health: `http://localhost/api/v1/health`
- docs api: `http://localhost/docs`

## Notas

- en production no se deben exponer `db` ni `redis`
- el proxy frontal debe ser el unico punto publico
