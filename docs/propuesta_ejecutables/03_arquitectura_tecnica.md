# Documento 3 — Arquitectura Técnica con Diagrama de Componentes

**Proyecto:** Sistema de Gestión de Inventario Multi-Bodega (`bodega`)
**Versión:** 1.0 — 2026-07-22
**Origen:** sección 22.1 (3) de `PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md`
**Fuente:** `apps/api/app/main.py`, `app/core/`, `app/modules/`, `apps/web/`,
`.github/workflows/ci.yml`, `docker-compose*.yml` (cuando aplique).

---

## 1. Propósito

Describir la arquitectura **tal como está implementada hoy** (Fase 5 cerrada
+ migración a Postgres), justificar elecciones técnicas, y dejar diagrama
de componentes en ASCII + tabla de responsabilidades. Las decisiones de
diseño grandes ya tienen un ADR asociado en `docs/adr/`; este documento los
consolida en una vista única.

---

## 2. Vista de despliegue (runtime)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Cliente web (Browser)                                                    │
│  - React 18 + Vite + Tailwind                                            │
│  - LocalStorage solo para token de sesión                                │
└──────────────┬───────────────────────────────────────────────────────────┘
               │ HTTPS (Nginx / cloud LB en prod)
               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Nginx / API Gateway                                                      │
│  - TLS termination                                                        │
│  - Cabeceras seguras (HSTS, X-Frame-Options, CSP)                         │
│  - Rate limiting por IP (futuro, hoy no configurado)                      │
│  - Sirve /apps/web/dist (build estático de Vite)                          │
└──────────────┬───────────────────────────────────────────────────────────┘
               │ HTTP interno
               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Uvicorn (ASGI) — contenedor: api                                        │
