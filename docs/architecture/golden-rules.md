# Reglas de Oro para Python en Producción — Bodega

> **Documento vivo.** Toda excepción a estas reglas debe documentarse como ADR.
> **Última revisión:** 2026-07-14
> **Owner:** Arquitecto de Software
> **Aplica a:** todo el código bajo `apps/api/`, `apps/web/` (en su capa de integración), `db/`, `infra/`.

---

## 1. Seguridad y Gestión de Credenciales

### R1 — Cero Hardcoding

- **Regla**: No debe existir ni una sola URL de base de datos, API key, secreto de JWT, credencial SMTP o similar escrito directamente en el código.
- **Cómo se cumple**:
  - Toda config se lee vía `pydantic-settings` en `apps/api/app/core/config.py`.
  - Variables definidas en `Settings` con tipos (`PostgresDsn`, `RedisDsn`, `SecretStr`, `EmailStr`).
  - Cada PR incluye grep check en CI: `grep -rE "postgres://|password=|secret=" apps/api/app` debe retornar 0 matches fuera de `core/`.
- **Violación → blocker**: PR con secreto en código se cierra sin review.

### R2 — Aislamiento de Entornos

- **Regla**: Las variables de desarrollo, staging y producción son distintas. Si dependes de tu memoria para cambiar un valor antes de un deploy, el sistema ya está roto.
- **Cómo se cumple**:
  - Tres archivos `.env.{development,staging,production}.example` con valores distintos (probados).
  - Cada archivo declara `ENVIRONMENT=...` en la primera línea.
  - Script `infra/scripts/check-env-isolation.sh` falla el CI si el mismo secreto aparece en 2 entornos.
  - En producción, secrets se leen de GitHub Secrets / AWS Secrets Manager, **nunca** de `.env` commiteado.
- **Violación → blocker**: deploy cancelado.

---

## 2. Arquitectura y Estructura

### R3 — La Regla de los 30 Segundos

- **Regla**: Debes ser capaz de saber exactamente en qué carpeta va una nueva funcionalidad en menos de medio minuto.
- **Cómo se cumple**:
  - Estructura canónica: `apps/api/app/modules/<dominio>/{router,schemas,service,repository,models,dependencies}.py`.
  - Cada `__init__.py` de módulo declara el dominio en 1 línea (auto-documentación).
  - Documento `docs/architecture/30-second-rule.md` mantiene el árbol de decisión.
- **Verificación**: code review checklist pregunta "¿dónde pondrías una nueva ruta para X?". Si la respuesta no es <30s, la estructura falla.

### R4 — Separación de Responsabilidades

- **Regla**: Un endpoint solo debe recibir la solicitud y delegar la acción. No debe validar, procesar lógica de negocio y consultar la base de datos en la misma función.
- **Cómo se cumple**:
  - `router.py`: solo HTTP — `def create_x(payload): return await service.create_x(payload)`.
  - `service.py`: reglas de negocio, orquestación.
  - `repository.py`: solo acceso a datos; un repository = una tabla/agregado.
  - `models.py`: definición SQLAlchemy.
  - `schemas.py`: contratos Pydantic.
  - Linter custom (Ruff rule) prohíbe `db.execute`, `db.query`, `sqlite3` en `service.py` y `router.py`.
  - Linter custom prohíbe lógica con `if`/`for` extensos en `router.py` (heurística: >10 líneas de código no-Pydantic).

### R5 — Auto-documentación

- **Regla**: La estructura de carpetas y el nombre de los archivos deben explicar el "porqué" de la arquitectura. Si alguien necesita leer el código interno para entender cómo se organiza el proyecto, la estructura falló.
- **Cómo se cumple**:
  - `apps/api/app/modules/<dominio>/` se llama como el dominio (`solicitudes`, no `controllers` ni `v2`).
  - `apps/api/app/shared/` contiene código compartido entre módulos (`movement_engine.py`, `barcode.py`, `approval_token.py`).
  - `apps/api/app/worker/tasks/` agrupa tareas async por dominio (`email.py`, `replenishment.py`).
  - El `tree apps/api/app` debe caber en 1 pantalla con la lógica a la vista.

