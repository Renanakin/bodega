# Fase 1 — PostgreSQL real (ADR-0001)

> **Estado:** Implementada ✅
> **ADR rector:** [`adr-0001-postgres-strategy.md`](../adr/adr-0001-postgres-strategy.md)
> **Fecha:** 2026-07-14

## Resumen ejecutivo

Esta fase adopta **SQLAlchemy 2.0 async + asyncpg + Alembic** como stack de
persistencia oficial, dejando SQLite únicamente como backend de tests rápidos
sin concurrencia. La interface `Database` se introduce como contrato abstracto
para que las próximas generaciones de repositorios (Fase 3+) sean portables
entre Postgres y SQLite sin cambios. Los routers existentes siguen usando el
SQLite sync legacy (`app.state.db` con `sqlite3` stdlib) por compatibilidad
con los tests en memoria — la migración completa a async se delega a Fase 3+,
manteniendo esta fase **no rompedora** sobre el contrato HTTP y los tests
unitarios.

## Cambios realizados

### Archivos creados

| Archivo | Propósito |
|---|---|
| `apps/api/app/db/seed.py` | Seed idempotente vía SQLAlchemy (reemplazo de `db/seeds/0001_inventory_mvp_seed.sql`). |
| `apps/api/tests/test_api_integration.py` | 11 tests con `@pytest.mark.integration`: 6 contra Postgres real (testcontainers), 4 sobre la factory, 1 sobre AsyncSQLite. |
| `infra/docker/compose.local.dev.yml` | Override de compose con la API hablando a Postgres real + entrypoint que corre `alembic upgrade head` al arrancar. |
| `docs/fases/fase-1-postgres-real.md` | Este documento. |

### Archivos modificados

| Archivo | Cambio |
|---|---|
| `apps/api/app/db/session.py` | +Sección 1.5: interface `Database` (ABC), `_AsyncSQLADatabase` (base), `PostgresDatabase`, `AsyncSQLiteDatabase`, `create_database_from_url(url)`, helper `_redact_url()`. Las Secciones 1 y 2 previas quedan intactas. |
| `apps/api/app/core/config.py` | `database_url` ahora es opcional (`str \| None = None`); nuevo campo `db_backend` auto-detectado por `model_validator`; validador que acepta schemes postgres + sqlite. |
| `apps/api/app/main.py` | Nueva función `_resolve_backend()` decide entre `sqlite_legacy` / `sqlite` / `postgres` y loguea el backend activo (R8). Para Postgres, también inicializa el engine async vía `get_engine()`. |
| `apps/api/alembic/env.py` | Skip del `set_main_option` cuando `settings.database_url` es `None` (fix del bug "option values must be strings" en contexts sin `.env`). |
| `apps/api/requirements.txt` | Comentarios de trazabilidad ADR-0001; bump a `testcontainers[postgresql]==4.8.0`, `aiosqlite==0.20.0`. Versiones finales fixadas al snapshot de Python 3.14 validado en CI. |

## Decisiones de implementación (resumen ADR-0001)

Las decisiones macro del ADR se respetan tal cual; lo relevante para esta
fase es cómo se aterrizaron en código:

1. **Stack:** `sqlalchemy[asyncio]==2.0.36` + `asyncpg==0.30.0` + `alembic==1.14.0`
   (versiones pinneadas — bumps requieren correr la matriz 3.12/3.14).
2. **Interface `Database`** (5 métodos): `execute`, `fetch_one`, `fetch_all`,
   `transaction` (async context manager), `close`. La semántica de
   `transaction()` es commit-on-exit / rollback-on-raise. Dentro del bloque
   `async with db.transaction():`, las llamadas a `execute`/`fetch_*`
   reutilizan la sesión activa (no abren una nueva).
3. **Factory `create_database_from_url(url)`:** acepta y **coerce** schemes
   `postgresql://` y `postgresql+psycopg2://` a `postgresql+asyncpg://` (común
   cuando el caller viene de testcontainers). Rechaza con `ValueError` schemes
   desconocidos (fail fast).