│  - FastAPI app (app/main.py)                                              │
│  - 4 workers en prod (uvicorn.workers.UvicornWorker)                      │
│  - Endpoints: /api/v1/*, /docs (dev), /metrics, /health                  │
│  - Middlewares (orden de registro → outermost primero):                   │
│      1. CORS                                                               │
│      2. CorrelationIdMiddleware (pure ASGI)                               │
│      3. IdempotencyMiddleware (Redis-backed, 24h TTL)                     │
│      4. FastAPI Exception handlers                                        │
└──────┬──────────────────┬───────────────────┬────────────────────────────┘
       │                  │                   │
       ▼                  ▼                   ▼
┌─────────────┐    ┌─────────────┐    ┌────────────────────┐
│ PostgreSQL  │    │   Redis     │    │  Mailpit (SMTP)    │
│  17-alpine  │    │  8-alpine   │    │  puerto 1025/8025  │
│  port 5432  │    │  port 6379  │    │  (dev)             │
│             │    │  cache +    │    │  En prod:          │
│  async via  │    │  idempotency│    │  SMTP real (Postmark│
│  asyncpg    │    │  + outbox   │    │  / Sendgrid)       │
└─────────────┘    └─────────────┘    └────────────────────┘
       ▲
       │
       │ (futuro, fase 2)
       │
┌──────┴──────────────┐
│ Arq worker          │  ← lee email_outbox y envía vía SMTP
│ python -m arq ...   │
│ contenedor: worker  │
└─────────────────────┘
```

> **Estado actual:** en desarrollo el outbox se procesa por el worker Arq
> en el mismo contenedor. En producción se separa en contenedor dedicado.
> La interfaz está lista (commit del sprint de hardening). Ver ADR-0004.

---

## 3. Vista de componentes (backend)

### 3.1 Capas de la app FastAPI

```
┌────────────────────────────────────────────────────────────────────┐
│  Capa de entrada (main.py + middleware stack)                      │
│  - create_app()                                                    │
│  - Logging estructurado (structlog)                                │
│  - CorrelationIdMiddleware (X-Request-ID, X-Correlation-ID)        │
│  - IdempotencyMiddleware (POST/PATCH/PUT/DELETE con Idempotency-   │
│    Key, cache 24h)                                                 │
│  - Exception handlers (DomainError → 4xx)                          │
└────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│  Capa de presentación (app/api/router.py + cada módulo/router.py)  │
│  - 19 routers (uno por módulo)                                     │
│  - Validación de payload con Pydantic v2                           │
│  - Dependencias: get_current_user, get_session, get_settings       │
│  - Documentación OpenAPI automática                                │
└────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│  Capa de servicio (app/modules/<modulo>/service.py)                │
│  - Reglas de negocio                                                │
│  - Orquestación de repositorios                                     │
│  - Validaciones que requieren leer otras filas                     │
│  - Transacciones explícitas (async with session.begin())            │
└────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│  Capa de persistencia (app/modules/<modulo>/repository.py o        │
│  queries/*.py)                                                     │
│  - En módulos migrados: AsyncSession + SQLAlchemy 2.x core          │
│  - En módulos legacy: detecta el backend en runtime y despacha     │
│  - Sin lógica de negocio                                            │
└────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│  Capa de datos (app/db/models/ + db/migrations/)                   │
│  - Modelos SQLAlchemy declarativos                                  │
│  - Migraciones versionadas (0001..0009)                             │
│  - asyncpg para Postgres en runtime, aiosqlite para tests          │
└────────────────────────────────────────────────────────────────────┘
```

### 3.2 Mapa de módulos backend

| Módulo | Router | Service | Repository | Tablas principales |
|---|---|---|---|---|
| `auth` | `router.py` | `service.py` | `repository.py` (híbrido async/legacy) | `users`, `user_sessions`, `audit_logs` |
| `warehouses` | `router.py` | `service.py` | via `Depends(get_session)` | `warehouses` |
| `products` | `router.py` | `service.py` | via `Depends(get_session)` | `products` |
| `product_extension` | `router.py` | — | via `Depends(get_session)` | `products` (columnas extend) |
| `categories` | `router.py` | `service.py` | via `Depends(get_session)` | `categories` |
| `ubicaciones` | `router.py` | `service.py` | via `Depends(get_session)` | `ubicaciones_estanteria` |
| `stock_real` | `router.py` | `service.py` | via `Depends(get_session)` | `inventario_stock_real` |
| `inventory` | `router.py` | `service.py` | via `Depends(get_session)` | `stock_levels`, `inventory_movements` |
| `solicitudes` | `router.py` | `service.py` | via `Depends(get_session)` | `solicitudes_recarga`, `detalle_solicitud_recarga` |
| `transfers` | `router.py` (solo GET + 410) | — | — | `transfers` (legacy) |
| `ordenes_compra` | `router.py` | `service.py` | via `Depends(get_session)` | `ordenes_compra`, `detalle_orden_compra`, `email_outbox` |
| `proveedores` | `router.py` | `service.py` | via `Depends(get_session)` | `proveedores` |
| `supervisores` | `router.py` | `service.py` | via `Depends(get_session)` | `supervisores` |
| `notifications` | `router.py` | `service.py` | via `Depends(get_session)` | `notificaciones` |
| `notificaciones` | (sub-módulo) | via `Depends(get_session)` | `notificaciones` |
| `audit` | `router.py` | — | via `Depends(get_session)` | `audit_logs` |
| `reports` | `router.py` | queries | via `Depends(get_session)` | `inventory_movements`, `products` |
| `barcode` | `router.py` | — | via `Depends(get_session)` | `products` |
| `observability` | `router.py` | `metrics.py` | — | (no DB) |
| `health` | `router.py` | — | chequea `app.state.async_engine` | (no DB) |

**Patrón de dependencias:** todos los routers usan
`Depends(get_session)` para inyectar `AsyncSession`. Los routers legacy
(durante la migración) usaban `app.state.db` (sync); ya fueron migrados
en commits `bf6cc3d..cb1950b`.

### 3.3 Diagrama de módulos (vista lógica)

```
                                ┌─────────────────┐
                                │     auth        │
                                │  (login, JWT)   │
                                └────────┬────────┘
                                         │ current_user
                ┌────────────────────────┼────────────────────────┐
                │                        │                        │
                ▼                        ▼                        ▼
        ┌───────────────┐         ┌───────────────┐         ┌───────────────┐
        │  warehouses   │         │   products    │         │  categories   │
        └───────┬───────┘         └───────┬───────┘         └───────┬───────┘
                │                         │                         │
                │  FK                     │  FK                     │ self-FK
                │                         │                         │
                ▼                         ▼                         ▼
        ┌───────────────┐         ┌───────────────┐         ┌───────────────┐
        │  ubicaciones  │         │  inventory    │         │   (niveles)   │
        │  stock_real   │◀────────│  movements    │         └───────────────┘
        └───────┬───────┘  1:N    └───────┬───────┘
                │                         │
                │                         │
                │                         ▼
                │                 ┌───────────────┐
                │                 │  solicitudes  │
                │                 │   (workflow)  │
                │                 └───────┬───────┘
                │                         │
                │                         │
                │                 ┌───────┴───────┐
                │                 ▼               ▼
                │         ┌───────────────┐  ┌───────────────┐
                │         │ordenes_compra │  │ notifications │
                │         │   + outbox    │  │   (in-app)    │
                │         └───────┬───────┘  └───────────────┘
                │                 │
                │                 ▼
                │         ┌───────────────┐
                │         │email_outbox → │──→ SMTP / Arq worker
                │         └───────────────┘
                │
                ▼
        ┌───────────────┐
        │   audit_logs  │  ◀── escribe auth y routers sensibles
        └───────────────┘
```

---

## 4. Middleware stack (orden de ejecución)

Los middlewares en Starlette se ejecutan en **orden inverso al registro**
(el último registrado es el más externo). En `create_app()` se registran
en este orden (de outermost a innermost):

1. **CORS** — maneja preflight `OPTIONS`, valida orígenes contra
   `settings.cors_origins_list`. Expone `X-Correlation-ID` y `X-Request-ID`.
2. **CorrelationIdMiddleware** (pure ASGI) — lee `X-Request-ID` del cliente
   o genera uno; lo propaga a `structlog` context; lo escribe en la
   respuesta. Ver `app/core/middleware.py`.
3. **IdempotencyMiddleware** (pure ASGI) — intercepta POST/PATCH/PUT/DELETE
   con header `Idempotency-Key`. Hashea `body + key` con SHA-256, busca en
   Redis (con fallback in-memory), sirve cache si hit, ejecuta y cachea si
   miss. TTL 24h. Ver `app/core/idempotency.py`.
4. **ExceptionMiddleware** (built-in Starlette) — captura excepciones no
   manejadas y las mapea a 500. Hay un handler global que setea
   `X-Correlation-ID` incluso en 500s.
5. **Exception handler de `DomainError`** (registrado vía
   `app.add_exception_handler`) — convierte errores de dominio a 4xx
   estructurados.

> **Importante:** el orden es deliberado. CORS debe ir primero para que
> la preflight no se loguee. Correlation va antes que Idempotency para
> que los hits/misses del cache ya tengan correlation_id en logs.

---

## 5. Capa de configuración

`app/core/config.py` define `Settings` con `pydantic-settings`. Variables
clave:

| Variable | Default | Propósito |
|---|---|---|
| `ENVIRONMENT` | `development` | Controla logs JSON vs console, Sentry, docs URL |
| `DATABASE_URL` | (none) | Si empieza con `postgresql+asyncpg://` → Postgres |
| `REDIS_URL` | `redis://localhost:6379/0` | Cache de idempotencia |
| `JWT_SECRET` | (requerido ≥32 chars en prod) | Firma de tokens |
| `JWT_EXPIRES_MIN` | `60` | Duración del access token |
| `SECRET_KEY` | (requerido ≥32 chars en prod) | Clave para sign de cookies/CSRF |
| `SMTP_HOST` / `SMTP_PORT` | `127.0.0.1` / `1025` | Relay para emails |
| `SMTP_FROM` | `noreply@bodega.cl` | Remitente |
| `CORS_ORIGINS` | `http://localhost:5173` | Lista separada por coma |
| `LOG_LEVEL` | `INFO` | structlog |
| `SENTRY_DSN` | (none) | Opcional; si está, captura errores |
| `METRICS_ENABLED` | `true` | Habilita `/metrics` Prometheus |

**Validaciones en arranque** (commit `6c1e9e6`):

- En `production`, `JWT_SECRET` y `SECRET_KEY` deben tener ≥32 caracteres
  o el server se rehúsa a arrancar.
- En `development`, se permiten defaults con `_*_DEV_OVERRIDE` solo si
  el test fuerza `_env_file=None`.

---

## 6. Capa de observabilidad

### 6.1 Logs estructurados

`app/core/logging.py` configura `structlog` con:

- `JSONRenderer` en `production` (line-oriented, parseable por Loki/ELK).
- `ConsoleRenderer` en `development` (con colores, traceback legible).
- Bound context: `request_id`, `user_id`, `path`, `method`, `latency_ms`.
- Sampling configurable por `LOG_LEVEL`.

### 6.2 Métricas Prometheus

`app/modules/observability/metrics.py` usa `prometheus-fastapi-instrumentator`:

- `/metrics` con métricas HTTP estándar (latencia p50/p95/p99, status
  codes, requests en vuelo).
- Métricas custom:
  - `solicitudes_creadas_total{estado}` (counter)
  - `ordenes_compra_aprobadas_total` (counter)
  - `email_outbox_pendientes` (gauge, leído de BD cada N segundos)
  - `db_pool_checked_out` (gauge del pool asyncpg)

### 6.3 Tracing / Sentry

- Sentry opcional. Si `SENTRY_DSN` está configurado, se inicializa con
  `FastApiIntegration` + `StarletteIntegration`. `send_default_pii=False`
  para no enviar emails o IPs en producción.
- No hay OpenTelemetry tracing distribuido todavía; es fase 2.

### 6.4 Healthcheck

`/health` (liveness): siempre 200 si el proceso está vivo.

`/health/ready` (readiness):

- Chequea `app.state.async_engine` con `SELECT 1`.
- Chequea Redis (si está configurado) con `PING`.
- Si cualquiera falla, devuelve 503.

---

## 7. Frontend (apps/web)

### 7.1 Stack

- **React 18** con hooks.
- **Vite 5** como bundler (HMR rápido, builds pequeños).
- **TypeScript** con strict mode.
- **Tailwind CSS 3** + shadcn/ui para componentes base.
- **React Query** para fetching con cache y revalidación.
- **Zustand** para estado global mínimo (auth + tema).

### 7.2 Estructura de carpetas

```
apps/web/
├── src/
│   ├── components/       ← componentes reutilizables
│   ├── pages/            ← rutas (1 archivo por página)
│   ├── hooks/            ← useAuth, useReviewMvpData, etc.
│   ├── services/         ← cliente HTTP (fetch wrapper + tipos)
│   ├── stores/           ← zustand stores
│   ├── lib/              ← utils, formatters
│   ├── routes.tsx        ← React Router
│   └── main.tsx
├── public/
├── tailwind.config.js
├── vite.config.ts
└── package.json
```

### 7.3 Build y deploy

- `npm run build` produce `dist/` con bundle estático.
- Nginx (o el servicio equivalente) sirve `dist/` en `/` y hace
  reverse-proxy para `/api/*` → uvicorn.
- `npm run dev` levanta Vite con HMR en `:5173` y proxy a
  `localhost:8000`.

---

## 8. CI/CD (`.github/workflows/ci.yml`)

```
┌────────────────────────────────────────────────────────────────────┐
│  Push a cualquier rama / PR a main                                  │
└─────────────────┬──────────────────────────────────────────────────┘
                  │
        ┌─────────┴────────┐
        │  Job 1: lint     │  → ruff + mypy + tsc --noEmit
        ├──────────────────┤
        │  Job 2: test     │  → pytest (SQLite in-memory) + coverage ≥ 77%
        ├──────────────────┤
        │  Job 3: web      │  → npm ci + npm run build
        ├──────────────────┤
        │  Job 4: external │  → Postgres 17 + Redis 7 + Mailpit services
        │                 │    + pytest -m integration
        ├──────────────────┤
        │  Job 5: docker   │  → build de imágenes api + web (no push)
        └──────────────────┘
                  │
        ┌─────────┴────────┐
        │  Job 6: gitleaks │  → secret scanning (con disable para
        │                 │    generic-api-key)
        └──────────────────┘
```

**Estado actual:** los 5 jobs (más gitleaks) corren en verde desde el
sprint de CI hardening. El push de imágenes a un registry no se hace
automáticamente todavía; se hace manualmente con `docker push`.

---

## 9. Decisiones arquitectónicas (consolidado de ADRs)

| ADR | Tema | Decisión |
|---|---|---|
| 0001 | Postgres como target de producción | Migración completa, `sqlite_legacy` eliminado |
| 0002 | Modelo de boxes (bodega origen/destino) | origen = auxiliar, destino = principal |
| 0003 | Reemplazo de `transfers` por `solicitudes` | N productos, workflow formal, transfers en 410 |
| 0004 | SMTP async via outbox + Arq worker | `email_outbox` es la fuente de verdad, worker es delivery |
| 0005 | Token de aprobación de OC por email | JWT con `jti` único, single-use |
| 0006 | Tailwind coexistiendo con CSS legacy | Vía `@layer` y scoping explícito |
| 0007 (pendiente) | PBKDF2 vs Argon2 | **Decidido PBKDF2**; ADR por escribir |

---

## 10. Patrones de diseño aplicados

| Patrón | Dónde | Propósito |
|---|---|---|
| **Repository** | `app/modules/<x>/repository.py` | Aislar la persistencia de la lógica de negocio |
| **Service Layer** | `app/modules/<x>/service.py` | Reglas de negocio orquestando repos |
| **Unit of Work** | `AsyncSession` con `session.begin()` | Transacciones explícitas |
| **Outbox** | `email_outbox` | Garantizar entrega de emails sin acoplar HTTP a SMTP |
| **Idempotency-Key** (Stripe) | `IdempotencyMiddleware` | Retry-safe POSTs |
| **State Machine** | `SolicitudEstado`, `OrdenCompraEstado` (enums) | Transiciones validadas en service |
| **Snapshot** | `ordenes_compra.proveedor_nombre` | Inmutabilidad histórica |
| **Append-only** | `audit_logs` | Cero UPDATE/DELETE |
| **Polymorphic reference** | `inventory_movements.reference_*` | Kardex unificado |
| **Hybrid backend dispatch** | `auth/repository.py` | Compat con tests legacy durante migración |

---

## 11. Trade-offs explícitos

| Decisión | Costo | Beneficio |
|---|---|---|
| UUIDs everywhere | Más bytes por fila | Sin colisiones, generar offline, merge-friendly |
| `numeric(14,2)` | Más espacio que float | Precisión exacta para dinero/stock |
| Snapshot en OC | Datos redundantes | Histórico inmutable si proveedor cambia |
| Polimórfico en `reference_*` | Menos tipos seguros | Una sola tabla kardex |
| `IdempotencyMiddleware` en stack | Latencia ~1ms por request con cache miss | Retry-safe en red inestable |
| `structlog` JSON en prod | Logs ilegibles sin tooling | Parseable por Loki/ELK |
| Frontend separado de API | 2 deploys, CORS | Build independiente, CDN-ready |
| Polling en `notificaciones` (no WS) | Latencia de actualización | Sin WebSockets aún; suficiente para MVP |

---

## 12. Riesgos arquitectónicos conocidos

1. **No hay WebSockets.** La UI hace polling cada 30s para
   `notificaciones`. Migrar a WS en fase 2 reduce latencia y carga.
2. **No hay service mesh.** Si escalamos a múltiples instancias de
   uvicorn, la idempotencia sigue funcionando (Redis es compartido),
   pero las tareas del outbox podrían duplicarse sin un lock distribuido.
   Hoy se mitiga con `attempts` y `status='dead'`.
3. **No hay circuit breaker.** Si Postgres se cae, las requests fallan
   con 500 inmediato. En fase 2: `tenacity` + backoff exponencial.
4. **CORS permisivo (`allow_methods=["*"]`).** En prod, restringir a
   los métodos necesarios.
5. **Sin rate limiting en app.** Nginx/Render proveen el control por IP,
   pero falta rate limit por usuario (ej: 10 logins/min).
6. **Sin OpenTelemetry.** Tracing distribuido end-to-end en fase 2.
7. **`mypy` con 214 errores preexistentes.** Plan de reducción en
   `docs/plan_mypy.md` (Sprints 1-5). No bloqueante.
8. **Sin CDN.** El bundle de React se sirve desde el mismo Nginx que
   la API. Aceptable para el volumen actual; Cloudflare/CloudFront
   cuando se justifique.

---

## 13. Roadmap de arquitectura (resumen)

Lo que ya **está hecho** vs lo que la propuesta original proponía:

| Componente | Propuesta | Estado |
|---|---|---|
| Frontend React + Vite + TS | ✅ | ✅ |
| Backend FastAPI | ✅ | ✅ |
| PostgreSQL | ✅ | ✅ (Fase 5+) |
| Redis (cache + idempotencia) | ✅ | ✅ (parcial) |
| WebSockets | ✅ | ❌ fase 2 |
| Tareas async (Celery/RQ/Arq) | ✅ | ⚠️ outbox + Arq en mismo contenedor |
| Docker | ✅ | ✅ |
| Nginx | ✅ | ✅ (config no versionada) |
| Prometheus + Grafana | ✅ | ⚠️ métricas sí, dashboards no |
| Kubernetes | opcional | ❌ (Compose es suficiente hoy) |

---

## 14. Glosario

- **Componente:** unidad lógica de la app (módulo backend, router,
  servicio, repositorio). Mapeable a archivos individuales.
- **Middleware ASGI:** callable que envuelve la app y puede
  cortocircuitar el response. Pure ASGI = no usa la API de Starlette
  (más rápido, sin overhead).
- **ADR:** Architecture Decision Record. Documento de decisión
  arquitectónica; vive en `docs/adr/`.
- **Outbox:** tabla que desacopla la decisión de "enviar" del envío
  efectivo. Patrón de la propuesta original sección 11.