---

## 3. Estabilidad y Pruebas

### R6 — Red de Seguridad (Tests)

- **Regla**: Las partes críticas (auth, lógica de stock, pagos, lógica central) deben tener tests automatizados. No necesitas 100% de cobertura, pero sí una red que evite desastres.
- **Cómo se cumple**:
  - Pirámide 60/30/10 (unit/integration/e2e).
  - Cobertura mínima por archivo:
    - `service.py` ≥ 90%.
    - `repository.py` ≥ 80%.
    - `router.py` ≥ 70% (validaciones y errores).
  - Tests de concurrencia explícitos para stock: 50 tasks paralelas al mismo SKU, 100/100 verde.
  - Tests parametrizados para casos de error de cada dominio.
  - CI ejecuta `pytest --cov=apps/api --cov-fail-under=80` y falla si baja.

### R7 — Confianza en el Cambio

- **Regla**: No debes "cruzar los dedos" al subir un cambio. La seguridad para hacer deploy viene de una arquitectura aislada y tests que validen el código.
- **Cómo se cumple**:
  - GitHub Actions ejecuta en cada PR:
    1. `ruff check` + `ruff format --check` (lint + formato).
    2. `mypy apps/api` (type-check).
    3. `pytest tests/unit tests/integration` con coverage.
    4. `playwright test` (E2E).
    5. `docker compose config` (validar compose).
    6. `trivy image` (security scan).
  - Cualquier fallo → bloquea merge.
  - Deploy a producción requiere manual approval en GitHub Actions.
  - Rollback documentado en `docs/operations/ROLLBACK.md` ejecutable en <5 min.

---

## 4. Observabilidad y Monitoreo

### R8 — Logging Profesional

- **Regla**: Prohibido usar `print` para debugar en producción. Necesitas un sistema de logs que te avise proactivamente de los fallos sin esperar a que un usuario te reporte el error.
- **Cómo se cumple**:
  - `structlog` configurado en `apps/api/app/core/logging.py` con JSON renderer a stdout.
  - Context vars: `request_id`, `user_id`, `entity_type`, `entity_id`.
  - Cada request pasa por `RequestLoggingMiddleware` que loguea `{method, path, status, duration_ms}`.
  - Linter custom prohíbe `print(` en `apps/api/app/`.
  - Linter custom prohíbe `import logging` directo (usar `structlog`).
  - Alertas Prometheus por:
    - `api_requests_5xx_rate > 1%` 5 min → warning.
    - `email_outbox_pending > 50` 10 min → crítica.
    - `replenishment_evaluator_last_run > 10min` → crítica.
  - Cada movimiento de stock loguea `movement.applied` con `user_id, warehouse_id, product_id, delta, new_quantity, reference_id`.

---

## 5. Despliegue (Deployment)

### R9 — Portabilidad con Docker

- **Regla**: Si tú eres el único que puede desplegar el proyecto o si toma horas configurar el entorno manualmente, no está listo. Usa Docker para que funcione en cualquier máquina, no solo en tu laptop.
- **Cómo se cumple**:
  - Un solo `make fresh-start` levanta todo el stack (api, worker, web, db, redis, mailpit) en <3 min desde cero.
  - Dockerfiles multi-stage: stage `builder` con dev deps, stage `runtime` solo con lo necesario.
  - Tres perfiles: `compose.local.yml`, `compose.staging.yml`, `compose.production.yml`, todos válidos.
  - En `production`, solo `nginx` expone puertos al exterior; `db`, `redis`, `api`, `worker` son internos.
  - `infra/scripts/reset-demo.sh` resetea la BD a estado demo en <30s.
  - Runbook en `docs/operations/DEPLOYMENT_RUNBOOK.md` con pasos exactos.

---

