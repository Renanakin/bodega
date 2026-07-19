# Changelog del Proyecto

> **Historial de cambios del sistema multi-bodega.**

## [0.1.0] - 2026-07-14

### FASE 0: Decisiones fundamentales ✅

**ADRs creados** (6):
- `adr-0001-postgres-strategy.md` - SQLAlchemy 2.0 async + asyncpg
- `adr-0002-boxes-modelo.md` - Boxes como warehouse_type='mecanico_box'
- `adr-0003-transfers-to-solicitudes.md` - Coexistencia 6 meses con vista derivada
- `adr-0004-worker-strategy.md` - Arq como worker async sobre Redis
- `adr-0005-smtp-stack.md` - Mailpit dev / AWS SES prod
- `adr-0006-token-approval.md` - HMAC itsdangerous 7 dias

**Documentos de gobernanza** (2):
- `docs/architecture/golden-rules.md` - 9 reglas + bonus
- `docs/architecture/30-second-rule.md` - Guia rapida de estructura

### FASE 1: Cimientos de Produccion ✅

**Archivos nuevos** (12):
- `app/core/config.py` - Settings con pydantic-settings (R1, R2)
- `app/core/logging.py` - structlog + JSON
- `app/core/middleware.py` - RequestLoggingMiddleware (R8)
- `app/core/security.py` - hash PBKDF2, tokens itsdangerous
- `app/shared/__init__.py`
- 9 modulos con `__init__.py` (placeholders con docstring)
- `tests/{unit,integration,e2e}/__init__.py`
- `tests/unit/conftest.py`
- `tests/unit/test_config.py` (7 tests)
- `tests/unit/test_logging.py` (6 tests)
- `pyproject.toml` (Ruff + mypy + pytest + coverage)
- `.env.{development,staging,production}.example`
- `infra/scripts/check-env-isolation.{sh,ps1}`

**Archivos modificados** (3):
- `requirements.txt` (24 deps)
- `main.py` (middleware, lifespan)
- `db/demo.py` (print → log.info)

### FASE 2: PostgreSQL Real + Alembic ✅

**Archivos nuevos** (15):
- `app/db/base.py` - DeclarativeBase + GUID type portable
- `app/db/postgres.py` - engine async con pool
- `app/db/sqlite.py` - fallback aiosqlite
- `app/db/session.py` - factory dual backend
- `app/db/models/{warehouses,products,inventory,transfers,users}.py`
- `app/db/models/__init__.py`
- `app/modules/health/{__init__,router}.py` - healthcheck ampliado
- `alembic.ini`, `alembic/{env,script.py.mako}`, `alembic/versions/0001_initial_mvp.py`
- `tests/integration/{conftest,test_async_session,test_warehouses_persistence,test_concurrent_postgres}.py`

**Archivos modificados** (5):
- `app/api/router.py` (movido health de api/routes a modules/health)
- `app/core/config.py` (compat props)
- `pyproject.toml` (asyncio_mode + per-file-ignores)

### FASE 3: MovementEngine + Lock Pesimista ✅

**Archivos nuevos** (6):
- `app/shared/movement_engine.py` - SELECT FOR UPDATE + log estructurado
- `app/modules/inventory/async_service.py` - InventoryServiceAsync
- `app/modules/transfers/async_service.py` - TransferServiceAsync
- `tests/conftest.py` (fixtures async con StaticPool)
- `tests/unit/test_movement_engine.py` (10 tests)
- `tests/integration/test_concurrent_movement_engine.py` (5 tests)

**Archivos modificados** (5):
- 5 modelos con `default=uuid.uuid4` en PKs

### FASE 4: Modelo de Datos Completo ✅

**Archivos nuevos** (19):
- 9 modelos SQLAlchemy
- 9 migraciones Alembic (0002-0010)
- 1 test suite (14 tests)

### FASE 5: Solicitudes de Recarga (N Productos) ✅

