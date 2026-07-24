# Bodegaje

[![E2E](https://img.shields.io/badge/E2E-5%2F5%20passing-brightgreen)](tests/e2e/)
[![Version](https://img.shields.io/badge/version-v1.0.0-blue)](docs/operations/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](apps/api/)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20React%20%2B%20Postgres%2017-blueviolet)](#stack)

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

## Testing E2E

Bateria de tests end-to-end en `tests/e2e/` que valida el sistema en vivo
contra http://localhost:8080. Orquestador: `tests/e2e/run_all.py`.

### Tests incluidos

| Test | Tiempo | Que valida |
|------|--------|------------|
| `replenishment_bug12` | ~5s | Cobertura de solicitudes: estados activos cubren SKUs bajo minimo |
| `oc_correo_flujo`     | ~13s | **Modulo OC por correo**: happy path / descuadre / rechazo (3 escenarios) |
| `backup_restore`      | ~6s | Backup diario + restore a BD temporal + integridad |
| `bug11_layout`        | ~5s | Layout del bloque de cubiertos en Replenishment (Playwright) |
| `manual_screens`      | ~40s | Captura de pantallas del manual de usuario (Playwright) |

### Como correr

**Con PowerShell (recomendado en Windows):**

```powershell
# Bateria completa (~70s, 5 tests)
.\test-e2e.ps1

# Bateria sin Playwright (~25s, 3 tests, util antes de commit)
.\test-e2e.ps1 quick

# Solo el modulo de OC por correo
.\test-e2e.ps1 oc

# Solo backup + restore
.\test-e2e.ps1 backup

# Ver aliases disponibles
Get-Help .\test-e2e.ps1
```

**Con Make (git-bash / WSL):**

```bash
make e2e                # Bateria completa (~70s)
make e2e-quick           # Sin Playwright (~25s)
make e2e-oc              # Solo OC
make e2e-backup          # Solo backup
make help                # Ver todos los targets
```

**Directo con Python:**

```bash
python tests/e2e/run_all.py                    # Bateria completa
python tests/e2e/run_all.py --skip bug11_layout manual_screens  # Sin Playwright
python tests/e2e/run_all.py --only oc_correo_flujo             # Solo OC
python tests/e2e/run_all.py --cleanup           # Tambien rechaza OCs viejas
python tests/e2e/run_all.py --verbose           # Output completo
```

### Exit codes

- `0` = todos los tests pasaron
- `1` = al menos un test fallo
- `2` = error del orquestador (script no existe, sin tests seleccionados, etc)
- `124` = timeout del test
- `130` = interrumpido por el usuario (Ctrl+C)

### Requisitos

- Python 3.10+ con `pip install requests`
- Para los tests de Playwright: `pip install playwright && playwright install`
- Sistema levantado: `docker compose -f infra/docker/docker-compose.yml up -d`

### Reportes

- Reporte detallado del modulo OC: [`tests/e2e/REPORTE_OC_CORREO.md`](tests/e2e/REPORTE_OC_CORREO.md)
- Manual de usuario: [`docs/manual_usuario.md`](docs/manual_usuario.md)
- Cheatsheet de operaciones: [`docs/cheatsheet.md`](docs/cheatsheet.md)
