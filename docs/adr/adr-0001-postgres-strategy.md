---
title: "ADR-0001: Estrategia de adopción de PostgreSQL real"
status: "Accepted"
date: "2026-07-14"
authors: "Equipo Bodegaje"
tags: ["arquitectura", "persistencia", "postgresql", "sqlalchemy"]
supersedes: ""
superseded_by: ""
---

# ADR-0001: Estrategia de adopción de PostgreSQL real

## Status

**Accepted** — Decisión ratificada para la Fase 1 del roadmap.

## Context

El MVP actual de `apps/api` corre sobre SQLite en memoria (`db_path=":memory:"`) para validar reglas de dominio sin acoplarse a un motor concreto. El `docker-compose.yml` provisiona PostgreSQL 17, pero la API no lo consume. Para soportar:

- Concurrencia real con `SELECT ... FOR UPDATE` (regla obligatoria de la spec de transferencias)
- Pool de conexiones para 100 usuarios concurrentes
- Migraciones versionadas robustas
- Vistas materializadas para `stock_levels` desde `inventario_stock_real`
- Auditoría transaccional de movimientos

se requiere conectar la API a PostgreSQL de forma nativa, sin pasar por adaptadores de compatibilidad. La decisión afecta a todo el ciclo de vida del backend (desarrollo, tests, CI, deploy).

## Decision

Adoptar **SQLAlchemy 2.0 async sobre `asyncpg`** como driver de acceso, con **Alembic** como gestor de migraciones. Se reemplaza la persistencia en SQLite por una conexión nativa a PostgreSQL. Los tests de integración usan `testcontainers-python` (PostgreSQL real en contenedor) en vez de SQLite en memoria. SQLite queda **únicamente** para tests unitarios muy rápidos que no tocan concurrencia.

### Capas y componentes

| Componente | Tecnología | Justificación |
|---|---|---|
| Driver | `asyncpg==0.30.0` | Performance, soporte async nativo |
| ORM/Core | `sqlalchemy[asyncio]==2.0.36` | `SELECT FOR UPDATE` idiomático, pool built-in, sin lock-in |
| Migraciones | `alembic==1.14.0` | Estándar, autogen, rollback explícito |
| Tests integración | `testcontainers-python` + `pytest-asyncio` | PostgreSQL real, aislamiento por test |
| Tests unitarios | SQLite in-memory (legado) | Velocidad, sin locks |
| Pool | `pool_size=10, max_overflow=20, pool_pre_ping=True` | Default sano para 100 usuarios |

## Consequences

### Positive

- **POS-001**: Concurrencia real con `SELECT FOR UPDATE` por fila, indispensable para Fase 3 (Solicitudes).
- **POS-002**: Pool de conexiones robusto evita agotamiento bajo carga.
- **POS-003**: Migraciones Alembic reemplazan el runner ad-hoc en `apps/api/app/db/session.py:128-153`.
- **POS-004**: Vistas materializadas en PostgreSQL soportan el modelo de 2 niveles de stock.
- **POS-005**: `pool_pre_ping` evita conexiones muertas tras restart del contenedor.

### Negative

- **NEG-001**: Curva de aprendizaje de SQLAlchemy 2.0 async (vs el actual `sqlite3` stdlib).
- **NEG-002**: Requiere contenedor PostgreSQL activo en dev local (ya existe en compose).
- **NEG-003**: Tests más lentos (100ms vs <1ms en SQLite memoria).
- **NEG-004**: Pérdida de sesiones de usuarios demo al migrar (necesario re-login).

## Alternatives Considered

### asyncpg puro (sin SQLAlchemy)

- **ALT-001**: **Description**: Usar `asyncpg` directamente, sin ORM.
- **ALT-002**: **Rejection Reason**: Mayor boilerplate para mapeo objeto-relacional, sin `SELECT FOR UPDATE` idiomático, no compensa el ahorro para 13 módulos.

### SQLAlchemy 1.4 sync

- **ALT-003**: **Description**: Versión síncrona clásica.
- **ALT-004**: **Rejection Reason**: Bloquea el event loop de FastAPI; pierde el beneficio principal del stack async.

### Tortoise ORM

- **ALT-005**: **Description**: ORM async estilo Django.
- **ALT-006**: **Rejection Reason**: Comunidad más pequeña, menos soporte para `FOR UPDATE` y migraciones complejas.

## Implementation Notes

- **IMP-001**: Refactor de `apps/api/app/db/session.py` → interface `Database` con implementaciones `SQLiteDatabase` (legacy) y `PostgresDatabase` (target).
- **IMP-002**: Nuevo `apps/api/alembic/` con configuración standalone; primera migración autogenerada desde los modelos SQLAlchemy derivados del esquema actual.
- **IMP-003**: Tests en `apps/api/tests/test_api.py` se dividen en `test_api_unit.py` (SQLite) y `test_api_integration.py` (testcontainers).
- **IMP-004**: Feature flag `DB_BACKEND=sqlite|postgres` en `apps/api/app/core/config.py` con default `postgres` en compose.
- **IMP-005**: Script de verificación: `python -m pytest tests/test_api_integration.py -v` debe pasar con PostgreSQL real.

## References

- **REF-001**: `docs/operations/api-db-handoff-2026-03-18.md` — estado previo del proyecto
- **REF-002**: `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md` §8.1
- **REF-003**: SQLAlchemy 2.0 async docs — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
