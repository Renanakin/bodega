# Multi-Equipo + Multi-Locación: Como escalar Bodegaje

> **Para:** el dueño del producto, el equipo tecnico, y futuros clientes.
> Explica como adaptar el sistema actual (single-tenant, multi-bodega)
> para soportar **multiples empresas/organizaciones** con bodegas en
> **distintas locaciones geograficas** (multi-region).
>
> **Audiencia:** tambien te interesa si sos una empresa con varias
> sucursales y queres ver el sistema en todas a la vez, o si queres
> revender el sistema a multiples clientes (modelo SaaS).

---

## Indice

1. [Estado actual: que SI y que NO soporta el sistema hoy](#1-estado-actual)
2. [3 modelos arquitectonicos para multi-equipo](#2-modelos-arquitectonicos)
3. [Modelo recomendado: multi-tenant (shared database)](#3-modelo-recomendado-multi-tenant)
4. [Plan de implementacion por fases](#4-plan-de-implementacion)
5. [Multi-locacion: como configurar bodegas remotas](#5-multi-locacion)
6. [Migracion de clientes existentes](#6-migracion-de-clientes-existentes)
7. [Costos de la solucion multi-tenant](#7-costos)
8. [Comparacion de los 3 modelos](#8-comparacion-de-modelos)
9. [Decision y siguientes pasos](#9-decision-y-siguientes-pasos)

---

## 1. Estado actual

El sistema actual **v1.0.0** ya soporta **multi-bodega** (varias bodegas
en una misma organización) y **multi-locacion LOGICA** (las bodegas
pueden tener direcciones en cualquier lugar del mundo). Pero **NO
soporta multi-empresa** (varios clientes independientes en la misma
instalacion).

### Que SI soporta (sin cambios)

| Capacidad | Como se usa | Limite |
|---|---|---|
| **Multiples bodegas** | Una organizacion con N bodegas (1 principal + N auxiliares + N boxes) | Sin limite duro. Probado con 8 bodegas en E2E. |
| **Multiples usuarios** | 1 admin + 1 supervisor + N operadores + N destino | 4 roles predefinidos |
| **Multiples proveedores** | 1 proveedor con N productos, OC, recepciones | Sin limite |
| **Multiples productos** | N productos con stock por bodega | Sin limite |
| **Solicitudes entre bodegas** | Aux pide a Principal, o Principal a Aux | Bidireccional |
| **OC con aprobacion publica** | Link por email al supervisor, sin login | Cada OC es unica |
| **Reportes consolidados** | `/reports/ejecutivo` agrega todas las bodegas | OK para 10-50 bodegas |
| **Auditoria cross-bodega** | Cada movimiento registra `warehouse_id` y `user_id` | OK |

### Que NO soporta (gaps)

| Gap | Impacto | Solucion |
|---|---|---|
| **Multi-tenant** (varias empresas en misma BD) | No se puede revender como SaaS. Cada cliente necesita su propio VPS. | Agregar `tenant_id` a todas las tablas + RLS |
| **Sincronizacion offline** (bodega sin internet) | Bodega rural sin conexion no puede operar | Replicacion local + sync periodica |
| **Multi-region** (latencia <100ms en LATAM) | VPS en EU = 200ms desde Chile | Multi-region con read replicas |
| **Permisos por bodega** (operador solo ve SU bodega) | Hoy un operador ve TODAS las bodegas | Agregar `warehouse_id` al JWT o session |
| **SLA contractual** (99.9% uptime) | Single VPS = single point of failure | Multi-AZ + load balancer |
| **Data residency** (datos en pais del cliente) | Cumplir con GDPR, Ley 19.628 (Chile), etc. | BD en region del cliente |

### Preguntas clave para decidir el modelo

Antes de elegir arquitectura, responder:

1. **Cuantos clientes/organizaciones** van a usar el sistema? (1, 10, 100, 1000?)
2. **Cuantas bodegas por cliente**? (1, 5, 50, 500?)
3. **Cual es la latencia maxima aceptable** entre operario y servidor? (50ms, 200ms, 1s?)
4. **Necesitan algunos clientes SU PROPIO servidor** (data residency)?
5. **Tienen bodegas en zonas sin internet confiable**? (camiones, barcos, faenas mineras, etc.)
6. **Cual es el modelo de negocio?** SaaS (varios clientes, $$ por mes) vs on-premise (1 cliente, licencia)?

---

## 2. Modelos arquitectonicos

### Modelo 1 — Single-Tenant (ESTADO ACTUAL)

**Que es:** cada cliente tiene su PROPIO servidor (VPS o on-premise).
Nada se comparte entre clientes. Es lo que tenes hoy.

```
Cliente A (HVM)              Cliente B (Frigosur)         Cliente C (Minera X)
+----------------+            +----------------+           +----------------+
| VPS dedicado   |            | VPS dedicado   |           | VPS dedicado   |
| bodega.cl      |            | frigosur.cl    |           | minerax.cl     |
| BD: bodega     |            | BD: frigosur   |           | BD: minerax    |
+----------------+            +----------------+           +----------------+
```

**Pros:**
- Aislamiento total (un cliente no afecta a otro)
- Data residency trivial (BD en pais del cliente)
- Modelo de negocio simple (licencia anual + soporte)
- Cumplimiento legal facil (Ley 19.628, GDPR)
- Sin cambios al codigo (es lo que hay hoy)

**Contras:**
- Costo por cliente: ~$5-30/mes (VPS) + tiempo de operacion
- Cuesta escalar a 100+ clientes (hay que operar 100 VPS)
- No hay cross-selling (no se pueden ofrecer servicios entre clientes)
- Reportes cross-cliente imposibles (no aplica, no es lo que se quiere)

**Ideal para:** 1-10 clientes grandes, on-premise, data residency estricta.

---

### Modelo 2 — Multi-Tenant con BD compartida (RECOMENDADO)

**Que es:** todos los clientes comparten UNA sola BD, separados por una
columna `tenant_id`. Es el modelo SaaS clasico (Salesforce, Slack, etc.).

```
                                [Internet]
                                    |
                                    v
                          +-----------------+
                          |   Cloudflare    | (CDN, WAF, DDoS, SSL)
                          +--------+--------+
                                   |
                                   v
                          +-----------------+
                          | Load Balancer  |  (ALB, Nginx, etc.)
                          | app.bodega.cl  |
                          +--------+--------+
                                   |
              +--------------------+--------------------+
              |                    |                    |
              v                    v                    v
      +-------------+      +-------------+      +-------------+
      | API node 1  |      | API node 2  |      | API node 3  |
      | (FastAPI)   |      | (FastAPI)   |      | (FastAPI)   |
      +------+------+      +------+------+      +------+------+
             |                    |                    |
             +--------------------+--------------------+
                                  |
                                  v
                        +-------------------+
                        |   PostgreSQL 17   |  <- RLS (Row Level Security)
                        |   + Read Replica  |     filtra por tenant_id
                        |   BD compartida    |
                        +-------------------+
                                  |
                                  v
                        +-------------------+
                        | Redis (sessions, |
                        | rate limit, cache)|
                        +-------------------+
```

**Cada tenant** (cliente/organizacion) tiene su `tenant_id` en TODAS las
tablas. Las queries filtran automaticamente por tenant via RLS o
middleware de SQLAlchemy.

**Pros:**
- Costo por cliente marginal ~$0.10/mes (comparten infra)
- Escalar a 1000+ clientes es trivial
- Cross-tenant analytics posibles (anonimizados)
- Un solo deploy, un solo upgrade
- Cumplimiento: backups centralizados, seguridad homogenea

**Contras:**
- Aislamiento debil: bug de RLS = leak cross-tenant
- Data residency dificil (todos en misma region fisica)
- Single point of failure: si la BD cae, caen todos
- Compliance complejo: auditoria por cliente, GDPR right-to-be-forgotten
- Customizacion limitada: todos ven la misma UI/features

**Ideal para:** SaaS B2B, 10-1000 clientes medianos, sin requisitos de data
residency estrictos, modelo de pricing por usuario/mes.

**Esfuerzo de implementacion:** **~80 horas de desarrollo** (3-4 semanas
para 1 dev). El sistema YA tiene la estructura multi-bodega, solo
falta agregar el concepto de tenant.

---

### Modelo 3 — Multi-Tenant con BD separada por cliente (HIBRIDO)

**Que es:** cada cliente tiene su PROPIA BD en el mismo servidor
Postgres (schemas separados). Aislamento fuerte pero single infra.

```
                                [Internet]
                                    |
                                    v
                          +-----------------+
                          |   Cloudflare    |
                          +--------+--------+
                                   |
                                   v
                          +-----------------+
                          |  API (FastAPI)  |  <- lee de la BD del tenant
                          |  schema routing |     segun el dominio o subdominio
                          +--------+--------+
                                   |
                  +----------------+----------------+
                  |                |                |
                  v                v                v
         +--------------+   +--------------+   +--------------+
         | BD HVM       |   | BD Frigosur  |   | BD Minera X |
         | (schema)     |   | (schema)     |   | (schema)     |
         | propio       |   | propio       |   | propio       |
         +--------------+   +--------------+   +--------------+
```

**Pros:**
- Aislamiento fuerte (cada cliente tiene su schema)
- Data residency: cada schema puede estar en region distinta
- Customizacion: clientes premium pueden tener features custom
- Backup por cliente: trivial, sin filtrar

**Contras:**
- Migraciones hay que correrlas N veces (1 por schema)
- Cross-tenant analytics requiere logica especial
- Costo de operacion mayor (mas conexiones, mas volumen)
- Complejidad de routing: el API debe saber que schema usar

**Ideal para:** SaaS B2B premium, 10-100 clientes que pagan bien, requisitos
de data residency moderados.

**Esfuerzo de implementacion:** **~120 horas** (4-6 semanas).

---

### Modelo 4 — Multi-Region / Federated

**Que es:** cada cliente grande o region geografica tiene su propio cluster
completo (API + BD). Replicacion async entre clusters. Es lo que usa
Walmart, Amazon, etc.

```
[LATAM]                                   [Europa]
+--------+                                +--------+
| Cluster|                                | Cluster|
| Mexico | <-- async replication -->      | Espana|
| Chile  |                                |        |
+--------+                                +--------+
     |                                        |
     +------- CDN/Anycast DNS ---------------+
```

**Pros:**
- Latencia <50ms en cualquier parte del mundo
- Compliance: datos en region del cliente
- Resiliencia: cluster caido no afecta a otros

**Contras:**
- Muy caro (~$200-500/mes por cluster)
- Complejidad operacional extrema
- Replicacion conflictiva (last-write-wins, CRDT, etc.)
- Requiere equipo DevOps dedicado

**Ideal para:** 100+ clientes, latencia <100ms requerida, presupuesto
empresarial, modelo enterprise.

**Esfuerzo de implementacion:** **300+ horas** (3-6 meses). NO para v1.0.

---

## 3. Modelo recomendado: Multi-Tenant (shared database)

Para Bodegaje v1.0 → v1.1 → v2.0, el modelo recomendado es el **multi-tenant
con BD compartida** (Modelo 2). Es el equilibrio correcto entre costo,
esfuerzo de implementacion y escalabilidad.

### 3.1 Cambios al modelo de datos

**Nueva tabla `tenants`:**

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) UNIQUE NOT NULL,        -- "hvm", "frigosur", "minerax"
    name VARCHAR(200) NOT NULL,              -- "Hipermercado VM"
    subdomain VARCHAR(100) UNIQUE,           -- "hvm.bodega.cl" (opcional)
    is_active BOOLEAN DEFAULT TRUE,
    plan VARCHAR(20) DEFAULT 'basic',        -- basic|pro|enterprise
    created_at TIMESTAMP DEFAULT NOW(),
    settings JSONB DEFAULT '{}'              -- config por tenant
);
```

**Agregar `tenant_id` a TODAS las tablas de dominio:**

```sql
ALTER TABLE warehouses ADD COLUMN tenant_id UUID REFERENCES tenants(id);
ALTER TABLE productos ADD COLUMN tenant_id UUID REFERENCES tenants(id);
ALTER TABLE users ADD COLUMN tenant_id UUID REFERENCES tenants(id);
-- ... y asi con ~15 tablas
```

**Reglas de aislamiento:**

1. **Row Level Security (RLS)** en Postgres: cada query automaticamente
   filtra por `tenant_id` del usuario actual.
2. **Tenant context** via `SET LOCAL app.current_tenant = '...'` en cada
   request (middleware que lee JWT).
3. **Foreign keys tenant-aware**: no se puede crear una solicitud
   entre bodegas de tenants distintos.

### 3.2 Cambios al codigo

**Middleware de tenant (nuevo archivo):**

```python
# apps/api/app/core/tenant_middleware.py
class TenantMiddleware:
    """Inyecta el tenant_id del usuario actual en cada request.
    
    Lee el JWT, extrae el tenant_id, y lo setea como session variable
    de Postgres para que RLS filtre automaticamente.
    """
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)
            # Extraer tenant del JWT (asumimos que el token ya esta validado)
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            tenant_id = decode_tenant_from_jwt(token)
            if tenant_id:
                # Settear en context de SQLAlchemy para que las queries
                # automaticamente filtren por tenant
                scope["state"]["tenant_id"] = tenant_id
        await self.app(scope, receive, send)
```

**Event listener de SQLAlchemy (nuevo):**

```python
# apps/api/app/db/tenant_events.py
from sqlalchemy import event

@event.listens_for(Session, "do_orm_execute")
def filter_by_tenant(execute_state):
    """Filtra automaticamente por tenant_id en cada query."""
    if not execute_state.is_select:
        return
    tenant_id = get_current_tenant_id()  # de contextvars
    if tenant_id is None:
        return  # superuser / admin
    for entity in execute_state.statement.column_descriptions:
        # Inyectar WHERE tenant_id = :tenant_id en cada query
        ...
```

**Modificacion al login:** el JWT ahora incluye `tenant_id`.

**Modificacion al signup:** nuevo endpoint `POST /auth/signup-tenant`
que crea un tenant + admin user en una sola operacion.

### 3.3 Como se ve desde el usuario

**Hoy (single-tenant):**
```
https://app.bodega.cl/
  -> Login (admin / admin12345)
  -> Ve 8 bodegas (HVM)
```

**Manana (multi-tenant):**

Opcion A — Subdominio por cliente:
```
https://hvm.bodega.cl/      -> login auto-detecta tenant por subdominio
https://frigosur.bodega.cl/  -> login auto-detecta tenant por subdominio
https://minerax.bodega.cl/   -> login auto-detecta tenant por subdominio
```

Opcion B — Login explicito:
```
https://app.bodega.cl/
  -> Form: "Email" + "Password" + (Tenant code opcional)
  -> Despues de login: redirige al dashboard del tenant
```

**Recomendado:** Opcion A (subdominio) porque:
- UX mas claro (el usuario sabe donde esta)
- Cloudflare maneja los subdominios con un solo cert wildcard
- No requiere que el usuario sepa el codigo del tenant
- Permite branding custom (`hvm.bodega.cl` con logo de HVM)

### 3.4 Estimacion de esfuerzo

| Componente | Esfuerzo | Notas |
|---|---|---|
| Modelo `Tenant` + migracion | 4h | Tabla + columna tenant_id en 15 tablas |
| Middleware de tenant | 8h | Lee JWT, setea context, integra con RLS |
| RLS en Postgres | 8h | Policies para cada tabla, testing exhaustivo |
| Modificar endpoints | 16h | Cada router verifica tenant antes de query |
| Frontend: detectar tenant | 8h | Subdominio + URL params |
| Tests cross-tenant | 16h | Aislamiento, intento de leak, permisos |
| Tests de migracion | 8h | Single → multi sin perder data |
| Documentacion + runbook | 8h | Manual multi-tenant |
| **TOTAL** | **~76h** (3-4 semanas) | 1 dev full-time |

---

## 4. Plan de implementacion

### Fase 1: Multi-tenant en codigo (Semanas 1-4)

1. **Semana 1:** Modelo `Tenant` + migracion 0017_add_tenants. Agregar
   `tenant_id` a 15 tablas.
2. **Semana 2:** Middleware de tenant + RLS. Testing de aislamiento.
3. **Semana 3:** Modificar routers existentes para inyectar tenant_id
   en cada query. Tests cross-tenant.
4. **Semana 4:** UI: detectar subdominio + branding. Deploy a staging.

**Entregable:** v1.1 con multi-tenancy funcional, deployed en staging,
testeado cross-tenant.

### Fase 2: Multi-locacion (Semanas 5-8)

1. **Semana 5:** Agregar campo `timezone` a bodegas y `tenant`. Cada
   bodega reporta timestamps en su zona horaria.
2. **Semana 6:** Latencia optimizada: VPS en region del cliente (o
   CDN/Cloudflare para assets estaticos).
3. **Semana 7:** Modo offline (opcional, MVP): bodega con SQLite local
   + sync periodica. Ver seccion 5.3.
4. **Semana 8:** Deploy a produccion + go-live con 1 cliente piloto.

**Entregable:** v1.2 con multi-locacion. 1 cliente real en produccion.

### Fase 3: Multi-region (opcional, v2.0+)

Solo si crece a >100 clientes en distintas geografias.

1. Read replicas en 2-3 regions (US East, EU West, AP Southeast)
2. DNS con GeoDNS (Cloudflare Load Balancing)
3. Replicacion asincrona de BD entre regions
4. Failover automatico con health checks

**Esfuerzo:** ~200h adicionales, 6-8 meses.

---

## 5. Multi-locacion

Hay 3 escenarios para "multiples equipos en distintas locaciones":

### 5.1 Escenario 1: Todas las bodegas online (CASO COMUN)

**Setup:** cada bodega tiene internet (4G, fibra, satelital) y se conecta
al servidor central. El operario usa la UI/API en tiempo real.

```
Bodega Santiago (Chile)    Bodega Lima (Peru)    Bodega Miami (USA)
     |                          |                       |
     +------- HTTPS ------------+-----------------------+
                |
                v
        +---------------+
        | VPS Frankfurt |
        | bodega.cl     |
        +---------------+
```

**Latencia esperada:**
- Chile ↔ Frankfurt: ~200ms (la UI se siente lenta)
- Peru ↔ Frankfurt: ~180ms
- USA ↔ Frankfurt: ~90ms (OK)

**Solucion:** **ubicar el VPS en region del cliente**. Hetzner tiene
datacenters en:
- Alemania (FSN1) — para Europa
- Finlandia (HEL1) — para Europa
- USA (ASH) — para Norteamerica
- Singapur (SIN) — para Asia

**Para LATAM:** no hay datacenter cerca. Opciones:
- Hetzner ASH (USA East, ~120ms desde Chile)
- DigitalOcean NYC3 (~120-150ms)
- AWS sa-east-1 (Sao Paulo, ~30-50ms desde Chile)
- Google Cloud southamerica-east1 (Santiago, <30ms!)

**Recomendado para LATAM:** **Google Cloud southamerica-east1 (Santiago)** o
**AWS sa-east-1 (Sao Paulo)** si los clientes son chilenos/peruanos.

### 5.2 Escenario 2: Multi-region con replicas

Si tenes clientes en 2-3 continentes y la latencia importa:

```
        [LATAM]                    [Europa]                  [Asia]
     +---------+               +---------+              +---------+
     | Read    |  <-- sync -->  | Primary | <-- sync --> | Read    |
     | Replica |               | Postgres|              | Replica |
     | (Chile) |               | (EU)    |              | (Sing)  |
     +---------+               +---------+              +---------+
                                     |
                                  [Writes]
                              (solo en Primary)
```

**Setup:**
- 1 Primary (region del cliente mas grande)
- N Read Replicas (otras regions)
- DNS con GeoDNS (Cloudflare Load Balancing, $5/mes)
- Replicacion asincrona (Postgres streaming replication)

**Costo:** $200-500/mes (1 primary + 2 replicas en cloud).

**Esfuerzo:** ~100h adicionales. v2.0+.

### 5.3 Escenario 3: Bodegas con conectividad intermitente (MODO OFFLINE)

**Caso de uso:** bodegas en zonas rurales, barcos, faenas mineras, o
camiones de reparto. La conexion a internet es intermitente o lenta.

**Setup:** cada bodega tiene su PROPIA BD local (SQLite) que sincroniza
con el servidor central cuando hay conexion.

```
Bodega rural (sin internet)
+------------------+
| BD local SQLite |
| bodegaje.db     |
| replica local   |
+------------------+
        |
        | (cuando hay internet, cada 5 min)
        v
   Sync bidireccional
        |
        v
+------------------+
| Servidor central|
| Postgres        |
+------------------+
```

**Implementacion (basica, ~40h):**
1. BD local SQLite en la bodega
2. Cola de cambios (operaciones pendientes de sync) en JSONL
3. Worker que sube la cola al servidor cuando hay internet
4. Conflict resolution: last-write-wins por timestamp + user_id

**Implementacion (avanzada, ~200h):**
1. Usar **CouchDB** o **PouchDB** (sync bidireccional nativo)
2. O usar **ElectricSQL** (sync diferencial)
3. CRDT para resolver conflictos automaticamente

**Recomendado para v1.x:** NO implementar offline. Mejor pedirle al
cliente que tenga internet. Bodega sin internet hoy no es viable
para nuestro sistema (requiere conexion en tiempo real para validar
stock).

**Workaround temporal:** deploy on-premise del servidor en la bodega
rural, con sync cuando vuelve a tener internet.

---

## 6. Migracion de clientes existentes

### 6.1 Si tenes 1 cliente hoy (HVM)

**Antes:** todos los datos estan en la BD unica.
**Despues:** hay que crear el tenant HVM y asignar todos los datos
existentes a ese tenant.

**SQL de migracion:**

```sql
-- 1. Crear el tenant inicial
INSERT INTO tenants (id, code, name, is_active, plan)
VALUES ('00000000-0000-0000-0000-000000000001', 'hvm', 'Hipermercado VM', TRUE, 'pro');

-- 2. Asignar todos los datos existentes al tenant HVM
UPDATE warehouses SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE productos SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
-- ... (repetir para cada tabla)
-- O usar un script Python que itere todas las tablas

-- 3. Hacer tenant_id NOT NULL despues de la asignacion
ALTER TABLE warehouses ALTER COLUMN tenant_id SET NOT NULL;
-- ... (repetir para cada tabla)
```

### 6.2 Si tenes varios clientes en servidores separados

**Antes:** Cliente A en VPS 1, Cliente B en VPS 2.
**Despues:** consolidar a 1 servidor con multi-tenant.

**Pasos:**
1. Hacer backup de cada VPS actual
2. Crear el tenant correspondiente en el nuevo servidor
3. Importar el backup al schema/tenant del nuevo servidor
4. Apuntar los DNS de cada cliente al nuevo servidor
5. Verificar que todo funciona
6. Dar de baja los VPS viejos (despues de 1 mes de estabilidad)

**Herramienta:** usar `pg_dump` + `pg_restore` por cliente:

```bash
# Exportar cliente A
docker exec bodegaje-db pg_dump -U bodegaje -d bodegaje \
    --no-owner --no-privileges --inserts \
    -t warehouses -t productos -t users -t ... \
    > /tmp/cliente_a.sql

# Importar en el nuevo servidor multi-tenant
# (con el tenant_id ya seteado)
psql -U bodegaje -d bodegaje -f /tmp/cliente_a.sql
```

---

## 7. Costos de la solucion multi-tenant

### Escenario: 50 clientes (SaaS pequeno)

| Concepto | Costo/mes |
|---|---|
| **VPS Primary** (Hetzner CCX23, 16 vCPU, 32 GB) | $63 |
| **BD gestionada** (Hetzner Managed Postgres 8, con backups) | $63 |
| **Redis gestionado** (Hetzner Managed Redis 4) | $20 |
| **Read Replica** (Hetzner CCX13, 8 vCPU) | $32 |
| **Backups S3** (200 GB) | $2 |
| **Cloudflare Pro** (WAF avanzado) | $20 |
| **Email SES** (50K emails/mes) | $5 |
| **Sentry** (team plan) | $26 |
| **Uptime Robot Pro** (1 min checks) | $7 |
| **TOTAL** | **~$238/mes** |

**Por cliente:** $238 / 50 = **~$4.80/mes por cliente** (increible).

**Pricing sugerido al cliente:** $50-200/mes por cliente (margen 10-40x).

### Escenario: 500 clientes (SaaS mediano)

| Concepto | Costo/mes |
|---|---|
| **Multi-region** (3 read replicas, primary US-East) | $800 |
| **BD gestionada** (RDS db.r5.xlarge, 100 GB, multi-AZ) | $1200 |
| **Redis ElastiCache** (cache.r5.large) | $300 |
| **S3 backups** (1 TB, lifecycle a Glacier) | $10 |
| **Cloudflare Pro** | $20 |
| **Email SES** (500K emails/mes) | $50 |
| **Sentry Business** | $80 |
| **PagerDuty** (1 user) | $21 |
| **TOTAL** | **~$2,481/mes** |

**Por cliente:** $2,481 / 500 = **~$5/mes por cliente**.

**Pricing sugerido:** $50-200/mes por cliente. Margen 10-40x.

### Escenario: 5000+ clientes (SaaS grande)

Aqui ya necesitas migrar a Cloud (AWS/GCP) con servicios gestionados
completos y equipo DevOps dedicado. Costo: **$5,000-15,000/mes**.
Pricing por cliente: $30-100/mes. Margen 50-300x.

---

## 8. Comparacion de modelos

| Criterio | Single-Tenant (hoy) | Multi-Tenant BD compartida | Multi-Tenant BD separada | Multi-Region |
|---|---|---|---|---|
| **Esfuerzo de implementacion** | 0h (ya esta) | ~80h (3-4 sem) | ~120h (4-6 sem) | ~300h (3-6 meses) |
| **Costo/cliente bajo escala** | $5-30 | $0.10-5 | $0.50-10 | $1-5 |
| **Costo/cliente alto escala** | $5-30 (no escala) | $1-5 | $2-10 | $0.50-2 |
| **Max clientes sin degradar** | 10-20 VPS | 1000+ | 500+ | 10,000+ |
| **Data residency** | Trivial (cada VPS en su pais) | Media (todos en 1 region) | Facil (BD por cliente) | Facil |
| **Aislamiento** | Total | Medio (RLS) | Alto (BD propia) | Total |
| **Complejidad operacional** | Alta (N VPS) | Baja (1 server) | Media (N schemas) | Muy alta |
| **Latencia LATAM** | Depende del VPS | ~30-50ms (region LATAM) | ~30-50ms | <30ms |
| **Cumplimiento GDPR** | Facil | Medio (BD compartida) | Facil | Facil |
| **Ideal para** | 1-10 clientes on-premise | 10-1000 SaaS | 10-100 SaaS premium | 1000+ enterprise |

---

## 9. Decision y siguientes pasos

### Decision recomendada por fase del producto

| Fase | Modelo | Justificacion |
|---|---|---|
| **Hoy (v1.0)** | **Single-Tenant** (ya esta) | Empezar simple, validar producto |
| **3-6 meses** (v1.1) | **Multi-Tenant BD compartida** | Cuando tengas 3+ clientes, consolidar |
| **12+ meses** (v2.0) | **Multi-Region** con replicas | Cuando tengas 100+ clientes en varias geografias |
| **24+ meses** (v3.0) | **Hybrid** (multi-tenant + BD separada para premium) | Cuando tengas clientes enterprise que paguen bien |

### Plan inmediato (esta semana)

1. **Decidir** con el equipo: cuantos clientes target a 12 meses?
   - Si <10: quedarse con single-tenant (no cambiar)
   - Si 10-100: implementar multi-tenant (plan 80h)
   - Si >100 y multi-region: contactar equipo DevOps dedicado

2. **Si van con multi-tenant:**
   - Crear ticket con los 4 entregables de la Fase 1
   - Asignar 1 dev full-time por 3-4 semanas
   - Definir fecha de corte (ej: fin de mes)

3. **Mientras tanto (single-tenant), optimizar para multi-locacion:**
   - Migrar el VPS a region LATAM (Google Cloud southamerica-east1)
   - Latencia mejorara de 200ms a 30-50ms
   - Costo: ~$30-50/mes (similar)

4. **Documentar las decisiones** en `docs/operations/DEPLOY_DECISIONS.md`:
   - Por que elegimos X modelo
   - Que alternativas consideramos
   - Cuando revisaremos la decision

### Costo de NO hacerlo

- Si te quedas single-tenant con 100 clientes: $500-3000/mes en VPS.
  Operar 100 VPS = 1-2 personas dedicadas full-time.
- Si te quedas single-tenant con 1000 clientes: IMPOSIBLE operarlo.
  Hay que migrar a multi-tenant.

### Proximos pasos

1. **Esta semana:** decision de modelo (single vs multi-tenant)
2. **Mes 1:** si multi-tenant, implementar Fase 1 (modelo + middleware)
3. **Mes 2:** Fase 2 (modificar routers + RLS)
4. **Mes 3:** Testing cross-tenant + go-live con 2do cliente
5. **Mes 6:** Evaluar si necesitan multi-region

### Contacto

- **Slack:** #bodega-dev
- **Email:** dev@bodega.cl
- **Documentacion:** `docs/PROPUESTA_PRODUCCION.md` + `docs/DEPLOY.md`
- **Issues GitHub:** https://github.com/Renanakin/bodega/issues

---

## Anexo: Como agregar un nuevo cliente en el modelo multi-tenant

Una vez implementado el multi-tenant, agregar un nuevo cliente es
1 sola operacion:

```bash
# 1. Crear el tenant via API (admin only)
curl -X POST https://api.bodega.cl/admin/tenants \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -d '{
        "code": "frigosur",
        "name": "Frigosur SpA",
        "subdomain": "frigosur.bodega.cl",
        "plan": "pro"
    }'
# Devuelve: {"tenant_id": "uuid", "admin_token": "..."}

# 2. El admin del nuevo cliente puede loguearse con ese token
# y empezar a crear sus bodegas, productos, usuarios, etc.

# 3. (Opcional) Configurar Cloudflare:
#    - Crear CNAME frigosur.bodega.cl -> app.bodega.cl
#    - Habilitar proxy (CDN + WAF)
```

**Onboarding de cliente:**

| Paso | Tiempo | Quien lo hace |
|---|---|---|
| 1. Contrato firmado | 1-3 dias | Comercial |
| 2. Crear tenant en el sistema | 5 min | Admin (vos) |
| 3. Asignar subdominio en Cloudflare | 5 min | Admin (vos) |
| 4. Cargar catalogos (productos, proveedores) | 1-2h | Operador del cliente |
| 5. Crear usuarios (admin, supervisor, ops) | 15 min | Admin del cliente |
| 6. Capacitar a los operadores | 2-4h | Vos o el supervisor |
| 7. Go-live con 1 bodega piloto | 1 dia | Operadores |
| 8. Expansion al resto de bodegas | 1-2 semanas | Operadores |
| **TOTAL** | **1-2 semanas** | Mixto |

---

**Anexo: comandos utiles para el operador multi-tenant**

```bash
# Ver todos los tenants
docker exec bodegaje-db psql -U bodegaje -d bodegaje \
    -c "SELECT code, name, plan, is_active, created_at FROM tenants;"

# Ver la cantidad de bodegas por tenant
docker exec bodegaje-db psql -U bodegaje -d bodegaje \
    -c "SELECT t.code, COUNT(w.id) AS n_bodegas FROM tenants t LEFT JOIN warehouses w ON w.tenant_id = t.id GROUP BY t.code;"

# Ver el tamano de la BD por tenant (requiere extension pgstattuple o query manual)
docker exec bodegaje-db psql -U bodegaje -d bodegaje <<EOF
SELECT t.code,
       pg_size_pretty(SUM(pg_total_relation_size(c.oid))::bigint) AS total_size
FROM tenants t
JOIN pg_class c ON c.relname = 'warehouses'
WHERE c.relname IN ('warehouses', 'productos', 'users', 'solicitudes_recarga', 'ordenes_compra', 'receipts', 'inventory_movements')
GROUP BY t.code;
EOF

# Backup de UN SOLO tenant (usando filtro WHERE en pg_dump)
docker exec bodegaje-db pg_dump -U bodegaje -d bodegaje \
    --where="tenant_id = '00000000-0000-0000-0000-000000000001'" \
    -t inventory_movements -t solicitudes_recarga -t ordenes_compra -t receipts \
    > /tmp/tenant_hvm.sql
```
