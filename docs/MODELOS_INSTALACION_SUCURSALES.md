# 2 Modelos de Instalación para Multi-Sucursal

> **Para:** el dueño del producto, el equipo tecnico, y futuros clientes
> con **multiples sucursales** (1 bodega principal + N sucursales).
>
> **Tu pedido:** comparar 2 formas de instalar el sistema:
>
> 1. **Modelo Distribuido:** 1 BD local en la sucursal principal + el
>    software instalado en cada PC/sucursal. Las sucursales se conectan
>    a la BD local de la principal (o trabajan offline y sincronizan).
>
> 2. **Modelo SaaS Multi-Empresa:** todo en la nube, multi-tenant.
>    Cada empresa cliente tiene su "espacio" en la misma instalación.
>    Las bodegas son "sucursales" dentro de cada empresa.
>
> **Lee esto de arriba a abajo** y elegi el modelo que mejor se adapte
> a tu operacion.

---

## Indice

1. [Tu pedido, contestado en 30 segundos](#1-tu-pedido)
2. [Modelo 1: Distribuido (BD local + software instalado)](#2-modelo-1)
3. [Modelo 2: SaaS Multi-Empresa (todo en cloud)](#3-modelo-2)
4. [Comparacion directa de los 2 modelos](#4-comparacion)
5. [Casos de uso para cada modelo](#5-casos-de-uso)
6. [Costos por modelo](#6-costos)
7. [Hibrido: ambos modelos a la vez](#7-hibrido)
8. [Como elegir el modelo correcto](#8-como-elegir)
9. [Decision y siguientes pasos](#9-decision-y-siguientes-pasos)

---

## 1. Tu pedido, contestado en 30 segundos

> *"1 BD local, el software se instala en pc o se asigna un multiempresa
> web, ve las 2 formas, bodega principal, y sucursales se conectan a la
> bd local que esta en la sucursal principal o puede ser todo cloud"*

**Interpretacion:** tenes una red de **multiples sucursales** (1 principal + N)
y queres ver 2 arquitecturas posibles:

| # | Modelo | Tu situacion |
|---|---|---|
| **1** | **Distribuido (on-premise + red local)** | BD local en la principal, software instalado en PCs de cada sucursal, conexiones por LAN/VPN |
| **2** | **SaaS Multi-Empresa (cloud)** | Todo en la nube, 1 sola instalacion sirve a varias empresas-clientes, cada una con sus sucursales |

**Mi recomendación depende de cuanto queres vender:**

- **Una sola empresa con tus sucursales** → **Modelo 1** (Distribuido)
  - Costo inicial mas alto, costo operativo mas bajo a largo plazo
  - Control total de los datos
  - Si queres revender a varias empresas → migrar a Modelo 2 despues

- **Vender a varias empresas** (modelo SaaS, una PyME con varias sucursales es 1 "empresa") → **Modelo 2** (SaaS)
  - Costo inicial bajo, costo operativo bajo por cliente
  - 1 sola instalacion, N empresas usan la misma
  - Si tienes solo 1 cliente → empezar con Modelo 1 simple, migrar a Modelo 2 cuando crezcas

**Si no querés decidir ahora:** el sistema actual (v1.0) ya soporta
multi-bodega (varias bodegas en 1 sola organización). Empezás con 1 sola
empresa en la nube, y cuando necesites multi-tenant, agregás una columna
`tenant_id` (ver `docs/MULTI_EQUIPO_MULTI_LOCACION.md`, ~80h de trabajo).

---

## 2. Modelo 1: Distribuido (BD local + software instalado)

### Concepto

Cada empresa tiene su PROPIO servidor. La BD vive en la **sucursal
principal** y el software se instala en las PCs de cada sucursal
(instalado como app de escritorio o via navegador). Las sucursales se
conectan a la BD de la principal por LAN o VPN.

### Diagrama de arquitectura

```
+================================================================+
|                    EMPRESA "HVM"                                |
|                  (1 sola organizacion)                          |
+================================================================+

+-------------------+         +-------------------+
|  SUCURSAL         |         |  SUCURSAL         |
|  PRINCIPAL         |         |  SANTIAGO         |
|  (Casa matriz)     |         |  (Sucursal 1)     |
|                   |         |                   |
|  +-------------+   |         |  +-------------+   |
|  | SERVIDOR    |   |         |  | PC operario |   |
|  | PRINCIPAL   |<--+         |  | (navegador) |   |
|  | (Mini PC)   |   |         |  | o app       |   |
|  +-------------+   |         |  | desktop)    |   |
|  | Postgres 17 |   |         |  +-------------+   |
|  | (la BD)     |   |         |                   |
|  +-------------+   |         +-------------------+
|  | Redis       |   |                 |
|  +-------------+   |                 | LAN / VPN
|  | API + Web   |   |                 | (red privada)
|  +-------------+   |                 v
|                   |         +-------------------+
+-------------------+         |  SUCURSAL         |
        |                   |  VALPARAISO        |
        |                   |  (Sucursal 2)     |
        | LAN / VPN         |                   |
        v                   |  +-------------+   |
+-------------------+         |  | PC operario |   |
|  SUCURSAL         |         |  +-------------+   |
|  CONCEPCION       |         +-------------------+
|  (Sucursal 3)     |
|                   |   <-- opcion 1: software instalado en PC
|  +-------------+   |   <-- opcion 2: navegador web al servidor principal
|  | PC operario |   |
|  +-------------+   |
+-------------------+
```

### Como se instala

**Opcion 1A: Software instalado en cada PC (cliente pesado)**

```
+--- PC Operario (en la sucursal) ---+
| Windows 10/11                     |
| +-----------------------------+   |
| | App de escritorio            |   |
| | (Electron o similar)        |   |
| | - Pantalla login            |   |
| | - Formularios de stock      |   |
| | - Reportes                   |   |
| +-----------------------------+   |
| | Backend: API REST            |   |
| | (corre local o remoto)      |   |
| +-----------------------------+   |
| | BD: Postgres (local)        |   |
| | o conecta a BD principal    |   |
| | por VPN                     |   |
| +-----------------------------+   |
+----------------------------------+
```

- Cada PC tiene la app instalada (descarga de un `.exe` o `.dmg`)
- La app se conecta a la BD de la principal por LAN/VPN
- Funciona offline si la BD esta en local (cada PC con su copia)
- **Pros:** funciona sin internet, baja latencia
- **Contras:** actualizar la app en N PCs es tedioso, soporte es dificil

**Opcion 1B: Software via navegador (cliente liviano, RECOMENDADO)**

```
+--- PC Operario (en la sucursal) ---+
| Windows 10/11                     |
| +-----------------------------+   |
| | Navegador (Chrome/Edge)     |   |
| | https://app.bodega.local    |   |
| | o http://192.168.1.100      |   |
| +-----------------------------+   |
| | Backend: API REST en el     |   |
| | servidor de la principal    |   |
| +-----------------------------+   |
| | BD: Postgres en la principal|   |
| | (accede por LAN/VPN)       |   |
| +-----------------------------+   |
+----------------------------------+
```

- Cada PC solo necesita un navegador moderno
- El software (UI + API + BD) corre **solo en la principal**
- Las sucursales acceden via LAN (10-50ms) o VPN (30-100ms)
- **Pros:** actualizar el software es 1 sola vez, soporte centralizado
- **Contras:** si la principal cae, todas las sucursales caen

**Opcion 1C: BD distribuida con sincronizacion (AVANZADO)**

```
+--- Sucursal 1 ---+        +--- Sucursal Principal ---+
| BD local        |<------>| BD local + replica        |
| (SQLite o       | sync   | (Postgres)               |
|  Postgres)      |period. |                          |
+-----------------+        +--------------------------+
                                     |
                                     v
                             +---------------+
                             | Otras          |
                             | sucursales     |
                             +---------------+
```

- Cada sucursal tiene su PROPIA copia local de la BD
- Sincronizacion periodica (cada 5-15 min) con la principal
- Funciona offline (cada sucursal es autonoma)
- **Pros:** maxima disponibilidad, baja latencia
- **Contras:** conflictos de sincronizacion, complejidad alta

### Como se conectan las sucursales a la BD local de la principal

**Opcion A: LAN directa (CASO COMUN, sin internet)**

```
[Sucursal 1] ----LAN----[Router]--[Switch]--[Servidor Principal]
[Sucursal 2] ----LAN----|             |        (BD aqui)
[Sucursal 3] ----LAN----|             |
```

- Todas las sucursales estan en la misma red fisica (mismo edificio o campus)
- Latencia: <5ms
- Si la red se cae, todo se cae (a menos que uses opcion 1C)

**Opcion B: VPN (CASO COMUN, sucursales en distintas ciudades/países)**

```
[Sucursal Santiago] ---internet---[VPN Tunnel]---internet---[Sucursal Lima]
   (cliente VPN)                                         (servidor VPN)
                                                          |
                                                          v
                                                  [Servidor Principal]
                                                  (BD aqui)
```

- WireGuard o Tailscale (ver `docs/INTEGRACION_REMOTA_Y_LOCAL.md`)
- Todas las sucursales se "ven" como si estuvieran en la misma LAN
- Latencia: 15-50ms (depende de la calidad del internet)
- **Pros:** segura (cifrada), facil de mantener
- **Contras:** si internet cae, todo se cae

**Opcion C: Cloudflare Tunnel (RECOMENDADO si tenes internet)**

```
[Sucursal 1] ---internet---[Cloudflare Edge]---internet---[Servidor Principal]
   (cloudflared)                                  (cloudflared daemon)
```

- Como el Modelo B de la propuesta anterior
- No requiere IP publica fija
- Mas facil de configurar que VPN
- **Pros:** no abrir puertos, automatico, gratis
- **Contras:** depende de Cloudflare

### Costo del Modelo 1 (Distribuido)

**Opcion 1B (cliente liviano via navegador) — RECOMENDADO**

| Concepto | Bajo (3 sucursales) | Medio (10 sucursales) | Alto (30 sucursales) |
|---|---|---|---|
| Servidor principal (Mini PC Beelink EQ12) | $300 (inicial) | $500 (mejor server) | $1,500 (rack server) |
| 1 PC por sucursal | $400 cada uno (3 × $400) | $400 cada uno (10 × $400) | $400 cada uno (30 × $400) |
| Red local (router, switch, cables) | $200 (incluido en oficina) | $500 (10 sucursales) | $1,500 (30 sucursales) |
| VPN / Cloudflare Tunnel | $0 (Cloudflare Free) | $0 | $0 |
| **TOTAL inicial** | **$1,700** | **$5,000** | **$15,000** |
| **TOTAL mensual** | **$0-5** (electricidad) | **$0-20** | **$0-50** |

**TCO a 3 años (10 sucursales):** $5,000 inicial + $720 (36 × $20) = **$5,720**

---

## 3. Modelo 2: SaaS Multi-Empresa (todo en cloud)

### Concepto

Una sola instalacion del sistema en la nube sirve a **multiples empresas-clientes**.
Cada empresa tiene su "espacio" aislado (sus bodegas, sus usuarios, su data).
Las sucursales de cada empresa son "bodegas" dentro de su tenant.

### Diagrama de arquitectura

```
                                 [Internet]
                                     |
                                     v
                          +-------------------+
                          |   Cloudflare      | (CDN, WAF, DDoS, SSL)
                          | app.bodega.cl     |
                          +---------+---------+
                                    |
                                    v
                          +-------------------+
                          | Load Balancer    |
                          +---------+---------+
                                    |
                +-------------------+-------------------+
                |                   |                   |
                v                   v                   v
        +-------------+      +-------------+      +-------------+
        | API Node 1  |      | API Node 2  |      | API Node 3  |
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
                          | Redis 8           | (cache, sessions, rate limit)
                          +-------------------+

================================================================
EMPRESAS CLIENTES (cada una es un "tenant" aislado)
================================================================

+--- Tenant 1: HVM (Hipermercado VM) ---+
|                                       |
|  +-----------------+                   |
|  | Sucursal 1      | (Bodega Principal)|
|  | BOD-PPAL-001    | <- UUID hvm-001   |
|  +-----------------+                   |
|  +-----------------+                   |
|  | Sucursal 2      | (Bodega Aux)      |
|  | BOD-AUX-001     | <- UUID hvm-002   |
|  +-----------------+                   |
|  +-----------------+                   |
|  | Sucursal 3      | (Bodega Aux)      |
|  | BOD-AUX-002     | <- UUID hvm-003   |
|  +-----------------+                   |
+---------------------------------------+

+--- Tenant 2: Frigosur (otro cliente) ---+
|                                         |
|  +-----------------+                   |
|  | Sucursal 1      | (Bodega Principal)|
|  | BOD-PPAL-001    | <- UUID frigo-001 |
|  +-----------------+                   |
|  +-----------------+                   |
|  | Sucursal 2      | (Bodega Aux)      |
|  | BOD-AUX-001     | <- UUID frigo-002 |
|  +-----------------+                   |
+---------------------------------------+

+--- Tenant 3: Minera X (otro cliente) ---+
| ... y asi N clientes                 |
+---------------------------------------+
```

### Como funciona

1. **1 sola instalacion** del sistema en la nube (VPS o cloud)
2. **1 sola BD** con **Row Level Security (RLS)** en Postgres que filtra
   automaticamente por `tenant_id`
3. **Cada empresa cliente** tiene su `tenant_id` en todas las tablas
4. **Subdominios** por cliente: `hvm.bodega.cl`, `frigosur.bodega.cl`, etc.
5. **Las sucursales** de cada cliente son bodegas dentro de su tenant
6. **Cada cliente** ve solo SUS bodegas, SUS usuarios, SU data
7. **El operador del SaaS** (vos) ve todos los tenants, estadisticas, billing

### Como se diferencian del Modelo 1

| Aspecto | Modelo 1 (Distribuido) | Modelo 2 (SaaS) |
|---|---|---|
| Instalacion | 1 por cliente (N instalaciones) | 1 sola para todos los clientes |
| BD | 1 por cliente | 1 sola, compartida con RLS |
| Hardware | 1 servidor por cliente (en su oficina) | 1 servidor cloud compartido |
| Costo por cliente | $300-500 (hardware por cliente) | $5-10 (marginal, mismo VPS) |
| Mantenimiento | El cliente opera su servidor | Vos operas todo centralizadamente |
| Personalizacion | Cada cliente puede customizar | Todos usan la misma version |
| Data residency | Facil (cada cliente en su oficina) | Media (todos en misma region) |

### Costo del Modelo 2 (SaaS)

**Una sola instalacion para muchos clientes:**

| Concepto | Bajo (10 clientes) | Medio (50 clientes) | Alto (500 clientes) |
|---|---|---|---|
| VPS / Cloud (compartido) | $10/mes (CAX21) | $63/mes (Hetzner CCX23) | $800/mes (3 read replicas) |
| BD gestionada | $15/mes (Hetzner) | $63/mes (Hetzner Postgres 8) | $1,200/mes (RDS multi-AZ) |
| Redis | $5/mes (pequeno) | $20/mes (Hetzner Redis 4) | $300/mes (ElastiCache) |
| Cloudflare Pro | $20/mes | $20/mes | $20/mes |
| Backups S3 | $0.20/mes | $2/mes | $10/mes |
| Email | $0 (Brevo) | $5/mes (SES) | $50/mes (SES) |
| Sentry | $0 (free) | $26/mes (team) | $80/mes (business) |
| **TOTAL mensual** | **$50/mes** | **$199/mes** | **$2,460/mes** |
| **Costo por cliente** | **$5/mes** | **$4/mes** | **$4.92/mes** |
| **Pricing sugerido al cliente** | $50-200/mes | $50-200/mes | $30-100/mes |
| **Margen** | 10-40x | 12-50x | 6-20x |

**TCO a 3 años (50 clientes, con 30% margen):**
- Setup inicial (desarrollo multi-tenant): $5,000 (ver `docs/MULTI_EQUIPO_MULTI_LOCACION.md`)
- Operativo: $199 × 36 = $7,164
- **Total: $12,164**
- **Por cliente: $243/año = $20/mes** (a precio de venta)
- **Margen bruto a $100/mes por cliente: 80%**

---

## 4. Comparacion directa de los 2 modelos

| Criterio | Modelo 1 (Distribuido) | Modelo 2 (SaaS) |
|---|---|---|
| **Cantidad de instalaciones** | 1 por cliente (N total) | 1 sola para todos |
| **Hardware** | 1 servidor por cliente | 1 servidor cloud compartido |
| **Costo inicial por cliente** | $300-500 | $0 (marginal) |
| **Costo mensual por cliente** | $0-5 (electricidad) | $5-10 (compartido) |
| **Costo de setup para N clientes** | $300-500 × N | $0 (ya esta deployado) |
| **Operacion** | Cada cliente opera el suyo | Vos operas todo |
| **Personalizacion** | Alta (cada cliente custom) | Baja (todos usan la misma) |
| **Data residency** | Facil (BD en su oficina) | Media (todos en region cloud) |
| **Latencia LAN** | <5ms (en la oficina) | 30-50ms (cloud) |
| **Latencia entre sucursales** | 10-50ms (LAN/VPN) | 30-50ms (cloud) |
| **Funciona sin internet** | Si (si usas opcion 1C) | NO |
| **Actualizar el software** | N actualizaciones (1 por cliente) | 1 sola actualizacion |
| **Soporte tecnico** | Complejo (N instalaciones) | Simple (1 instalacion) |
| **Escalar a 100 clientes** | Cuesta $30,000-50,000 en hardware | Cuesta $0 marginal (compartido) |
| **Ideal para** | 1 empresa, 1-10 sucursales, internet inestable | Multiples empresas, 1-100+ sucursales cada una |
| **Complejidad inicial** | Alta (instalar N veces) | Alta (multi-tenant en codigo) |
| **Complejidad operativa** | Media (N servidores) | Baja (1 servidor) |
| **Vendor lock-in** | Cero (es tu codigo) | Bajo (vps + cloud) |
| **Tiempo de setup del 1er cliente** | 1-2 dias (instalar en su oficina) | 5 min (crear tenant via API) |
| **Tiempo de setup del 10mo cliente** | 1-2 dias (repetir) | 5 min (mismo script) |

---

## 5. Casos de uso para cada modelo

### Modelo 1 (Distribuido) — ideal para:

- **Una sola empresa** con 1-20 sucursales que quiere control total
- **Empresa con internet inestable** (sucursales rurales, faenas)
- **Empresa con requisitos de compliance estricto** (banco, gobierno, defensa)
- **Empresa que no quiere depender de un proveedor cloud**
- **Empresa con personal de IT** que puede mantener servidores
- **Empresa que va a estar muchos años** y quiere controlar su stack

**Ejemplos:**
- Hipermercado VM con 8 sucursales en Chile (cloud + 8 PCs en cada sucursal)
- Distribuidora de bebidas con 5 sucursales en Chile y Peru
- Frigosur con 1 oficina central + 3 frigorificos distribuidos

### Modelo 2 (SaaS) — ideal para:

- **Vos queres VENDER el sistema** a multiples empresas
- **Multiples empresas** (PyME) que no quieren operar infra
- **Empresa con 1-3 sucursales** que prefiere pagar $$ por mes
- **Crecimiento rapido**: agregar 10 clientes/mes no requiere 10 instalaciones
- **Modelo de negocio recurrente** (SaaS) en vez de licencia unica
- **Vos tenes equipo de DevOps** que opera el cluster

**Ejemplos:**
- 50 PyMEs en LATAM con 1-3 sucursales cada una
- Cadenas de tiendas pequenas (5-10 locales por cadena)
- Distribuidores regionales
- Empresas emergentes que prefieren OpEx vs CapEx

### Hibrido (Modelo 1 + 2) — casos especiales

- **Vos** operas el SaaS (Modelo 2) para 50+ clientes, pero
  **1 cliente enterprise** quiere su propio servidor dedicado
  (Modelo 1) por compliance. Vos le vendes el on-premise como
  "Enterprise Plan" a $2000/mes.
- **Multi-region**: tu SaaS tiene servidores en Chile, USA y Europa
  (Modelo 2) pero para clientes en zonas sin internet, ofreces
  instalacion on-premise sincronizada con la nube (Modelo 1C).

---

## 6. Costos por modelo

### Tabla comparativa de costos a 3 años

**Asumamos 10 sucursales de UNA sola empresa (no SaaS):**

| Concepto | Modelo 1 (Distribuido) | Modelo 2 (SaaS para 1 empresa) |
|---|---|---|
| Setup inicial | $4,000 (10 sucursales + servidor central) | $50 (VPS + dominio) |
| Costo mensual | $20 (electricidad, internet) | $11 (VPS cloud) |
| Operacion (4h/mes × $25/h) | $100/mes | $0 (cloud) |
| **Total a 3 años** | **$7,400** | **$496** |
| **Por sucursal** | **$740** | **$50** |

**Asumimos 10 empresas-clientes, cada una con 2 sucursales:**

| Concepto | Modelo 1 (10 instalaciones) | Modelo 2 (SaaS 1 instalacion) |
|---|---|---|
| Setup inicial | $40,000 (10 × $4,000) | $5,000 (multi-tenant) + $50 (VPS) |
| Costo mensual | $200 (electricidad) | $199 (VPS + DB + Cloudflare) |
| Operacion (soporte 4h/mes × $25/h) | $1,000/mes (10 clientes) | $200/mes (centralizado) |
| **Total a 3 años** | **$80,000** | **$19,400** |
| **Por cliente** | **$8,000** | **$1,940** |
| **Precio sugerido al cliente** | $500/mes (licencia + soporte) | $100/mes (SaaS) |
| **Revenue a 3 años** | $180,000 | $36,000 |
| **Margen bruto** | $100,000 (56%) | $16,600 (46%) |

**Conclusion:** el Modelo 2 SaaS es 4-5x mas barato de operar y similar
en margen, PERO requiere inversion inicial en desarrollo multi-tenant.

---

## 7. Hibrido: ambos modelos a la vez

Si queres **ofrecer ambos** a tus clientes (Plan Pro cloud + Plan Enterprise
on-premise), necesitas:

1. **Desarrollar multi-tenant** en el codigo (Modelo 2 base, ~80h)
2. **Empaquetar el software** como instalador (Docker Compose + script
   de setup) para clientes que quieran on-premise (~40h)
3. **Sistema de billing** que distinga planes (basico cloud, pro cloud,
   enterprise on-premise) (~40h)
4. **Documentar ambos modelos** de instalacion (~16h)
5. **CRM/soporte** que maneje ambos tipos de clientes (~ongoing)

**Esfuerzo total:** ~180h adicionales (1 mes de 1 dev).

**Pricing:**

| Plan | Tipo | Precio/mes | Incluye |
|---|---|---|---|
| **Basico** | SaaS | $50 | 1 usuario, 3 bodegas, 1K transacciones/mes |
| **Pro** | SaaS | $200 | 10 usuarios, 30 bodegas, 100K transacciones/mes, soporte |
| **Enterprise** | On-premise | $2000 + setup | N usuarios, N bodegas, instalacion en oficina del cliente, soporte premium |
| **White-label** | Custom | $5000+ | Tu marca, tu dominio, todo customizado |

---

## 8. Como elegir el modelo correcto

### Diagrama de decision

```
              ¿Cuantas empresas van a usar el sistema?
                              |
                +-------------+-------------+
                |                           |
               UNA                        VARIAS
                |                           |
                v                           v
        ¿Tiene internet            ¿Vos queres
        estable en las              operarlo todo
        sucursales?                 centralizadamente?
                |                           |
          +-----+-----+                +------+------+
          |           |                |             |
         SI          NO              SI            NO
          |           |                |             |
          v           v                v             v
     Modelo 1    Modelo 1            Modelo 2    ¿Tenes
     (cloud)     (opcion 1C:         (SaaS)    personal IT
                 offline-first)                 en el cliente?
                                                     |
                                                +----+----+
                                                |         |
                                               SI        NO
                                                |         |
                                                v         v
                                            Modelo 1  Modelo 2
                                            (hibrido)  (SaaS)
```

### Matriz de decision

| Pregunta | Si la respuesta es SI | Si la respuesta es NO |
|---|---|---|
| ¿Tenes mas de 1 cliente? | **Modelo 2 (SaaS)** | **Modelo 1 (Distribuido)** |
| ¿Las sucursales tienen internet estable? | **Modelo 1A o 2** | **Modelo 1C (offline-first)** |
| ¿Los datos deben quedar en la oficina del cliente? | **Modelo 1 (Distribuido)** | **Modelo 1B o 2** |
| ¿Queres modelo de negocio recurrente (SaaS)? | **Modelo 2** | **Modelo 1 (licencia unica)** |
| ¿Tenes equipo de DevOps? | **Modelo 2 (cloud)** | **Modelo 1 (tercerizar soporte)** |
| ¿El cliente tiene personal de IT? | **Modelo 1** | **Modelo 2** |
| ¿Costo inicial es limitante? | **Modelo 2 (sin inversion por cliente)** | **Modelo 1 (inversion grande al inicio, bajo despues)** |

### Recomendacion por tipo de empresa

| Tipo de empresa | Modelo recomendado | Por que |
|---|---|---|
| **Una PyME con 1-3 sucursales, internet OK** | Modelo 1B (cloud + navegador) | Bajo costo, simple |
| **Una empresa con 5-20 sucursales, multiples ciudades** | Modelo 1 con VPN | Performance, control |
| **Una empresa con sucursales en zonas sin internet** | Modelo 1C (offline-first) | Operacion autonoma |
| **Vos vendes a 1 empresa (licencia unica)** | Modelo 1 | Pago unico grande, sin operar |
| **Vos vendes a 10-100 empresas** | Modelo 2 (SaaS) | Bajo costo marginal por cliente |
| **Vos vendes a 1 empresa grande ($100K+/año)** | Modelo 1 Enterprise | Soporte premium, customizacion |
| **Vos vendes a 50+ empresas + 1-2 enterprise** | Ambos (hibrido) | Maximizar mercado |

---

## 9. Decision y siguientes pasos

### Recomendacion por defecto

| Caso | Recomendacion | Esfuerzo | Costo |
|---|---|---|---|
| **1 empresa propia, 1-5 sucursales** | **Modelo 1B (Distribuido + navegador)** | 2-3 dias | $300-500 inicial, $0-5/mes |
| **1 empresa propia, 5-30 sucursales** | **Modelo 1B + VPN** | 1 semana | $2,000-5,000 inicial, $0-20/mes |
| **Vos queres vender a N empresas (SaaS)** | **Modelo 2 (SaaS Multi-Tenant)** | 1 mes (multi-tenant en codigo) | $5,000 inicial, $50-200/mes |
| **Ofrecer ambos (hibrido)** | **Modelo 2 + opcion Enterprise on-premise** | 2 meses | $10,000+ inicial |

### Plan inmediato (esta semana)

1. **Decidir** con el equipo:
   - Si es para tu empresa: **Modelo 1B** (lo mas simple)
   - Si es para vender a N empresas: **Modelo 2** (requiere desarrollo)

2. **Si elegis Modelo 1B:**
   - Comprar 1 Mini PC (~$300, Beelink EQ12 recomendado)
   - Instalar Ubuntu Server + Docker
   - Levantar el stack en la sucursal principal
   - Configurar las PCs de las sucursales (navegador + acceso por LAN/VPN)
   - Validar con el E2E del manual de usuario (43/43 verde)

3. **Si elegis Modelo 2:**
   - Asignar 1 dev por 3-4 semanas para implementar multi-tenant
   - Contratar VPS (~$10/mes)
   - Crear 1 tenant de prueba
   - Documentar el flujo de onboarding de clientes
   - Validar con tests cross-tenant

4. **Si elegis Hibrido:**
   - Empezar con Modelo 2 (SaaS)
   - Agregar opcion Enterprise on-premise como plan premium
   - Inversion ~$15,000 inicial, ROI en 6-12 meses

### Comandos utiles (Modelo 1)

```bash
# === En el servidor principal (sucursal principal) ===

# 1. Instalar Ubuntu Server + Docker
sudo apt update && sudo apt install -y docker.io docker-compose-v2

# 2. Clonar el repo
sudo mkdir -p /opt/bodega
cd /opt/bodega
sudo git clone https://github.com/Renanakin/bodega.git .

# 3. Levantar el stack completo
sudo docker compose -f infra/docker/docker-compose.yml up -d

# 4. Configurar la IP del servidor como DNS local
# (en cada PC de las sucursales)
# 192.168.1.100  app.bodega.cl
# 192.168.1.100  api.bodega.cl

# 5. Generar certs self-signed para HTTPS
bash infra/scripts/generate-selfsigned-certs.sh

# 6. Validar
curl -sk https://192.168.1.100/api/v1/health

# 7. (Opcional) Configurar Cloudflare Tunnel para acceso desde internet
# (ver docs/INTEGRACION_REMOTA_Y_LOCAL.md seccion 6)
```

### Comandos utiles (Modelo 2)

```bash
# === En el VPS cloud ===

# 1. Setup inicial (ver docs/DEPLOY.md seccion 3)
docker compose -f infra/docker/docker-compose.yml up -d

# 2. Crear el primer tenant via API
ADMIN_TOKEN=$(curl -sk -X POST https://api.bodega.cl/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin12345"}' \
    | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -sk -X POST https://api.bodega.cl/api/v1/admin/tenants \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "code": "hvm",
        "name": "Hipermercado VM",
        "subdomain": "hvm.bodega.cl",
        "plan": "pro"
    }'

# 3. Asignar subdominio en Cloudflare
#    - Crear CNAME hvm.bodega.cl -> app.bodega.cl (Proxied)

# 4. Listar tenants
curl -sk https://api.bodega.cl/api/v1/admin/tenants \
    -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Contacto

- **Slack:** #bodega-dev
- **Email:** dev@bodega.cl
- **Documentacion relacionada:**
  - `docs/DEPLOY.md` — Manual de despliegue completo
  - `docs/PROPUESTA_PRODUCCION.md` — Cloud puro en detalle
  - `docs/MULTI_EQUIPO_MULTI_LOCACION.md` — Multi-tenant + multi-locacion
  - `docs/INTEGRACION_REMOTA_Y_LOCAL.md` — 3 modalidades con tuneles

---

## Anexo A: Setup paso a paso del Modelo 1B (Distribuido + navegador)

### A.1 Hardware recomendado para el servidor principal

| Escenario | Modelo | CPU | RAM | SSD | Precio |
|---|---|---|---|---|---|
| 1-3 sucursales, 10 usuarios | **Beelink Mini S12 Pro** | N100 4C/4T | 8 GB | 256 GB | $180 |
| 3-10 sucursales, 50 usuarios | **Beelink EQ12** | N100 4C/4T | 16 GB | 500 GB | **$300** |
| 10-30 sucursales, 200 usuarios | **Intel NUC 13 Pro** | i7-1360P 12C/16T | 32 GB | 1 TB | $900 |
| 30+ sucursales, 500+ usuarios | **HP ProLiant Microserver** | Xeon E-2224 4C/4T | 32 GB | 4 TB RAID | $1,500 |

**Recomendado:** Beelink EQ12 ($300, 16 GB, fanless, bajo consumo).

### A.2 Setup del servidor principal (paso a paso)

```bash
# 1. Instalar Ubuntu Server 22.04 LTS
# 2. Configurar IP estatica (ej: 192.168.1.100)
# 3. Configurar hostname
sudo hostnamectl set-hostname bodega-principal
sudo nano /etc/hosts
# 127.0.0.1   bodega-principal
# 192.168.1.100  app.bodega.local api.bodega.local

# 4. Instalar Docker
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 fail2ban ufw curl git
sudo systemctl enable docker

# 5. Configurar firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# 6. Clonar el repo
sudo mkdir -p /opt/bodega
sudo chown deploy:deploy /opt/bodega
sudo -u deploy git clone https://github.com/Renanakin/bodega.git /opt/bodega
cd /opt/bodega

# 7. Generar secrets
sudo -u deploy python3 infra/scripts/generate-secrets.py
# (copiar los secrets a .env.production)

# 8. Crear .env.production
sudo -u deploy cp infra/docker/.env.production.example infra/docker/.env.production
sudo -u deploy nano infra/docker/.env.production
# Pegar los secrets. Configurar:
#   DATABASE_URL=postgresql+asyncpg://bodegaje:<pwd>@db:5432/bodegaje
#   REDIS_URL=redis://redis:6379/0
#   ENVIRONMENT=production
#   DEBUG=false
#   CORS_ALLOWED_ORIGINS=https://app.bodega.cl,http://192.168.1.100

# 9. Generar certs self-signed para HTTPS
bash infra/scripts/generate-selfsigned-certs.sh
# Esto genera infra/docker/nginx/ssl/server.crt y server.key

# 10. Levantar el stack completo
sudo -u deploy docker compose -f infra/docker/docker-compose.yml up -d

# 11. Validar
sleep 30
curl -sk https://192.168.1.100/api/v1/health
# Esperado: {"status":"ok",...}
```

### A.3 Setup de las PCs de las sucursales

**Cada PC en cada sucursal:**

1. Instalar Windows 10/11 o Linux Mint/Ubuntu
2. Instalar Chrome/Edge/Firefox
3. **No instalar nada mas**. La app corre 100% en el navegador.
4. Agregar entrada DNS local: `192.168.1.100  app.bodega.local`
5. Abrir `https://app.bodega.local` (HTTPS con cert self-signed, ignorar warning)
6. Login con las credenciales del operario

**Si la sucursal esta en otra ciudad/país:**

1. Instalar Tailscale en el servidor principal y en cada PC
2. Unirse a la red Tailscale (magic DNS)
3. Acceder via `https://bodega-principal.tail-net.ts.net`
4. O configurar Cloudflare Tunnel (ver `INTEGRACION_REMOTA_Y_LOCAL.md` seccion 6)

### A.4 Mantenimiento

```bash
# Backup local (disco USB o NAS)
mount /dev/sdb1 /mnt/backup
docker exec bodegaje-db pg_dump -U bodegaje -d bodegaje | gzip > /mnt/backup/$(date +%Y%m%d).sql.gz
umount /mnt/backup

# Ver uso de disco
df -h /mnt/bodega-data

# Ver logs
docker logs bodegaje-api --tail 50 -f

# Reiniciar la API despues de un cambio
cd /opt/bodega
sudo -u deploy git pull origin main
sudo -u deploy docker compose -f infra/docker/docker-compose.yml up -d --build
```

---

## Anexo B: Setup paso a paso del Modelo 2 (SaaS Multi-Tenant)

### B.1 Pre-requisitos

1. Haber leido `docs/MULTI_EQUIPO_MULTI_LOCACION.md` (multi-tenant)
2. Tener implementado el codigo multi-tenant (~80h, ver seccion 3.4 de ese doc)
3. VPS cloud configurado con HTTPS via Cloudflare

### B.2 Setup del VPS (1 sola instalacion)

```bash
# En el VPS (siguiendo docs/DEPLOY.md seccion 3)
cd /opt/bodega
sudo -u deploy docker compose -f infra/docker/docker-compose.yml up -d

# Validar
curl -sk https://api.bodega.cl/api/v1/health
```

### B.3 Crear el primer tenant

```bash
# Login como admin (vos)
ADMIN_TOKEN=$(curl -sk -X POST https://api.bodega.cl/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin12345"}' \
    | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Crear tenant "HVM"
curl -sk -X POST https://api.bodega.cl/api/v1/admin/tenants \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "code": "hvm",
        "name": "Hipermercado VM",
        "subdomain": "hvm.bodega.cl",
        "plan": "pro",
        "settings": {
            "max_users": 50,
            "max_warehouses": 10,
            "max_transactions_per_month": 100000
        }
    }'
# Devuelve: {"tenant_id": "...", "admin_token": "..."}

# Listar tenants
curl -sk https://api.bodega.cl/api/v1/admin/tenants \
    -H "Authorization: Bearer $ADMIN_TOKEN"
```

### B.4 Configurar DNS por tenant

En Cloudflare, para cada tenant crear:

```
hvm.bodega.cl          CNAME  app.bodega.cl  (Proxied)
frigosur.bodega.cl     CNAME  app.bodega.cl  (Proxied)
minerax.bodega.cl      CNAME  app.bodega.cl  (Proxied)
```

Con Cloudflare Pro y wildcard:
```
*.bodega.cl            CNAME  app.bodega.cl  (Proxied)
```

Asi, cada nuevo tenant funciona automaticamente con su subdominio.

### B.5 Onboarding de un cliente

| Paso | Tiempo | Quien |
|---|---|---|
| Crear tenant via API | 1 min | Admin (vos) |
| Configurar subdominio en Cloudflare | 5 min | Admin (vos) |
| Crear usuario admin del tenant | 1 min | Admin (vos) o auto |
| Enviar credenciales al cliente | 5 min | Vos |
| Cliente carga catalogos (productos, proveedores) | 1-2h | Cliente |
| Cliente crea sus bodegas (sucursales) | 15 min | Cliente |
| Cliente crea sus usuarios | 15 min | Cliente |
| Capacitar al cliente | 2h | Vos o el supervisor |
| **TOTAL** | **~4-6h** | Mixto |

---

## Anexo C: Cuando usar cada tunel (Modelo 1)

| Tunel | Costo | Setup | Ideal para |
|---|---|---|---|
| **LAN directa** | $0 | 0 | Todas las sucursales en la misma oficina/edificio |
| **Cloudflare Tunnel** | $0 | 10 min | Sucursales en distintas ciudades con internet |
| **Tailscale** | $0 (<100 disp) | 5 min | Admin accediendo desde casa |
| **WireGuard** | $0 | 30 min | Redes corporativas con auditoria estricta |
| **VPN tradicional (OpenVPN)** | $0 | 4h | Legacy, compatibilidad amplia |

**Recomendado para Modelo 1B:** 
- LAN directa para sucursales en el mismo edificio
- Cloudflare Tunnel para sucursales remotas
- Tailscale para el admin

---

**Resumen ejecutivo (1 parrafo):**

Si tenes **1 sola empresa con 5-10 sucursales en LATAM** y queres
empezar rapido, usa **Modelo 1B (Distribuido + navegador + LAN/VPN)**: 1
Mini PC en la principal ($300), todo en LAN, las sucursales acceden via
navegador. Setup: 2-3 dias. Costo mensual: ~$5 (electricidad).

Si queres **vender a 10+ empresas** o tenes 1 empresa con 50+
sucursales, usa **Modelo 2 (SaaS Multi-Tenant)**: 1 sola instalacion en
la nube, multi-tenant con RLS, N empresas en 1 sola BD. Setup inicial:
1 mes de desarrollo. Costo operativo: $50-200/mes (compartido entre
N clientes).
