# Handoff API/DB - 18-03-2026

**Fecha:** 18-03-2026  
**Alcance:** `apps/api`, `db`, `docs`  
**Objetivo de este handoff:** dejar documentado que ya se hizo, que se verifico y que falta para continuar en otra sesion sin perder contexto.

## 1. Estado actual

El proyecto ya tiene un **MVP funcional de API** para inventario multi-bodega y una **base SQL alineada** al dominio del MVP.

### API

La API ya implementa:

- `GET /api/v1/health`
- `GET /api/v1/warehouses`
- `POST /api/v1/warehouses`
- `GET /api/v1/warehouses/{warehouse_id}`
- `GET /api/v1/products`
- `POST /api/v1/products`
- `GET /api/v1/products/{product_id}`
- `GET /api/v1/inventory/stock`
- `GET /api/v1/inventory/movements`
- `POST /api/v1/inventory/movements`
- `GET /api/v1/inventory/summary`

La implementacion actual usa **persistencia en memoria** en `apps/api/app/db/session.py`. Esto fue intencional para cerrar primero el dominio, los contratos HTTP y las reglas de inventario antes de acoplar la API a una base de datos real.

### Base de datos

La base de datos ya tiene:

- referencia legible del modelo en `db/schema/initial-domain.sql`
- migracion versionada en `db/migrations/0001_inventory_mvp.sql`
- seed minima en `db/seeds/0001_inventory_mvp_seed.sql`

El esquema contempla:

- `warehouses`
- `products`
- `inventory_movements`
- `stock_levels`

## 2. Lo realizado

### Backend

Se implemento la separacion por dominio y responsabilidad:

- `router.py`
- `schemas.py`
- `service.py`
- `repository.py`

para los modulos:

- `warehouses`
- `products`
- `inventory`

Tambien se agrego:

- manejo centralizado de errores de dominio en `apps/api/app/core/errors.py`
- almacenamiento en memoria y estado compartido en `apps/api/app/db/session.py`
- pruebas backend en `apps/api/tests/test_api.py`

### Reglas de dominio ya cubiertas

- el stock cambia solo a traves del modulo de inventario
- una salida sin saldo suficiente es rechazada
- bodegas y productos tienen claves de negocio unicas a nivel de dominio
- los movimientos quedan registrados y el stock se recalcula a partir de ellos

### SQL / DB

Se actualizo el esquema base y se formalizo la primera migracion con:

- restricciones de unicidad
- llaves foraneas
- checks de cantidad
- catalogo controlado de tipos de movimiento
- indices base para consultas de inventario

### Documentacion

Se actualizaron documentos de:

- producto
- arquitectura
- operaciones
- `apps/api/README.md`
- `db/README.md`

para reflejar el estado real del trabajo.

## 3. Verificacion realizada

### API

Se ejecuto:

```powershell
python -m compileall app tests
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Resultado:

- compilacion correcta
- **5 pruebas OK**

Las pruebas cubren:

- healthcheck
- alta y listado de bodegas
- alta y listado de productos
- registro de movimientos
- lectura de stock
- rechazo por stock insuficiente

### DB

Se ejecuto una validacion de sanidad por script para confirmar que:

- la migracion crea las 4 tablas esperadas
- la migracion contiene los indices principales
- `initial-domain.sql` ya incluye `inventory_movements`
- la seed inserta bodega, producto, movimiento y stock

## 4. Lo faltante

### Pendiente principal

Conectar la API a una **persistencia real** reutilizando la separacion ya creada entre rutas, servicios y repositorios.

### Pendientes concretos

1. definir la estrategia de acceso a BD que se va a usar en `apps/api`
2. reemplazar repositorios en memoria por repositorios persistentes
3. ejecutar la migracion `0001_inventory_mvp.sql` en una base real
4. cargar la seed si se quiere validar rapido el flujo local
5. mantener exactamente las mismas reglas de dominio al pasar de memoria a BD
6. ampliar pruebas para:
   - duplicados de `code` y `sku`
   - filtros por `sku`
   - filtros por `movement_type`
   - consultas por rango de fechas

### Fuera de alcance por ahora

- `apps/web`
- `infra`
- autenticacion/autorizacion
- transferencias
- reposicion
- compras
- reportes avanzados

## 5. Riesgos actuales

1. la API aun no persiste datos entre reinicios porque usa memoria
2. la migracion existe, pero no fue aplicada ni probada contra un PostgreSQL real
3. el flujo transaccional actual esta resuelto con bloqueo en memoria, no con transacciones reales de BD
4. en pruebas aparece un `DeprecationWarning` de FastAPI/Starlette sobre Python 3.14, sin romper ejecucion

## 6. Recomendacion para retomar

Cuando se retome el trabajo, avanzar en este orden:

1. preparar acceso a BD real en `apps/api`
2. implementar repositorios persistentes para `warehouses`, `products` e `inventory`
3. ejecutar migracion y seed en entorno local
4. adaptar pruebas para correr contra la capa persistente
5. validar que el comportamiento observable de la API no cambie

## 7. Archivos clave para empezar rapido la proxima sesion

### API

- `apps/api/app/main.py`
- `apps/api/app/core/errors.py`
- `apps/api/app/db/session.py`
- `apps/api/app/modules/warehouses/`
- `apps/api/app/modules/products/`
- `apps/api/app/modules/inventory/`
- `apps/api/tests/test_api.py`

### DB

- `db/schema/initial-domain.sql`
- `db/migrations/0001_inventory_mvp.sql`
- `db/seeds/0001_inventory_mvp_seed.sql`

### Docs

- `docs/architecture/api-db-inventory-mvp.md`
- `docs/operations/api-db-validation-checklist.md`
- `docs/operations/api-db-handoff-2026-03-18.md`