4. **Pool:** `pool_size=10, max_overflow=20, pool_pre_ping=True, echo=dev-only`
   (valores sane default para 100 usuarios concurrentes; tuneables vía
   `Settings`).
5. **Tests de integración con testcontainers:** Postgres 17-alpine efímero en
   Docker, schema vía `Base.metadata.create_all` (no Alembic — ver "Riesgos").
6. **Logs estructurados:** Cada decisión de backend se loguea al arrancar la
   app con `log.info("app.backend_selected", backend=..., detail=...)` —
   clave para diagnosticar drift entre dev/staging/prod.

## Cómo correr localmente

### Stack completo con Postgres real (recomendado)

```powershell
# 1) Levantar DB + Redis + API (que conecta a Postgres real + corre migrations)
docker compose `
  -f infra/docker/docker-compose.yml `
  -f infra/docker/compose.local.dev.yml `
  up --build

# 2) En otra terminal: cargar seeds (idempotente)
$env:ENVIRONMENT = "development"
docker compose -f infra/docker/docker-compose.yml exec api python -m app.db.seed
```

### Verificar el backend activo

```powershell
# El log de arranque debe decir:
#   app.backend_selected backend=postgres detail=postgresql+asyncpg://***@db:5432/bodegaje
docker compose -f infra/docker/docker-compose.yml logs api | Select-String "backend_selected"
```

### Inspeccionar la BD

```powershell
# Conectarse con psql
docker compose -f infra/docker/docker-compose.yml exec db psql `
  -U bodegaje -d bodegaje -c "SELECT count(*) FROM warehouses;"
```

## Cómo correr los tests

### Tests unitarios (SQLite in-memory, sin Docker)

```powershell
cd apps/api
$env:REDIS_URL  = "redis://localhost:6379/0"
$env:JWT_SECRET = "dev-secret-not-for-production-32chars-XXXXXX"

# Todos los tests
pytest -v

# Solo unit (excluye integration)
pytest -v -m "not integration"
```

### Tests de integración (requieren Docker local)

```powershell
cd apps/api
$env:REDIS_URL  = "redis://localhost:6379/0"
$env:JWT_SECRET = "dev-secret-not-for-production-32chars-XXXXXX"

# Solo integration (levanta Postgres en testcontainers)
pytest -v -m integration

# Salida esperada: 11 passed in ~5s (cuando Docker está activo)
# Si Docker no está: 5 passed, 6 skipped (skip limpio, no fail)
```

### Lint + type-check

```powershell
cd apps/api
ruff check .
ruff format --check .
mypy app
```

## Riesgos conocidos

### R1 — Tests `test_api.py` no corren localmente (pre-existente)

`starlette==1.3.1` requiere `httpx2` (paquete nuevo), pero solo `httpx==0.28.1`
está instalado. **No es un bug introducido por esta fase** — es un mismatch
de versiones en el entorno local. Workarounds:

```powershell
# Opción A: instalar httpx2 (preferida)
python -m pip install httpx2

# Opción B: degradar starlette a una versión compatible con httpx 0.28
python -m pip install "starlette<1.0"
```

Esto NO bloquea CI si la imagen base ya tiene `httpx2` instalado.

### R2 — Migraciones Alembic en testcontainers

Los integration tests usan `Base.metadata.create_all` en vez de `alembic
upgrade head` porque Alembic requiere un driver síncrono (`psycopg2-binary` o
`psycopg3+libpq`) y la install de esos en Python 3.14 / Windows es
problematica. **Implicancia:** los integration tests validan el **contrato
de la interface Database** contra un schema generado, no la fidelidad exacta
de las migraciones Alembic.

**Mitigación:** agregar `alembic check` (Alembic 1.14+) en CI para validar
que `alembic upgrade head` contra una BD vacía produce el mismo schema que
los modelos. No implementado en esta fase por scope.

### R3 — `app.state.db` sigue siendo SQLite legacy

