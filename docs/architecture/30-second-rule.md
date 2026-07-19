# La Regla de los 30 Segundos — Guía Rápida de Estructura

> **Propósito:** un dev nuevo debe saber dónde va una nueva funcionalidad (ruta, modelo, servicio, test) en menos de 30 segundos.
> **Aplicabilidad:** todo el código bajo `apps/api/`, `apps/web/`, `db/`, `infra/`.

---

## 1. El árbol de decisión (en 30 segundos)

```
¿QUÉ QUIERO AGREGAR?
│
├── Una nueva RUTA DE API (endpoint)
│   └── apps/api/app/modules/<dominio>/router.py
│       └── si el dominio no existe → apps/api/app/modules/<nuevo_dominio>/__init__.py
│
├── Una nueva REGLA DE NEGOCIO
│   └── apps/api/app/modules/<dominio>/service.py
│       └── si la regla es transversal (compartida por 2+ dominios) → apps/api/app/shared/<utilidad>.py
│
├── Un nuevo MODELO DE DATOS (tabla)
│   └── apps/api/app/modules/<dominio>/models.py
│       └── apps/api/migrations/versions/00XX_<descripcion>.py (Alembic)
│       └── db/schema/<dominio>.md (documentación legible)
│
├── Un nuevo CONTRATO DE REQUEST/RESPONSE (Pydantic)
│   └── apps/api/app/modules/<dominio>/schemas.py
│
├── Un nuevo QUERY A BASE DE DATOS
│   └── apps/api/app/modules/<dominio>/repository.py
│       └── NUNCA en service.py (R4)
│
├── Un nuevo TRABAJO ASÍNCRONO (worker)
│   └── apps/api/app/worker/tasks/<nombre>.py
│       └── apps/api/app/worker/main.py (registro)
│
├── Una nueva VISTA EN FRONTEND (página)
│   └── apps/web/src/views/<Nombre>Page.jsx
│       └── apps/web/src/router.jsx (registrar ruta)
│
├── Un nuevo COMPONENTE REUTILIZABLE
│   └── apps/web/src/components/<Nombre>.jsx
│
├── Un nuevo FORMULARIO OPERACIONAL
│   └── apps/web/src/forms/<Nombre>Form.jsx
│
├── Una nueva REGLA DE LINTER O SETUP
│   └── apps/api/pyproject.toml (Ruff) o apps/api/.mypy.ini
│
├── Un nuevo HOOK DE GIT
│   └── .git/hooks/ o .pre-commit-config.yaml
│
├── Un nuevo SCRIPT DE OPERACIÓN
│   └── infra/scripts/<nombre>.sh o .ps1
│
└── Una nueva DECISIÓN ARQUITECTURAL
    └── docs/adr/adr-NNNN-<titulo-slug>.md
```

---

## 2. Estructura canónica de un módulo backend

Cada dominio en `apps/api/app/modules/<dominio>/` tiene **exactamente** estos archivos (pueden faltar si aún no se usan, pero no se añaden otros):

```
modules/<dominio>/
├── __init__.py           # Docstring de 1 línea describiendo el dominio
├── router.py             # Endpoints HTTP (R4: solo HTTP)
├── schemas.py            # Pydantic: request/response models
├── service.py            # Reglas de negocio (R4: orquesta repos)
├── repository.py         # Acceso a datos (R4: solo SQL/queries)
├── models.py             # Modelos SQLAlchemy (tabla, columnas, FKs)
├── dependencies.py       # FastAPI Depends (guards, current_user, etc.)
├── exceptions.py         # Errores de dominio (opcional, solo si hay específicos)
└── jobs.py               # Tareas programadas o workers específicos (opcional)
```

**Reglas estrictas:**

- `router.py` **nunca** importa de `sqlalchemy` o llama a `db.execute`.
- `service.py` **nunca** importa de `fastapi` o `starlette`.
- `repository.py` **nunca** tiene reglas de negocio (sin `if` que no sea de filtrado SQL).
- `models.py` **nunca** tiene lógica (solo definiciones de tabla).
- `schemas.py` **nunca** importa de `app.db` (no debe conocer la BD).

---

## 3. ¿Qué nombre le pongo al módulo?

| Si la funcionalidad es sobre... | Nombre del módulo |
|---|---|
| Usuarios, login, sesiones, roles | `auth` |
| Bodegas, sus tipos, jerarquía | `warehouses` |
| Productos, SKUs, precios | `products` |
| Categorías de producto | `categories` |
| Ubicaciones físicas (pasillo, estantería) | `ubicaciones` |
| Stock por slot físico | `stock_real` |
| Movimientos de inventario, kardex | `inventory` |
| Solicitudes de recarga entre bodegas | `solicitudes` |
| Órdenes de compra externas | `ordenes_compra` |
| Proveedores externos | `proveedores` |
| Supervisores (entidad de dominio) | `supervisores` |
| Envío de emails, outbox | `notifications` |
| Reportes, exports | `reports` |
| Auditoría de acciones | `audit` |
| Chat interno | `chat` |
| Replenishment automático (job) | `solicitudes/jobs.py` (no módulo aparte) |
| Sistema de slotting | `stock_real` + `ubicaciones` (no módulo aparte) |

**Reglas de naming:**

- Nombres en singular (`solicitudes`, no `solicitud`).
- Nombres en español para dominio (`ordenes_compra`, no `purchase_orders`).
- Si el nombre tiene espacios, usar snake_case (`ordenes_compra`, no `ordenes-compra`).
- **Nunca** sufijos como `v2`, `new`, `old`; eso es señal de mala abstracción previa.

---

## 4. ¿Mi código va en `modules/` o en `shared/`?

**Regla fácil:**

