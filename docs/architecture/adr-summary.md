# Arquitectura Final del Sistema Multi-Bodega

> **Documento vivo.** Refleja el estado al cierre del roadmap (Fases 0-12).

## Resumen ejecutivo

Sistema de inventario multi-bodega con workflow completo:
- 1 Bodega Central (Principal) que recibe mercadería externa.
- N Bodegas Auxiliares (Talleres) que solicitan reposición a Central.
- M Boxes de mecánicos que reciben stock de su auxiliar padre.
- Workflow formal de Solicitudes (N productos) y Ordenes de Compra (externas con aprobación por token).

## Stack

| Capa | Tecnología | Versión |
|---|---|---|
| Backend | Python | 3.12+ |
| Backend | FastAPI | 0.116.1 |
| Backend | SQLAlchemy (async) | 2.0.36 |
| Backend | asyncpg | 0.30+ |
| Backend | Alembic | 1.14.0 |
| Backend | Pydantic | 2.10+ |
| Backend | structlog | 24.4+ |
| Backend | pytest + pytest-asyncio | 8.3+ / 1.4+ |
| Base de datos | PostgreSQL | 17 |
| Cache/Queue | Redis | 8 |
| SMTP dev | Mailpit | latest |
| SMTP prod | AWS SES / SendGrid | – |
| Frontend | React | 19.1 |
| Frontend | Vite | 7.1 |
| Frontend | Tailwind CSS | 3.4 |
| Frontend | React Router | 7.8 |
| Observabilidad | Prometheus | – |
| Workers | Arq (async, Redis) | 0.26 |
| CI/CD | GitHub Actions | – |
| Containers | Docker + Compose | – |

## Estructura del proyecto

```
bodega/
├── apps/
│   ├── api/                          # Backend FastAPI
│   │   ├── app/
│   │   │   ├── main.py              # Entry point
│   │   │   ├── core/                # Config, logging, security, errors
│   │   │   ├── db/                  # SQLAlchemy models + sessions
│   │   │   ├── modules/             # Dominios (warehouses, products, solicitudes, OC, etc.)
│   │   │   ├── shared/              # MovementEngine, BarcodeValidator
│   │   │   └── worker/              # Arq workers
│   │   ├── alembic/                 # Migraciones versionadas
│   │   └── tests/                   # unit / integration / e2e
│   └── web/                          # Frontend React
│       ├── src/
│       │   ├── components/           # BarcodeInput, MultibodegaGrid
│       │   ├── views/               # Paginas (DashboardPage, SolicitudesAuxPage, etc.)
│       │   ├── context/             # AuthContext, UiContext
│       │   ├── lib/                 # api.js (HTTP client)
│       │   └── styles/              # tailwind.css + styles.css legacy
│       └── tailwind.config.js
├── db/                               # SQL canonico de referencia
├── infra/
│   ├── docker/
│   │   ├── docker-compose.yml       # Base comun
│   │   ├── compose.{local,staging,production}.yml
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.web
│   │   └── nginx/conf.d/
│   ├── environments/                 # Plantillas .env
│   └── scripts/                      # Operacion
├── docs/
│   ├── adr/                         # Architecture Decision Records
│   ├── architecture/                # 30-second-rule, golden-rules
│   ├── operations/                  # Runbooks
│   └── product/                     # Manual de usuario
├── .github/workflows/                # CI/CD
└── .env.{development,staging,production}.example
```

## Modelo de datos (19 tablas)

| Tabla | Categoria | Proposito |
|---|---|---|
| `warehouses` | Core | Bodegas (principal, auxiliar, mecanico_box) |
| `users` | Auth | Usuarios con rol |
| `user_sessions` | Auth | Tokens bearer |
| `audit_logs` | Cross | Acciones auditables |
| `products` | Catalogo | Productos con categoria, precios, codigo_barras |
| `categories` | Catalogo | Jerarquia opcional |
| `detalles_neumaticos` | Catalogo | 1:1 con products (opt-in) |
| `stock_levels` | Inventario | Stock por bodega+producto (Nivel 1) |
| `inventory_movements` | Inventario | Ledger inmutable |
| `ubicaciones_estanteria` | Inventario | Pasillo/estanteria/altura |
| `inventario_stock_real` | Inventario | Stock por slot fisico (Nivel 2) |
| `solicitudes_recarga` | Operaciones | N productos de auxiliar a principal |
| `detalle_solicitud_recarga` | Operaciones | Lineas de solicitud |
| `supervisores` | Operaciones | Entidad fisica con email |
| `ordenes_compra` | Operaciones | OC externas |
| `detalle_orden_compra` | Operaciones | Lineas de OC |
| `email_outbox` | Operaciones | Cola SMTP |
| `proveedores` | Operaciones | Catalogo de proveedores |
| `transfers` | Legacy | DEPRECADO en Fase 5 (mantener 6 meses) |