**Archivos nuevos** (4):
- `app/modules/solicitudes/schemas.py` - Pydantic
- `app/modules/solicitudes/service.py` - workflow completo
- `app/modules/solicitudes/router.py` - 8 endpoints REST
- `tests/integration/test_solicitudes.py` (8 tests)

**Archivos modificados** (2):
- `app/core/errors.py` (4 nuevas excepciones)
- `app/api/router.py` (incluir solicitudes)

### FASE 6: Replenishment + Multibodega ✅

**Archivos nuevos** (3):
- `app/modules/solicitudes/replenishment.py` - ReplenishmentEvaluator
- `app/modules/inventory/multibodega.py` - StockMultibodegaService
- `tests/integration/test_replenishment.py` (4 tests)

### FASE 7: BarcodeValidator + BarcodeInput ✅

**Archivos nuevos** (2):
- `app/shared/barcode.py` - EAN-13, EAN-8, Code 128, Code 39, QR
- `tests/unit/test_barcode.py` (15 tests)

### FASE 8: Supervisores + OrdenCompraService + Approval Token ✅

**Archivos nuevos** (3):
- `app/modules/supervisores/{service,router}.py` - CRUD
- `app/modules/ordenes_compra/{service,router}.py` - workflow + token
- `tests/integration/test_ordenes_compra.py` (5 tests)

**Archivos modificados** (2):
- `app/core/errors.py` (5 nuevas excepciones)
- `app/api/router.py` (incluir supervisores + ordenes_compra)

### FASE 9: Notifications + Email Outbox + Worker ✅

**Archivos nuevos** (3):
- `app/modules/notifications/service.py` - SMTP outbox pattern
- `app/modules/notifications/worker.py` - standalone worker
- `app/modules/notifications/router.py` - admin endpoint
- `tests/integration/test_notifications.py` (4 tests)

### FASE 10: Frontend Tailwind + Vistas ✅

**Archivos nuevos** (13):
- `tailwind.config.js`, `postcss.config.js`
- `src/styles/tailwind.css` con componentes custom
- `src/components/{BarcodeInput,MultibodegaGrid}.jsx`
- `src/views/{SolicitudesAuxPage,RecepcionBandejaPage,ConsolidadorCentralPage,OrdenesCompraPage,MultibodegaGridPage}.jsx`
- `src/styles/tailwind.css`

**Archivos modificados** (3):
- `package.json` (deps Tailwind)
- `src/router.jsx` (5 nuevas rutas)
- `src/shell/AppShell.jsx` (5 nuevos items)
- `src/main.jsx` (import tailwind.css)

### FASE 11: Observabilidad ✅

**Archivos nuevos** (2):
- `app/modules/observability/__init__.py`
- `app/modules/observability/metrics.py` - 14 metricas custom

**Archivos modificados** (1):
- `app/main.py` (integrar prometheus_fastapi_instrumentator)

**Dependencias añadidas**:
- `prometheus-fastapi-instrumentator==8.0.2`
- `prometheus-client==0.25.0`

### FASE 12: CI/CD + Documentacion Final ✅

**Archivos nuevos** (4):
- `.github/workflows/ci.yml` - 4 jobs (lint-backend, test-backend, lint-frontend, security-scan)
- `docs/architecture/adr-summary.md` - arquitectura final
- `docs/product/manual-usuario.md` - MANUAL DE USUARIO (12 KB)
- `docs/operations/runbook.md` - runbook operacional

**Archivos resumen** (2):
- `RESUMEN_FINAL.md` - resumen ejecutivo del proyecto
- `CHANGELOG_PROYECTO.md` - este archivo

## Estadisticas finales

- **Tests**: 83 verdes + 6 skipped (Postgres-only)
- **Modulos backend**: 15
- **Tablas**: 19
- **Migraciones**: 9
- **ADRs**: 6
- **Vistas frontend**: 13
- **Componentes frontend custom**: 2
- **Reglas de Oro cumplidas**: 9/9