> Si **un solo módulo** lo usa → va en `modules/<ese_dominio>/`.
> Si **dos o más módulos** lo usan → va en `shared/`.

**Ejemplos de `shared/`:**

| Utilidad | Por qué está en `shared/` |
|---|---|
| `movement_engine.py` | `inventory` y `solicitudes` lo usan |
| `barcode.py` | `solicitudes` y `inventory` lo usan |
| `approval_token.py` | `ordenes_compra` y `notifications` lo usan |
| `pagination.py` | Casi todos los listados lo usan |
| `pagination.py` | Casi todos los listados lo usan |

**Ejemplos de cosas que NO van en `shared/`:**

- `email_template_orden_compra.html.j2` → `modules/notifications/templates/` (un solo módulo).
- `low_stock_evaluator.py` → `modules/solicitudes/jobs.py` (un solo módulo).
- `migration_helper.py` → borrar (las migraciones son one-shot, no reutilizables).

---

## 5. ¿Y si tengo dudas?

1. **Busca un módulo análogo** y copia su estructura. Si `solicitudes/` tiene `router, schemas, service, repository, models, dependencies`, tu nuevo módulo también.
2. **Pregúntate: ¿es una funcionalidad o una integración?**
   - Funcionalidad (e.g. "gestión de proveedores") → `modules/proveedores/`.
   - Integración (e.g. "cliente de Mailgun") → `shared/mailgun_client.py`.
3. **Si es la segunda vez que lo escribes**, muévelo a `shared/`.
4. **Si ni siquiera encaja aquí, plantea un ADR** antes de force-fittear.

---

## 6. Anti-patrones explícitos (NO hacer)

| Anti-patrón | Por qué está mal | Dónde debería ir |
|---|---|---|
| `apps/api/app/utils.py` con funciones genéricas | Es el "cajón de sastre"; viola R3, R4 y R5 | `shared/<utilidad_específica>.py` |
| Lógica de negocio en `router.py` | Viola R4 | `service.py` |
| SQL crudo en `service.py` | Viola R4 | `repository.py` |
| `modules/inventory/controllers/` (anidamiento innecesario) | Viola R3; el archivo router.py ya implica HTTP | `modules/inventory/router.py` |
| `modules/v2_solicitudes/` | Naming con versión = mala abstracción previa | Refactorizar `solicitudes/` |
| Constantes mágicas (`"admin"`, `"supervisor"`) en varios archivos | El linter no las atrapa, el código se rompe al refactorizar | `shared/constants.py` o enum en el módulo que las define |
| `print("debug")` para inspeccionar | Viola R8 | `logger.debug("...")` con structlog |
| `os.getenv("DB_URL")` en `repository.py` | Viola R1, R2 | `get_settings().database_url` |
| `db.execute("SELECT ...") en router.py` | Viola R4 | `repository.py` |

---

## 7. Test: ¿estoy aplicando bien la regla de los 30 segundos?

Hágase estas preguntas:

1. Si mañana se incorpora un dev nuevo, ¿podría encontrar dónde va un endpoint de "orden de compra" en menos de 30 segundos?
   - Si la respuesta es "no", la estructura falla.
2. Si necesito ver la lógica de negocio de "generar solicitud automática", ¿puedo ir directo a un solo archivo?
   - Si la respuesta es "tengo que buscar en 3 archivos", el service está mal partido.
3. Si quiero agregar un nuevo test de "stock concurrente", ¿sé dónde ponerlo sin preguntar?
   - Si la respuesta es "no", el árbol de tests no es obvio.

Si alguna respuesta es "no" durante 3 sprints seguidos, **es hora de un ADR para reorganizar**.

---

## 8. Ejemplo completo: agregar "Gestión de Proveedores"

Supongamos que se pide:

> "Necesito un módulo para gestionar proveedores externos (nombre, RUT, contacto, email, productos que vende)."

**Pasos (en orden, debería tomar <2 minutos):**

1. **¿Es un dominio nuevo?** Sí (no hay `proveedores/`). Crear carpeta.
2. **Crear archivos canónicos** (sin inventar nuevos):
   ```
   apps/api/app/modules/proveedores/
   ├── __init__.py          # "Proveedores externos: catálogo, contacto, productos que vende."
   ├── router.py            # CRUD endpoints
   ├── schemas.py           # ProveedorCreate, ProveedorUpdate, ProveedorResponse
   ├── service.py           # Reglas: RUT único, no eliminar si tiene OC asociadas
   ├── repository.py        # Queries
   ├── models.py            # Tabla proveedores
   └── dependencies.py      # (vacío por ahora)
   ```
3. **Migración Alembic**:
   ```
   apps/api/migrations/versions/0014_proveedores.py
   ```
4. **Tests**:
   ```
   apps/api/tests/unit/proveedores/test_service.py
   apps/api/tests/integration/proveedores/test_crud.py
   ```
5. **Frontend** (si aplica):
   ```
   apps/web/src/views/ProveedoresPage.jsx
   apps/web/src/forms/ProveedorForm.jsx
   apps/web/src/router.jsx  # añadir /proveedores
   ```
6. **Documentación**:
   ```
   docs/product/proveedores.md  # manual de usuario
   docs/architecture/backend-modules.md  # actualizar estado de módulos
   ```

**Tiempo total:** <5 min si la estructura está clara. Si toma más, hay un problema con la regla de los 30 segundos.

---

## 9. Referencias cruzadas

- `docs/architecture/golden-rules.md` — las 9 reglas + bonus
- `docs/architecture/backend-modules.md` — estado de cada módulo
- `docs/adr/` — decisiones arquitectónicas formales
- `docs/product/` — manuales de usuario y features
- `docs/operations/` — runbooks y procedimientos