## 6. Regla Bonus (Regla #10)

**Si una tarea nueva no cabe en la estructura de módulos actual, es señal de que la estructura está mal — no de que la tarea está mal. Replantear la estructura antes de force-fittear el código.**

- Ejemplo: si tienes que meter una ruta de "orden de compra" en `inventory/`, la estructura está mal; crea `ordenes_compra/`.
- Ejemplo: si el `router.py` de `warehouses` crece a >300 líneas, es señal de que falta un submódulo (e.g. `warehouses/boxes.py`).

---

## 7. Aplicación por Fase del Roadmap

| Fase | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 |
|---|---|---|---|---|---|---|---|---|---|
| **0 — Decisiones** | ✓ | ✓ | ✓ | ✓ | ✓ | | | | |
| **1 — Cimientos** | ★ | ★ | ★ | ★ | ★ | | | ★ | ✓ |
| **2 — PostgreSQL real** | ★ | ★ | ✓ | ★ | ✓ | ★ | ★ | ★ | ★ |
| **3 — MovementEngine** | | | ★ | ★ | ★ | ★ | ✓ | ★ | |
| **4 — Modelo completo** | | | ★ | ★ | ★ | ★ | ✓ | | ★ |
| **5 — Solicitudes N-prod** | | | ★ | ★ | ★ | ★ | ★ | ★ | |
| **6 — Stock real + replenishment** | | | ★ | ★ | ★ | ★ | ★ | ★ | ★ |
| **7 — Barcode scanner** | | | ★ | ★ | ★ | ★ | ★ | ★ | |
| **8 — Supervisores + OC** | | | ★ | ★ | ★ | ★ | ★ | ★ | |
| **9 — SMTP async** | ★ | ★ | ★ | ★ | ★ | ★ | ★ | ★ | ★ |
| **10 — Frontend Tailwind** | | | ★ | | ★ | | ★ | | ★ |
| **11 — Observabilidad** | | | ✓ | | | ✓ | ★ | ★ | ★ |
| **12 — Hardening + CI/CD** | ★ | ★ | ✓ | | | ★ | ★ | ★ | ★ |

Leyenda: `★` = regla se INTRODUCE en esta fase · `✓` = regla se APLICA/VERIFICA en esta fase.

---

## 8. Verificación Periódica

### Auditoría trimestral (manual)

```bash
# R1: sin secretos en código
grep -rE "postgres://|password=|secret=" apps/api/app | grep -v "core/config.py" | grep -v "core/security.py"

# R2: entornos aislados
bash infra/scripts/check-env-isolation.sh

# R4: separación de capas
grep -rn "db.execute\|db.query" apps/api/app/modules/*/service.py apps/api/app/modules/*/router.py

# R8: sin print
grep -rn "print(" apps/api/app

# R9: compose válido en 3 perfiles
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.local.yml config
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.staging.yml config
docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml config
```

### Gate de merge (CI)

```yaml
# .github/workflows/ci.yml (extracto)
- name: Check no hardcoded secrets
  run: |
    if grep -rE "postgres://|password=|secret=" apps/api/app | grep -v "core/config.py" | grep -v "core/security.py"; then
      echo "::error::Hardcoded secret found"
      exit 1
    fi

- name: Check no print statements
  run: |
    if grep -rn "print(" apps/api/app; then
      echo "::error::print() is forbidden in production code"
      exit 1
    fi

- name: Check environment isolation
  run: bash infra/scripts/check-env-isolation.sh

- name: Lint with custom rules
  run: ruff check apps/api

- name: Type check
  run: mypy apps/api

- name: Tests with coverage
  run: pytest --cov=apps/api --cov-fail-under=80
```

---

## 9. Cambios a Este Documento

| Fecha | Cambio | Autor |
|---|---|---|
| 2026-07-14 | Creación inicial con 9 reglas + bonus | Arquitecto de Software |

Cualquier cambio a estas reglas requiere un ADR en `docs/adr/`.
