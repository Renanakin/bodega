# Propuesta de Integración: Acceso Remoto + Base de Datos Local

> **Para:** el dueño del producto, el equipo tecnico, y futuros clientes
> que necesitan distintas formas de acceder al sistema. Cubre:
>
> 1. **Acceso por internet** (cloud puro, recomendado para la mayoría)
> 2. **Base de datos local con conexión desde el exterior** (híbrido, on-premise + cloud)
> 3. **On-premise puro** (instalación en la propia bodega del cliente)
>
> **Lee esto de arriba a abajo la primera vez** y elegi la modalidad que
> mejor se adapte a tu caso de uso (o combina varias).

---

## Indice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Tu pregunta, contestada en 30 segundos](#2-tu-pregunta-en-30-segundos)
3. [Modalidad A: Cloud puro (acceso por internet)](#3-modalidad-a-cloud-puro)
4. [Modalidad B: Hibrido (BD local + acceso por internet)](#4-modalidad-b-hibrido)
5. [Modalidad C: On-premise puro (instalación local)](#5-modalidad-c-on-premise-puro)
6. [Tuneles seguros para acceso desde el exterior](#6-tuneles-seguros)
7. [Comparacion de las 3 modalidades](#7-comparacion)
8. [Casos de uso reales](#8-casos-de-uso-reales)
9. [Costos por modalidad](#9-costos-por-modalidad)
10. [Plan de implementacion](#10-plan-de-implementacion)
11. [Como elegir la modalidad correcta](#11-como-elegir)
12. [Decisión y siguientes pasos](#12-decision-y-siguientes-pasos)

---

## 1. Resumen ejecutivo

El sistema **Bodegaje v1.0.0** puede deployarse de **3 formas distintas**,
segun las necesidades del cliente:

| Modalidad | Que es | Para quien | Costo/mes |
|---|---|---|---|
| **A) Cloud puro** | Todo en la nube, acceso via internet | Clientes que quieren pagar $$ por mes y olvidarse de la infra | **$6-11** |
| **B) Hibrido** | BD local en la bodega del cliente, API en la nube, conectados via tunel | Clientes con requisitos de data residency o que quieren backup local | **$15-50** |
| **C) On-premise** | Todo instalado en la bodega/servidor del cliente, sin conexion a internet | Clientes con internet inestable o requisitos de control total | **$0/mes** (solo setup inicial) |

**Las 3 son validas.** La decisión depende de las prioridades del cliente.

### La mas comun: **Modalidad A (Cloud puro)**

Para el 90% de los clientes, la opción cloud puro es la mejor:
- Costo minimo ($6-11/mes para empezar)
- Cero operaciones de infra
- Acceso desde cualquier lugar con internet
- HTTPS automatico via Cloudflare
- Backups automaticos a S3
- DRP probado (RTO < 1 min)

### La mas segura: **Modalidad B (Hibrido)**

Para clientes con requisitos legales de data residency (Ley 19.628 en Chile,
GDPR en Europa) o que quieren control sobre su propia BD, la modalidad
hibrida es ideal. La BD queda en la bodega del cliente, pero la API corre
en la nube. Ambas se conectan via un tunel seguro (Cloudflare Tunnel,
WireGuard, o Tailscale).

### La mas controlada: **Modalidad C (On-premise)**

Para clientes con internet muy inestable (faenas mineras, barcos, zonas
rurales) o requisitos de control total, todo se instala en la propia
infraestructura del cliente. La contra es que ellos operan todo.

---

## 2. Tu pregunta, contestada en 30 segundos

> "Como hago para que el software sea accesible desde distintos puntos
> por internet y tambien con base de datos local y conexion desde el exterior"

**Respuesta corta:**

| Requisito | Solución | Tecnologia |
|---|---|---|
| **Acceso desde distintos puntos por internet** | Cloud + dominio + HTTPS | Cloudflare + VPS (Hetzner/Google Cloud/AWS) |
| **Base de datos local** (en la propia oficina del cliente) | Servidor local en la oficina | Mini PC + Docker (~$300-500) o servidor NAS |
| **Conexion desde el exterior** (a esa BD local) | Tunel seguro | Cloudflare Tunnel (recomendado) o WireGuard o Tailscale |

**La forma más práctica de combinar todo:** **Modalidad B (Híbrido)**
con la BD local en una Mini PC en la oficina del cliente, y un Cloudflare
Tunnel que expone la API de forma segura sin abrir puertos en el router
del cliente.

**Costo de la modalidad B recomendada:** $300-500 inicial (Mini PC) + $5-10/mes
(VPS cloud) + $0 (Cloudflare Tunnel free tier).

---

## 3. Modalidad A: Cloud puro (acceso por internet)

### Arquitectura

```
[Operario Bodega Santiago]    [Operario Bodega Lima]    [Operario Bodega Miami]
       |                              |                          |
       |  HTTPS (443)                 |  HTTPS                   |  HTTPS
       +-------------+----------------+----------+---------------+
                                 |
                                 v
                    +-------------------------+
                    |      Cloudflare          |  <- CDN + WAF + DDoS + SSL
                    |  api.bodega.cl          |     (Free tier o Pro $20/mes)
                    +------------+------------+
                                 |  HTTPS (Full Strict)
                                 v
                    +-------------------------+
                    |   VPS (Hetzner / GCP)    |  <- Ubuntu 22.04 + Docker
                    |   Frankfurt / Santiago   |
                    +------------+------------+
                                 |
            +--------------------+--------------------+
            |                    |                    |
            v                    v                    v
      +-------------+      +-------------+      +-------------+
      | API (FastAPI)|     | Worker (Arq) |     | Web (React) |
      | port 8000    |     | emails + cron |    | port 80     |
      +------+------+      +------+-------+      +------+------+
             |                    |                    |
             +--------------------+--------------------+
                                  |
                  +---------------+---------------+
                  |                               |
                  v                               v
          +---------------+              +---------------+
          |  Postgres 17  |              |  Redis 8      |
          |  port 5432    |              |  port 6379    |
          +---------------+              +---------------+
```

**Flujo:**
1. Operario abre `https://app.bodega.cl` en su navegador
2. Cloudflare recibe la peticion, valida SSL, filtra DDoS
3. Cloudflare reenvia a VPS via HTTPS (Full Strict)
4. Nginx en el VPS sirve la UI estatica (React build)
5. La UI hace llamadas a la API REST en `https://api.bodega.cl`
6. FastAPI responde, consulta Postgres o Redis segun necesidad
7. Worker Arq procesa emails y corre el replenishment cada 5 min

**Caracteristicas:**

- **Acceso universal:** cualquier operario con navegador puede usar el sistema
- **HTTPS valido** (cert de Cloudflare, sin warnings del browser)
- **CDN + WAF + DDoS** gratis via Cloudflare
- **BD centralizada** en el VPS (Postgres 17 + backups a S3)
- **Latencia** depende de la region del VPS (Hetzner FSN ~200ms desde Chile, GCP `southamerica-east1` ~30ms)

**Setup completo:** ver `docs/PROPUESTA_PRODUCCION.md` seccion 4.

**Costo:** **$6-11/mes** (VPS + Cloudflare Free + S3).

---

## 4. Modalidad B: Híbrido (BD local + acceso por internet)

### Arquitectura

```
                                          [Internet]
                                              |
                                              v
                                     +----------------+
                                     |   Cloudflare   |  <- SSL + WAF + Tunnel
                                     |  api.bodega.cl |     (Cloudflare Tunnel)
                                     +-------+--------+
                                             |
                                             | Tunel cifrado (no abre puertos)
                                             | (Cloudflare Tunnel o WireGuard)
                                             v
+------------------------------------------------------------------+
|  Oficina del cliente (red local, IP privada 192.168.x.x)        |
|                                                                  |
|  +----------------+      +----------------+   +---------------+ |
|  |  Mini PC       |      |  Postgres 17   |   |  Redis 8     | |
|  |  (i3/N100,     | <--> |  (la BD del    |   |  (cache)     | |
|  |   8 GB RAM,   |      |   cliente,     |   |              | |
|  |   256 GB SSD) |      |   local)       |   |              | |
|  |  $300-500     |      |  port 5432     |   |  port 6379  | |
|  +-------+--------+      +----------------+   +------+-------+ |
|          |                                          |         |
|          +------------------------------------------+         |
|                              |                              |
|                              v                              |
|                    +-------------------+                     |
|                    |  Cloudflare Tunnel| (cloudflared)        |
|                    |  daemon          |                     |
|                    +-------------------+                     |
+------------------------------------------------------------------+
                                  |
                                  | Sale a internet por tunel
                                  v
                              [Cloudflare Edge]
                                       |
                                       v
                              [VPS cloud (api.bodega.cl)]
                                       |
                                       v
                              [FastAPI workers + Nginx]
```

**Como funciona:**

1. La oficina del cliente tiene una **Mini PC** con Docker
2. En esa Mini PC corren: **Postgres 17** (la BD), **Redis 8** (cache), y un **daemon de Cloudflare Tunnel** (`cloudflared`)
3. El daemon `cloudflared` establece una conexion saliente cifrada a Cloudflare
4. Cloudflare expone el subdominio `api.bodega.cl` que apunta a ese tunel
5. **NO se abre ningun puerto en el router del cliente** (no hay forwarding, no hay firewall que configurar)
6. La API (FastAPI) corre en el VPS cloud y se conecta al Postgres local via el tunel
7. Los operarios acceden via `https://app.bodega.cl` (UI) que apunta al VPS cloud

**Ventajas:**
- **Data residency:** la BD con datos sensibles (proveedores, stock, clientes) queda en la oficina del cliente
- **Cumplimiento legal:** Ley 19.628 (Chile) y GDPR (Europa) requieren datos en el pais
- **Backup local:** la BD se respalda en la propia oficina (mas rapido que S3)
- **Acceso desde internet:** via Cloudflare Tunnel (gratis, seguro, sin puertos abiertos)
- **Latencia local:** operario en la oficina accede a la BD en LAN (1ms) si el front corre localmente
- **Disaster recovery:** si internet cae en la oficina, la BD sigue funcionando localmente

**Setup paso a paso:**

#### 4.1 En la oficina del cliente (Mini PC)

```bash
# 1. Instalar Ubuntu Server 22.04 LTS en la Mini PC
# 2. Instalar Docker
apt update && apt install -y docker.io docker-compose-v2
systemctl enable docker

# 3. Clonar el repo
mkdir -p /opt/bodega
cd /opt/bodega
git clone https://github.com/Renanakin/bodega.git .

# 4. Crear .env.local con la configuracion de la oficina
cat > .env.local <<EOF
ENVIRONMENT=production
DEBUG=false
APP_NAME=Bodegaje Local (HVM)
APP_VERSION=1.0.0
DATABASE_URL=postgresql+asyncpg://bodegaje:bodegaje@db:5432/bodegaje
REDIS_URL=redis://redis:6379/0
JWT_SECRET=<secret-generado-con-generate-secrets.py>
SECRET_KEY=<secret-generado>
# ... resto de las variables ...
EOF

# 5. Levantar SOLO la BD + Redis + Cloudflare Tunnel
docker compose -f infra/docker/docker-compose.yml \
    -f infra/docker/production.yml \
    --env-file .env.local \
    up -d db redis cloudflared

# 6. Validar que la BD este corriendo
docker exec bodegaje-db pg_isready -U bodegaje
# Esperado: accepting connections
```

#### 4.2 Instalar Cloudflare Tunnel

```bash
# En la Mini PC
# 1. Login en Cloudflare
docker exec -it bodegaje-cloudflared cloudflared tunnel login
# Esto abre un browser para autorizar el tunnel. Pegar el URL en un browser
# y autorizar.

# 2. Crear el tunnel
docker exec -it bodegaje-cloudflared cloudflared tunnel create bodega-hvm
# Esto genera un tunnel UUID y un archivo de credenciales

# 3. Configurar el tunnel
# Crear /etc/cloudflared/config.yml en la Mini PC
cat > /etc/cloudflared/config.yml <<EOF
tunnel: bodega-hvm
credentials-file: /etc/cloudflared/<TUNNEL_ID>.json

ingress:
  # Regla 1: API REST -> exponer la API que corre en la nube, NO la local
  # (la API esta en el VPS, no en la Mini PC)
  # Esta regla es solo para tuneles que APUNTAN a servicios locales.
  # Si la API corre en el VPS, NO necesita tunnel.

  # Regla 2: Acceso directo a la BD para admin (opcional, para pgAdmin)
  - hostname: db.bodega.cl
    service: tcp://localhost:5432

  # Catch-all: 404 si no matchea ninguna regla
  - service: http_status:404
EOF

# 4. Iniciar el tunnel (ya lo hace cloudflared daemon, pero verificar)
docker logs bodegaje-cloudflared
# Debe mostrar: "Connection established connIndex=0 ... registered"
```

#### 4.3 En el VPS cloud (la API)

```bash
# En el VPS, el docker compose NO incluye db/redis (estos estan locales)
# Solo incluye: api + worker + web + nginx + cloudflared
docker compose -f infra/docker/cloud-api-only.yml up -d

# La API se conecta a la BD local via:
# postgresql+asyncpg://bodegaje:bodegaje@db.bodega.cl:5432/bodegaje
# (el hostname db.bodega.cl resuelve via Cloudflare DNS al tunnel del cliente)
```

#### 4.4 Diagrama final de la Modalidad B

```
+-------------------------+         +-------------------------+
| Operario Santiago       |         | Operario Lima           |
| Browser: app.bodega.cl |         | Browser: app.bodega.cl  |
+-----------+-------------+         +-----------+-------------+
            | HTTPS                            | HTTPS
            v                                   v
+----------------------------------------------------------------+
|                    Cloudflare Edge                              |
|   - SSL terminacion                                              |
|   - WAF + DDoS                                                   |
|   - GeoDNS (apunta al VPS)                                       |
+-------+----------------+----------------------------------------+
        |
        | HTTPS (Full Strict)
        v
+-------------------------+
| VPS (Hetzner Frankfurt)  |
| API + Worker + Web      |
| NO tiene BD (conecta    |
| a la del cliente via    |
| Cloudflare Tunnel)     |
+-----------+-------------+
            | Conexion a bd.bodega.cl
            | (resuelve via Cloudflare DNS al tunnel)
            v
+----------------------------------------------------------------+
| Oficina cliente (IP privada 192.168.1.x)                       |
|                                                                  |
|  +-------------+     +-------------+     +-------------------+ |
|  | Mini PC     |     | Postgres 17 |     | Cloudflare Tunnel | |
|  | (8 GB RAM,  |---->| (la BD)     |     | daemon (cloudflared) |
|  |  256 GB SSD)|     | port 5432   |     |                   | |
|  +-------------+     +-------------+     +---------+---------+ |
|                                                          |     |
|                                                          |     |
+----------------------------------------------------------+----+
                                                           |
                                                    Conexion saliente
                                                    (no abre puertos)
                                                           |
                                                           v
                                                     [Cloudflare]
```

**Caracteristicas de la Modalidad B:**

- **NO se abre ningun puerto** en el router del cliente (gracias a Cloudflare Tunnel)
- **NO se requiere IP publica fija** (Cloudflare Tunnel maneja DNS dinamico)
- **Cifrado end-to-end** entre Cloudflare y la Mini PC
- **La BD nunca sale de la oficina** del cliente (data residency)
- **Backups locales** en la propia oficina (y opcionales a S3)
- **Acceso desde internet** sigue siendo HTTPS via Cloudflare
- **Si internet cae en la oficina:** la BD sigue accesible en LAN (operario puede seguir trabajando)
- **Si internet cae en Cloudflare:** la API no responde (pero la BD sigue intacta)

---

## 5. Modalidad C: On-premise puro (instalación local)

### Arquitectura

```
[Oficina del cliente - red aislada, sin internet]
+---------------------------------------------------------------+
|                                                               |
|  +----------+    +---------+   +-------+   +-----------+     |
|  | Nginx   |    | FastAPI |   | Arq   |   | React     |     |
|  | :80/443|<-->| :8000  |<->| worker|   | (build)   |     |
|  +----+----+    +----+----+   +-------+   +-----------+     |
|       |              |            |              |          |
|       +------+-------+------------+--------------+          |
|              |                                               |
|              v                                               |
|       +-------------+      +-----------+                    |
|       | Postgres 17 |      | Redis 8   |                    |
|       | :5432       |      | :6379     |                    |
|       +-------------+      +-----------+                    |
|                                                               |
+---------------------------------------------------------------+
              |
              | (NO internet - totalmente aislado)
              x
              x
         (nada hacia afuera)
```

**Cuando se usa:**
- Cliente en zona sin internet (faena minera, barco, zona rural)
- Cliente con requisitos de control total (banco, gobierno, defensa)
- Cliente que quiere auditar todo el codigo que corre en su infra
- Red air-gapped (sin conexion a internet por seguridad)

**Setup:**

```bash
# En el servidor del cliente (Mini PC o servidor rack)
# 1. Instalar Ubuntu Server 22.04
# 2. Instalar Docker
apt install -y docker.io docker-compose-v2

# 3. Clonar el repo
cd /opt
git clone https://github.com/Renanakin/bodega.git

# 4. Levantar el stack completo (13 containers)
cd bodega
docker compose -f infra/docker/docker-compose.yml \
    -f infra/docker/production.yml \
    up -d

# 5. Configurar DNS interno (opcional)
# Agregar al /etc/hosts de cada operario:
# 192.168.1.100 app.bodega.cl api.bodega.cl

# 6. Generar certs self-signed para HTTPS
bash infra/scripts/generate-selfsigned-certs.sh
# o usar mkcert

# 7. Listo
# Los operarios acceden a https://app.bodega.cl o https://192.168.1.100
```

**Caracteristicas:**
- **Cero dependencia de internet** (red air-gapped)
- **Cero costos recurrentes** (sin VPS, sin cloud, sin Cloudflare)
- **Control total** del cliente
- **Costo inicial:** $300-500 (Mini PC) o $1,500+ (servidor rack)
- **Operacion:** el cliente opera todo (o contrata soporte)
- **Updates:** hay que hacerlo manual o via USB

**Limitaciones:**
- Sin acceso desde internet (solo LAN)
- Si el cliente quiere que su admin acceda desde casa, necesita VPN o tunnel
- Backups a S3 requieren internet (alternativa: backup en disco USB)
- Actualizaciones de codigo requieren acceso fisico

---

## 6. Tuneles seguros para acceso desde el exterior

Para la Modalidad B, hay 3 opciones de tunel. Las comparo:

### Opcion 1: Cloudflare Tunnel (RECOMENDADO)

**Que es:** un daemon ligero (`cloudflared`) que establece una conexion
saliente cifrada a Cloudflare. Cloudflare expone tu servicio sin que
abras puertos.

**Setup (en la Mini PC del cliente):**

```bash
# 1. Instalar cloudflared
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared

# 2. Login (autoriza el tunnel con tu cuenta de Cloudflare)
sudo cloudflared tunnel login

# 3. Crear el tunnel
sudo cloudflared tunnel create bodega-hvm-db
# Output: Tunnel credentials written to /etc/cloudflared/<UUID>.json

# 4. Crear el config
sudo nano /etc/cloudflared/config.yml
# tunnel: bodega-hvm-db
# credentials-file: /etc/cloudflared/<UUID>.json
# 
# ingress:
#   - hostname: db.bodega.cl
#     service: tcp://localhost:5432
#   - service: http_status:404

# 5. Crear el DNS record en Cloudflare
sudo cloudflared tunnel route dns bodega-hvm-db db.bodega.cl

# 6. Iniciar el tunnel como servicio
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# 7. Verificar
sudo cloudflared tunnel info bodega-hvm-db
# Output: Your tunnel is connected to Cloudflare Edge.
```

**Pros:**
- Gratis (free tier)
- Cero puertos abiertos en el router
- Cero configuracion de firewall
- DNS automatico (Cloudflare crea el record)
- HTTPS automatico (cert de Cloudflare)
- Multi-tunnel: puedes tener N tunnels (1 por cliente, 1 por BD, etc.)

**Contras:**
- Dependencia de Cloudflare (si cae, no hay tunnel)
- Requiere cuenta de Cloudflare (gratis)
- Logs en Cloudflare (puede ser un tema de compliance)

### Opcion 2: Tailscale (VPN mesh, RECOMENDADO para admins)

**Que es:** VPN mesh (red privada virtual) que conecta dispositivos en
cualquier parte del mundo como si estuvieran en la misma LAN. Ideal
para que el admin del sistema acceda a la BD local desde su casa.

**Setup:**

```bash
# 1. Instalar Tailscale en la Mini PC
curl -fsSL https://tailscale.com/install.sh | sh

# 2. Login
sudo tailscale up

# 3. Instalar Tailscale en la laptop del admin
# (Windows / Mac / Linux)

# 4. La laptop del admin ahora ve la Mini PC como si estuviera en LAN
# Puede acceder a localhost:5432 de la Mini PC desde su laptop
psql -h <TAILSCALE_IP> -U bodegaje -d bodegaje
```

**Pros:**
- Gratis para uso personal (hasta 100 dispositivos)
- Cero puertos abiertos (Tailscale usa relays cifrados)
- Magic DNS: hostname de Tailscale resuelve automaticamente
- MagicDNS: cada dispositivo tiene un nombre fijo
- MagicDNS: ideal para SSH, RDP, acceso a servicios internos

**Contras:**
- Limite de 100 dispositivos en free tier
- Si la red Tailscale cae, no hay acceso
- Latencia mayor que LAN (15-50ms)

### Opcion 3: WireGuard (VPN clasica, MAXIMA SEGURIDAD)

**Que es:** VPN moderna, super rapida (~linea base), ideal para redes
corporativas con requisitos de auditoria.

**Setup (server en la Mini PC):**

```bash
# 1. Instalar WireGuard
sudo apt install -y wireguard

# 2. Generar claves
wg genkey | tee /etc/wireguard/privatekey | wg pubkey > /etc/wireguard/publickey
wg genkey | tee /etc/wireguard/client_privatekey | wg pubkey > /etc/wireguard/client_publickey

# 3. Configurar el server
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.0.0.1/24
ListenPort = 51820
PrivateKey = <server_privatekey>
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

[Peer]
PublicKey = <client_publickey>
AllowedIPs = 10.0.0.2/32
EOF

# 4. Iniciar WireGuard
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0

# 5. Configurar el cliente
# (en la laptop del admin)
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.0.0.2/24
PrivateKey = <client_privatekey>

[Peer]
PublicKey = <server_publickey>
Endpoint = <public_ip_of_office>:51820
AllowedIPs = 10.0.0.1/32
EOF
```

**Pros:**
- Criptografia state-of-the-art (ChaCha20)
- Muy rapido (~linea base, ~1ms overhead)
- Es parte del kernel Linux (no user-space)
- Ideal para redes corporativas con auditoria

**Contras:**
- Mas complejo de configurar (iptables, DNS, etc.)
- Requiere IP publica fija o DDNS
- Hay que abrir 1 puerto UDP en el router (51820)
- Si el admin quiere acceder desde multiples dispositivos, hay que generar 1 par de claves por dispositivo

### Comparativa de tuneles

| Criterio | Cloudflare Tunnel | Tailscale | WireGuard |
|---|---|---|---|
| **Costo** | Free | Free (<100 disp) | Free |
| **Puertos abiertos** | 0 | 0 | 1 (UDP 51820) |
| **Setup** | 10 min | 5 min | 30 min |
| **Latencia** | ~10-50ms | ~15-50ms | ~1-5ms |
| **Confiabilidad** | Depende de Cloudflare | Depende de Tailscale | Auto-contenido |
| **Auditoria** | Logs en Cloudflare | MagicDNS, ACLs | iptables |
| **Ideal para** | BD expuesta a internet | Admin accediendo desde casa | Red corporativa |
| **Cumple HIPAA/SOC2** | Si (con plan Pro) | Si (con plan Business) | Si (auto-gestionado) |
| **Recomendado para v1.0** | **SI** | SI (admin) | SI (enterprise) |

**Recomendado:** usar **Cloudflare Tunnel** para la BD expuesta
(internet), y **Tailscale** para el admin que accede desde casa.

---

## 7. Comparacion de las 3 modalidades

| Criterio | A) Cloud puro | B) Hibrido | C) On-premise |
|---|---|---|---|
| **Acceso por internet** | Si (HTTPS via Cloudflare) | Si (HTTPS via Cloudflare) | NO (solo LAN) |
| **Acceso por LAN** | NO (cloud only) | Si (BD local) | Si (todo local) |
| **BD local en oficina** | NO | SI | SI |
| **Data residency** | Media (region del cloud) | Alta (oficina del cliente) | Total (oficina) |
| **Costo inicial** | $0 (solo setup) | $300-500 (Mini PC) | $300-2000 (hardware) |
| **Costo mensual** | $6-11 (VPS+CF) | $5-10 (solo VPS) | $0 (sin servicios cloud) |
| **Operacion** | Baja (cloud) | Media (BD local) | Alta (todo local) |
| **Internet requerido** | SIEMPRE | Para sync/salida, NO para operar | NO |
| **Latencia tipica** | 30-200ms | 30ms (LAN) + 50ms (cloud) | <5ms (todo LAN) |
| **Backups** | S3 (offsite) | Disco local + opcional S3 | Disco local / USB |
| **Disaster recovery** | RTO < 1 min (probado) | Media (depende del tunnel) | RTO 1-2h (manual) |
| **Compliance** | GDPR facil | GDPR + Ley 19.628 (Chile) | Auto-controlado |
| **Cumple "sin internet"** | NO | Parcial (BD local funciona) | SI |
| **Max usuarios recomendado** | 1000+ (cloud) | 50-200 (hibrido) | 10-50 (local) |
| **Complejidad operacional** | Baja | Media | Alta |
| **Mejor para** | SaaS, empresas chicas | Empresas con data local | Faenas, barcos, gobierno |

---

## 8. Casos de uso reales

### Caso 1: Hipermercado VM (Santiago, Chile)

- **Modalidad recomendada:** A (Cloud puro)
- **Por que:** 8 bodegas en Santiago, todas con internet, datos sensibles
  pero no requieren local. Costo $6/mes es trivial.
- **Setup:** VPS en `googleapis.com/southamerica-east1` (Santiago), 30ms de latencia.
- **Resultado esperado:** operario en la bodega abre la app y registra un
  movimiento en <100ms (UX excelente).

### Caso 2: Frigosur (Lima, Peru)

- **Modalidad recomendada:** B (Hibrido)
- **Por que:** cliente quiere la BD local por compliance legal en Peru.
  Operarios usan internet 4G en la bodega.
- **Setup:** Mini PC en la oficina central de Lima, BD local,
  Cloudflare Tunnel expone la API. Operarios en cualquier bodega
  de Peru acceden via `app.frigosur.bodega.cl`.
- **Costo:** $400 (Mini PC) + $8/mes (VPS) = $408 inicial, $8/mes despues.

### Caso 3: Minera X (Atacama, Chile, faena remota)

- **Modalidad recomendada:** C (On-premise) con sincronizacion eventual
- **Por que:** la faena tiene internet satelital intermitente (2h/dia).
  Los operarios en el campamento necesitan operar offline.
- **Setup:** servidor rack en el campamento de la mina, todo on-premise.
  Backups a disco USB que se envian semanalmente.
- **Costo:** $2,000 (servidor) + $0/mes. Backups a USB: $20/mes (envio).

### Caso 4: Banco Regional (Chile, sucursales en 3 ciudades)

- **Modalidad recomendada:** B (Hibrido) con Tailscale para admin
- **Por que:** compliance bancario (datos en Chile), pero el admin del
  banco quiere ver metricas desde su casa. Multi-tenant v1.1
  (cada sucursal = 1 tenant, o 1 tenant para todo el banco).
- **Setup:** VPS en Chile (`southamerica-east1`), 3 Mini PC (1 por
  sucursal principal), Tailscale para admin.
- **Costo:** $1,500 (3 Mini PC) + $30/mes (VPS + S3 + monitoring) = $1,530 inicial.

### Caso 5: Distribuidora de bebidas (5 bodegas en Chile y Peru)

- **Modalidad recomendada:** A (Cloud puro) con v1.1 multi-tenant
- **Por que:** 5 bodegas, todas con internet, equipo chico.
  Multi-tenant para tener 1 sola instalacion.
- **Setup:** VPS en Chile, multi-tenant habilitado. 1 sola BD.
- **Costo:** $11/mes (VPS cloud) para 5 bodegas.

---

## 9. Costos por modalidad

### Modalidad A: Cloud puro

| Concepto | Bajo (1-10 users) | Medio (10-50 users) | Alto (100+ users) |
|---|---|---|---|
| VPS | $4.50/mes (CAX11) | $9.50/mes (CAX21) | $32/mes (CCX13) |
| Dominio | $1.25/mes | $1.25/mes | $1.25/mes |
| Cloudflare | $0 (Free) | $0 (Free) | $20/mes (Pro) |
| Backups S3 | $0.05/mes | $0.20/mes | $2/mes |
| Email | $0 (Brevo) | $0 (Brevo) | $5/mes (SES) |
| Monitoring | $0 | $0 | $7/mes (UptimeRobot Pro) |
| **TOTAL** | **$5.80/mes** | **$10.95/mes** | **$67.25/mes** |

### Modalidad B: Hibrido

| Concepto | Bajo (1 oficina) | Medio (3 oficinas) | Alto (10+ oficinas) |
|---|---|---|---|
| **VPS cloud** (API + Worker) | $9.50/mes | $9.50/mes | $32/mes |
| **Mini PC oficina central** | $400 (inicial) | $1,200 (3) | $4,000 (10) |
| **Cloudflare Tunnel** | $0 (Free) | $0 (Free) | $0 (Free) |
| **Backups S3** (BD local) | $0.10/mes | $0.30/mes | $1/mes |
| **Disco backup local** (en Mini PC) | $50 (1 TB USB) | $150 (3 TB) | $500 (10 TB) |
| **Email** | $0 (Brevo) | $0 (Brevo) | $5/mes (SES) |
| **Monitoring** | $0 | $7/mes (Tailscale) | $21/mes (PagerDuty) |
| **TOTAL inicial** | **$450** | **$1,350** | **$4,500** |
| **TOTAL mensual** | **$9.60/mes** | **$16.80/mes** | **$59/mes** |

### Modalidad C: On-premise puro

| Concepto | Bajo (1 oficina) | Medio (3 oficinas) | Alto (10+ oficinas) |
|---|---|---|---|
| **Servidor** (Mini PC o rack) | $400 (inicial) | $1,500 (3) | $5,000 (10) |
| **Cloudflare Tunnel** (si quieren admin remoto) | $0 | $0 | $0 |
| **Backups USB** (envio periodico) | $20/mes | $60/mes | $200/mes |
| **Email** (solo si tienen internet) | $0 (Brevo) | $0 | $5/mes |
| **TOTAL inicial** | **$400** | **$1,500** | **$5,000** |
| **TOTAL mensual** | **$20/mes** | **$60/mes** | **$200/mes** |

**TCO a 3 años (50 usuarios, 5 oficinas):**

| Modalidad | Setup | 36 meses | **Total** |
|---|---|---|---|
| A) Cloud puro | $50 | $394 (36 × $11) | **$444** |
| B) Hibrido | $1,350 | $605 (36 × $17) | **$1,955** |
| C) On-premise | $1,500 | $2,160 (36 × $60) | **$3,660** |

**Ganador en TCO a 3 años:** **Modalidad A** (cloud puro) es 4-8x mas barato
que on-premise. La modalidad B es razonable cuando hay requisitos de
data residency.

---

## 10. Plan de implementacion

### Paso 1: Decidir la modalidad (1-2 horas)

**Preguntas para el cliente:**

1. Tienen internet estable y rapido en la oficina? (Si/No)
2. Necesitan que los datos queden en su pais? (Si/No)
3. Tienen requisitos de compliance especificos? (Cuales)
4. Cuantas bodegas/usuarios? (Numero)
5. Cual es el presupuesto mensual para infra? (USD)
6. Tienen personal de IT? (Si/No)
7. Prefieren SaaS (pago mensual) o licencia (pago unico)?

**Matriz de decision:**

| Si el cliente... | Entonces |
|---|---|
| Tiene internet + 1-50 usuarios + sin requisitos de data residency | **Modalidad A (Cloud)** |
| Tiene internet + 50+ usuarios + multi-region | **Modalidad A + Multi-Region** |
| Requiere data local + 1 oficina con internet | **Modalidad B (Hibrido)** |
| Requiere data local + 10+ oficinas | **Modalidad B + Multi-Office** |
| Internet inestable o cero internet | **Modalidad C (On-premise)** |
| Compliance estricto (banco, gobierno) | **Modalidad C con WireGuard** |

### Paso 2: Setup inicial (1-3 dias)

**Modalidad A (Cloud puro):**
- Ver `docs/DEPLOY.md` seccion 3 (Setup paso a paso)
- Tiempo: 2-3 horas

**Modalidad B (Hibrido):**
1. Comprar Mini PC (verificar con el cliente)
2. Instalar Ubuntu Server 22.04
3. Levantar la BD local (docker compose)
4. Configurar Cloudflare Tunnel
5. Desplegar la API en el VPS cloud
6. Validar end-to-end

**Modalidad C (On-premise):**
1. Instalar Ubuntu Server 22.04 en el servidor del cliente
2. Clonar el repo
3. Levantar el stack completo
4. Generar certs self-signed
5. Configurar DNS local
6. Capacitar al cliente para operar

### Paso 3: Validacion (1 dia)

- E2E del manual de usuario (43/43 verde)
- Pruebas de latencia (operario en LAN vs internet)
- Pruebas de failover (apagar internet, ver que pasa)
- Backup y restore (DRP drill)

### Paso 4: Go-live (1-2 semanas)

- Onboarding del cliente (ver seccion 11 de `MULTI_EQUIPO_MULTI_LOCACION.md`)
- Monitoreo activo durante 1-2 semanas
- Iterar segun feedback

---

## 11. Como elegir la modalidad correcta

### Diagrama de decision

```
                    ¿Tienen internet estable?
                              |
                    +---------+---------+
                    |                   |
                   SI                  NO
                    |                   |
                    v                   v
        ¿Datos deben quedar       Modalidad C
         en su pais?              (On-premise)
                    |
          +---------+---------+
          |                   |
         SI                  NO
          |                   |
          v                   v
  Modalidad B           ¿>100 usuarios
  (Hibrido)             o multi-region?
                              |
                    +---------+---------+
                    |                   |
                   SI                  NO
                    |                   |
                    v                   v
             Modalidad A          Modalidad A
             (Cloud + Multi)       (Cloud puro)
```

### Recomendacion por tipo de cliente

| Tipo de cliente | Modalidad | Por que |
|---|---|---|
| Startup / PYME con 1-3 bodegas | A (Cloud) | Bajo costo, sin ops |
| Empresa mediana con 5-20 bodegas en 1 pais | A (Cloud) | Costo razonable, performance OK |
| Empresa grande con 50+ bodegas en 1 pais | A o B (Hibrido) | Data residency opcional |
| Empresa con sucursales en 3+ paises | A + Multi-Region | Latencia <100ms global |
| Banco / gobierno / defensa | C (On-premise) + WireGuard | Compliance estricto |
| Faena minera / barco / campo | C (On-premise) | Sin internet confiable |
| Distribuidora con 100+ clientes SaaS | A (Cloud) + Multi-Tenant | Modelo SaaS, 1 sola instalacion |

---

## 12. Decision y siguientes pasos

### Recomendacion por defecto

**Para el 90% de los clientes:** **Modalidad A (Cloud puro)**.
- Costo: $6-11/mes
- Setup: 2-3 horas
- Operacion: ~0 horas/mes (cloud)
- Latencia: 30-50ms (con VPS en LATAM) a 200ms (con VPS en EU)
- Recomendado para empezar: **VPS en Google Cloud `southamerica-east1` (Santiago)** para clientes en Chile/Peru/Argentina

**Si el cliente pide data residency:** **Modalidad B (Hibrido)**.
- Costo: $400-500 inicial + $5-10/mes
- Setup: 1-2 dias
- Operacion: ~1-2 horas/mes (mantenimiento Mini PC)
- Cloudflare Tunnel para acceso seguro

**Si el cliente no tiene internet:** **Modalidad C (On-premise)**.
- Costo: $400-2000 inicial (hardware) + $0-20/mes
- Setup: 1-2 dias
- Operacion: 2-4 horas/mes (mantenimiento + backups)

### Plan inmediato

1. **Esta semana:** definir con el equipo/cliente la modalidad.
2. **Mes 1:** setup inicial + onboarding del primer cliente.
3. **Mes 2-3:** operar en produccion, monitorear, iterar.
4. **Mes 6:** revisar la decision segun uso real. Si crecen a >100
   usuarios, migrar a Modalidad A + Multi-Region.

### Proximos pasos concretos

1. **Documentar la decision** en `docs/operations/DEPLOY_DECISIONS.md`:
   - Por que elegimos X modalidad
   - Que trade-offs consideramos
   - Cuando revisaremos la decision
2. **Crear templates** de deploy para cada modalidad:
   - `infra/docker/cloud-only.yml` (Modalidad A)
   - `infra/docker/hybrid-local-db.yml` (Modalidad B)
   - `infra/docker/on-premise-full.yml` (Modalidad C)
3. **Documentar troubleshooting** especifico de cada modalidad.
4. **Testear failover** en cada modalidad (apagar internet, ver que pasa).

### Contacto

- **Slack:** #bodega-dev
- **Email:** dev@bodega.cl
- **Documentacion relacionada:**
  - `docs/DEPLOY.md` — Manual de despliegue completo
  - `docs/PROPUESTA_PRODUCCION.md` — Cloud puro en detalle
  - `docs/MULTI_EQUIPO_MULTI_LOCACION.md` — Multi-tenant + multi-locacion
  - `docs/operations/https-rollout-runbook.md` — HTTPS en detalle
  - `docs/operations/DRP_DRILL_REPORT_2026-07-24.md` — DRP probado

---

## Anexo A: Setup completo Modalidad B (paso a paso)

### A.1 Hardware recomendado (Mini PC)

| Modelo | CPU | RAM | SSD | Precio | Notas |
|---|---|---|---|---|---|
| **Beelink Mini S12 Pro** | N100 (4C/4T) | 8 GB | 256 GB | $180 | Barato, eficiente, ideal para 1-10 usuarios |
| **Beelink EQ12** | N100 (4C/4T) | 16 GB | 500 GB | $300 | Recomendado, balance precio/rendimiento |
| **Intel NUC 13 Pro** | i7-1360P (12C/16T) | 32 GB | 1 TB | $900 | Para 50+ usuarios |
| **Protectli VP2420** | N100 | 8 GB | 256 GB | $350 | Especializado para firewalls, super bajo consumo |
| **HP ProDesk 400 G9 Mini** | i5-12500T | 16 GB | 512 GB | $700 | Marca conocida, garantia 3 anos |

**Recomendado:** Beelink EQ12 o Protectli VP2420 (~$300-350, 16 GB RAM, fanless).

### A.2 OS y software

- **OS:** Ubuntu Server 22.04 LTS (soporte hasta 2027)
- **Docker:** docker.io + docker-compose-v2
- **SSH:** preinstalado
- **fail2ban:** proteccion contra brute-force
- **ufw:** firewall

### A.3 Comandos completos de setup

```bash
# === En la Mini PC del cliente ===

# 1. Instalar Ubuntu Server 22.04 LTS (durante el boot)
# - Hostname: bodega-hvm-oficina
# - Usuario: deploy
# - SSH: enabled

# 2. Configurar red estatica (opcional, recomendado para servidores)
sudo nano /etc/netplan/01-netcfg.yaml
# network:
#   version: 2
#   ethernets:
#     eno1:
#       dhcp4: no
#       addresses: [192.168.1.100/24]
#       gateway4: 192.168.1.1
#       nameservers: [8.8.8.8, 1.1.1.1]
sudo netplan apply

# 3. Instalar Docker y dependencias
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2 fail2ban ufw curl git
sudo systemctl enable docker

# 4. Configurar firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# 5. Clonar el repo
sudo mkdir -p /opt/bodega
sudo chown deploy:deploy /opt/bodega
sudo -u deploy git clone https://github.com/Renanakin/bodega.git /opt/bodega
cd /opt/bodega

# 6. Generar secrets
sudo -u deploy python3 infra/scripts/generate-secrets.py

# 7. Configurar .env (con secrets reales)
sudo -u deploy cp infra/docker/.env.production.example infra/docker/.env.production
sudo -u deploy nano infra/docker/.env.production
# Pegar los secrets generados en el paso 6
# Configurar:
#   DATABASE_URL=postgresql+asyncpg://bodegaje:<pwd>@db:5432/bodegaje
#   REDIS_URL=redis://redis:6379/0
#   CORS_ALLOWED_ORIGINS=https://app.bodega.cl,https://hvm.bodega.cl
#   ENVIRONMENT=production
#   DEBUG=false
#   ...

# 8. Levantar SOLO db + redis + cloudflared
sudo -u deploy docker compose -f infra/docker/docker-compose.yml \
    -f infra/docker/hybrid-local-db.yml \
    --env-file infra/docker/.env.production \
    up -d

# 9. Aplicar migraciones
sudo -u deploy docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "SELECT 1;"
sudo -u deploy docker exec bodegaje-api alembic upgrade head

# 10. Instalar cloudflared
sudo curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install -y cloudflared

# 11. Login y crear tunnel
sudo cloudflared tunnel login
sudo cloudflared tunnel create bodega-hvm-db
sudo nano /etc/cloudflared/config.yml
# tunnel: bodega-hvm-db
# credentials-file: /etc/cloudflared/<UUID>.json
# ingress:
#   - hostname: db.bodega.cl
#     service: tcp://localhost:5432
#   - service: http_status:404
sudo cloudflared tunnel route dns bodega-hvm-db db.bodega.cl
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# 12. Validar
sudo cloudflared tunnel info bodega-hvm-db
# Output: Your tunnel is connected to Cloudflare Edge.

# 13. Probar acceso desde internet
# (en cualquier laptop con internet)
# Instalar cloudflared localmente:
# brew install cloudflared  (Mac)
# choco install cloudflared  (Windows)
# Crear tunnel cliente: cloudflared access tcp --hostname db.bodega.cl --listener localhost:5432
# Conectar: psql -h localhost -p 5432 -U bodegaje -d bodegaje
```

### A.4 Configuracion de la API en el VPS cloud

```bash
# === En el VPS (no en la oficina del cliente) ===

# 1. El .env.production del VPS tiene la URL de la BD local via tunnel:
cat .env.production | grep DATABASE_URL
# DATABASE_URL=postgresql+asyncpg://bodegaje:<pwd>@db.bodega.cl:5432/bodegaje
# (db.bodega.cl resuelve via Cloudflare DNS al tunnel de la oficina del cliente)

# 2. Verificar conectividad desde el VPS al tunnel
docker run --rm alpine nc -zv db.bodega.cl 5432
# Si funciona, la API del VPS puede conectarse a la BD local del cliente.

# 3. Levantar la API
docker compose -f infra/docker/cloud-api-only.yml up -d
```

### A.5 Validacion end-to-end

```bash
# 1. La BD local responde a queries
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "SELECT count(*) FROM warehouses;"

# 2. El tunnel esta conectado
sudo cloudflared tunnel info bodega-hvm-db

# 3. La API (en el VPS) puede acceder a la BD via tunnel
docker exec bodegaje-api python -c "
import asyncio
from app.db.session import get_engine
async def test():
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute('SELECT 1')
        print('OK:', result.scalar())
asyncio.run(test())
"

# 4. El frontend puede acceder a la API
curl -sk https://app.bodega.cl/api/v1/health
# Esperado: {"status":"ok",...}

# 5. E2E del manual de usuario
cd auditoria-fase5
python e2e_manual_usuario.py
# Esperado: 43/43 verde
```

---

## Anexo B: Glosario de terminos

| Termino | Significado |
|---|---|
| **Cloudflare Tunnel** | Tunel saliente cifrado de Cloudflare que expone servicios sin abrir puertos |
| **Tailscale** | VPN mesh (red privada virtual) basada en WireGuard, ideal para acceso admin |
| **WireGuard** | VPN moderna, super rapida, parte del kernel Linux |
| **VPS** | Virtual Private Server: un servidor virtual en la nube |
| **Data residency** | Requisito legal de que los datos queden en un pais especifico |
| **Mini PC** | Computador pequeno y de bajo consumo (NUC, Beelink, etc.) ideal para instalar en oficinas |
| **SSL/TLS** | Protocolo de cifrado para HTTPS. Cert de Cloudflare = gratis, cert de Let's Encrypt = gratis con renovacion automatica. |
| **FQDN** | Fully Qualified Domain Name: el hostname completo (ej: `api.bodega.cl`) |
| **MTU** | Maximum Transmission Unit: tamano maximo de paquete de red. Importante para tuneles. |
| **DDNS** | Dynamic DNS: actualiza la IP publica del router cuando cambia (no aplica con Cloudflare Tunnel) |

---

**Anexo C: Comandos utiles para el operador**

```bash
# === Modalidad A (Cloud puro) ===

# Ver logs de la API
docker logs bodegaje-api --tail 50 -f

# Reiniciar la API despues de un cambio
docker compose -f infra/docker/docker-compose.yml restart api

# Backup manual
docker exec bodegaje-db pg_dump -U bodegaje -d bodegaje > /tmp/backup.sql

# === Modalidad B (Hibrido) - agregar ===

# Ver estado del tunnel
sudo cloudflared tunnel info bodega-hvm-db

# Reiniciar el tunnel
sudo systemctl restart cloudflared

# Ver logs del tunnel
sudo journalctl -u cloudflared -f

# Probar conexion a la BD via tunnel
# (desde una laptop con cloudflared instalado)
cloudflared access tcp --hostname db.bodega.cl --listener localhost:5432 &
psql -h localhost -U bodegaje -d bodegaje

# Backup local de la BD
docker exec bodegaje-db pg_dump -U bodegaje -d bodegaje | gzip > /mnt/backup/$(date +%Y%m%d).sql.gz

# Sincronizar backup a S3 (opcional, ademas del local)
aws s3 cp /mnt/backup/$(date +%Y%m%d).sql.gz s3://bodega-backups-hvm/

# === Modalidad C (On-premise) - agregar ===

# Ver uso de disco
df -h /mnt/bodega-data

# Verificar conectividad a la BD local
docker exec bodegaje-db pg_isready -U bodegaje

# Backup a USB
mount /dev/sdb1 /mnt/usb
docker exec bodegaje-db pg_dump -U bodegaje -d bodegaje | gzip > /mnt/usb/backup-$(date +%Y%m%d).sql.gz
umount /mnt/usb

# Actualizar el sistema (requiere acceso fisico o VPN)
cd /opt/bodega
sudo -u deploy git pull origin main
sudo -u deploy docker compose -f infra/docker/docker-compose.yml up -d --build
```

---

**Anexo D: Estimacion de esfuerzo de implementacion**

| Modalidad | Esfuerzo | Tiempo | Quien lo hace |
|---|---|---|---|
| A) Cloud puro | 4h | 1 dia | 1 dev |
| B) Hibrido (1 oficina) | 12h | 2 dias | 1 dev + 1 admin del cliente |
| B) Hibrido (3 oficinas) | 24h | 4 dias | 1 dev + 1 admin por oficina |
| C) On-premise (1 oficina) | 16h | 3 dias | 1 dev (en sitio) |
| C) On-premise (multi-oficina) | 40h | 1 semana | 1 dev + 1 admin por oficina |

Incluye: setup de hardware, instalacion de OS, configuracion de Docker,
setup de tuneles, validacion end-to-end, documentacion.