## Modulos backend

```
auth/                 Auth + RBAC (4 roles)
warehouses/           CRUD bodegas
products/             CRUD productos
categories/           CRUD categorias
ubicaciones/          Slots fisicos
stock_real/           Stock por slot
inventory/            Stock por bodega + Multibodega
solicitudes/          Solicitudes de recarga (N productos) + ReplenishmentEvaluator
ordenes_compra/       OC externas + approval token
supervisores/         CRUD supervisores
notifications/        Email outbox + worker
proveedores/          CRUD proveedores
audit/                Audit logs
health/               Healthcheck ampliado
observability/        Metricas Prometheus
```

## APIs (resumen)

| Endpoint | Descripcion |
|---|---|
| `POST /api/v1/auth/login` | Login con bearer token |
| `GET/POST /api/v1/warehouses` | CRUD bodegas |
| `GET/POST /api/v1/products` | CRUD productos |
| `GET /api/v1/inventory/stock` | Stock por bodega |
| `GET /api/v1/inventory/multibodega?sku=X` | Distribucion SKU x bodega |
| `GET /api/v1/inventory/summary` | KPIs dashboard |
| `GET/POST /api/v1/solicitudes` | Solicitudes de recarga |
| `PATCH /api/v1/solicitudes/{id}/approve` | Aprobar |
| `POST /api/v1/solicitudes/{id}/dispatch` | Despachar (N productos) |
| `POST /api/v1/solicitudes/{id}/receive` | Recibir (con barcode opcional) |
| `POST /api/v1/solicitudes/{id}/reject` | Rechazar |
| `GET/POST /api/v1/supervisores` | CRUD supervisores |
| `GET/POST /api/v1/ordenes-compra` | CRUD OC |
| `POST /api/v1/ordenes-compra/{id}/enviar` | Enviar email + generar token |
| `POST /api/v1/ordenes-compra/aprobar/{token}` | Aprobar OC publica (sin auth) |
| `POST /api/v1/ordenes-compra/rechazar/{token}` | Rechazar OC publica |
| `GET /api/v1/notificaciones/outbox` | Ver cola de emails |
| `GET /api/v1/health` | Healthcheck (DB + Redis) |
| `GET /api/v1/health/live` | Liveness probe |
| `GET /metrics` | Prometheus metrics |

## Reglas de Oro aplicadas

| Regla | Implementacion | Verificacion |
|---|---|---|
| R1 (Cero Hardcoding) | Settings via pydantic-settings | grep `grep -rE "postgres://.*:" apps/` retorna 0 |
| R2 (Aislamiento) | 3 archivos `.env.*` | `check-env-isolation.sh` |
| R3 (30 segundos) | Estructura canónica | Documento `30-second-rule.md` |
| R4 (Separación) | Router/Service/Repository | Ruff custom rule + grep |
| R5 (Auto-doc) | Nombres de archivos | Code review |
| R6 (Tests) | 60+ tests verdes | CI con cobertura ≥ 80% |
| R7 (CI) | GitHub Actions | Pipeline verde |
| R8 (Logging) | structlog con JSON | grep `print()` retorna 0 |
| R9 (Docker) | compose base + 3 perfiles | `docker compose config` |

## Decisiones arquitecturales

Ver [docs/adr/](adr/) para las 6 ADRs:
- [ADR-0001](adr/adr-0001-postgres-strategy.md): SQLAlchemy 2.0 async + asyncpg
- [ADR-0002](adr/adr-0002-boxes-modelo.md): Boxes como `warehouse_type='mecanico_box'`
- [ADR-0003](adr/adr-0003-transfers-to-solicitudes.md): Coexistencia transfers/solicitudes 6 meses
- [ADR-0004](adr/adr-0004-worker-strategy.md): Arq como worker async
- [ADR-0005](adr/adr-0005-smtp-stack.md): Mailpit dev / SES prod
- [ADR-0006](adr/adr-0006-token-approval.md): HMAC itsdangerous 7 dias