Cuando el backend detectado es `postgres`, la app igualmente crea un
`SQLiteDatabase` legacy en `app.state.db` para que los routers actuales
sigan funcionando (Fase 0/1 compat). El engine async Postgres se inicializa
en `app.state.engine` (vía `get_engine()`) y queda disponible para
healthcheck (`/api/v1/health`) y futuros repositorios async. **La migración
de routers a async es Fase 3+** y no es scope de esta fase.

**Síntoma observable:** los datos que se ven vía la API son los del SQLite
in-memory, NO los del Postgres. Para escribir en Postgres hoy, hay que
bypasear los routers y usar `create_database_from_url()` directamente (como
hacen los integration tests).

### R4 — `psycopg2-binary==2.9.10` no tiene wheel para Python 3.14

Si se quiere correr `alembic upgrade head` directamente (no vía
testcontainers) desde el host con Python 3.14, hay que:

- Bajar a Python 3.12 (workaround), o
- Compilar `psycopg2-binary` desde source (puede requerir libpq-dev), o
- Usar `psycopg[binary]==3.x` (recomendado; pure-Python opcional vía
  `pip install psycopg[binary]` pero requiere libpq runtime).

### R5 — Seed legacy usaba `warehouse_type='central'`

La migración 0001 (post-ADR-0002) cambió el CHECK constraint a
`('principal', 'auxiliar', 'mecanico_box')`. El seed SQL crudo en
`db/seeds/0001_inventory_mvp_seed.sql` quedó desactualizado (el archivo NO
fue actualizado en esta fase por scope). **El nuevo seed en
`app/db/seed.py` usa `'principal'`** y funciona contra la BD real. Si se
corre `db/seeds/0001_inventory_mvp_seed.sql` directamente hoy, va a fallar
con un CHECK constraint violation.

## Próximos pasos

### Fase 2 (próxima)
- Migrar `app.state.db` y todos los routers a usar `PostgresDatabase` async.
- Eliminar la sección 2 (legacy `SQLiteDatabase`) una vez que `test_api.py`
  también migre a async.
- Implementar `SELECT ... FOR UPDATE` en `InventoryService.register_movement()`
  (regla de Fase 3 hoy; se adelanta a Fase 2 por ser prerequisite para
  concurrent tests).

### Fase 3 — Transferencias / Solicitudes
- Usar la nueva interface `Database` para el flujo de transferencias.
- Vistas materializadas para `stock_levels` desde `inventario_stock_real`
  (ADR-0001 POS-004).
- Concurrencia: tests con `pytest.mark.concurrency` y workers en paralelo.

### Fase 9 — Observabilidad (ADR-0007)
- Métricas Prometheus: queries por segundo, latencia p50/p95/p99, conexiones
  pool en uso. Exponer el pool stats de asyncpg vía `/metrics`.
- Logs estructurados con `request_id` y `db.query.duration_ms` (ya parcialmente
  implementado en `RequestLoggingMiddleware`).

### Backlog
- Agregar `alembic check` en CI (mitiga R2).
- Eliminar dependencia de `httpx2` vs `httpx` (mitiga R1).
- Reemplazar `app.db.demo.reset_demo_database()` por un fixture pytest con
  scope de módulo.
- Mover `app/db/demo.py` a `tests/_fixtures/` (código de demo, no de
  producción).

## Referencias

- [ADR-0001: Estrategia de adopción de PostgreSQL real](../adr/adr-0001-postgres-strategy.md)
- [ADR-0002: Modelo de boxes de mecánicos](../adr/adr-0002-boxes-modelo.md) — explica el cambio de `warehouse_type` que invalida el seed SQL legacy.
- [API DB Handoff 2026-03-18](../operations/api-db-handoff-2026-03-18.md) — estado previo del proyecto antes de esta fase.
- [Aterrizaje requerimiento multi-bodega 2026-07-14 §8.1](../architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md) — donde se origina la decisión de Fase 1.
- [SQLAlchemy 2.0 async docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
