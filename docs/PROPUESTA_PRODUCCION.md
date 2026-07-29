# Propuesta de Despliegue a Producción en Red/Web

> **Para:** el dueño del producto, el equipo tecnico, y el operador
> de deploy. Define como llevar el sistema Bodegaje v1.0.0
> (actualmente en dev local con 13 containers Docker) a un entorno
> **publicamente accesible** en internet, con HTTPS, dominio propio,
> BD gestionada, backups, monitoreo, y plan de DRP.
>
> **Estado del sistema:** v1.0.0 con F1-F7 del roadmap cerrados.
> E2E del manual de usuario 43/43 verde. Listo para produccion con
> los pendientes documentados en `docs/operations/GO_LIVE_CHECKLIST.md`.

---

## Indice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura objetivo](#2-arquitectura-objetivo)
3. [Opciones de hosting](#3-opciones-de-hosting)
4. [Opcion recomendada: VPS gestionado + Cloudflare](#4-opcion-recomendada-vps-gestionado--cloudflare)
5. [Plan de deploy paso a paso](#5-plan-de-deploy-paso-a-paso)
6. [DNS, dominio y TLS](#6-dns-dominio-y-tls)
7. [Backups y DRP en produccion](#7-backups-y-drp-en-produccion)
8. [Monitoreo y alertas 24/7](#8-monitoreo-y-alertas-247)
9. [Costos mensuales estimados](#9-costos-mensuales-estimados)
10. [Plan de migracion gradual](#10-plan-de-migracion-gradual)
11. [Pendientes v1.1 (mejoras continuas)](#11-pendientes-v11-mejoras-continuas)
12. [Decision final y siguientes pasos](#12-decision-final-y-siguientes-pasos)

---

## 1. Resumen ejecutivo

**Bodegaje v1.0.0** es un sistema de inventario multi-bodega
(FastAPI + React + Postgres 17 + Redis) que actualmente corre en
13 containers Docker locales. Para hacerlo **publicamente accesible
en internet** y dar servicio a multiples bodegas, necesitamos:

| Requisito | Como se resuelve |
|---|---|
| **Hosting** (donde corre la app) | VPS gestionado (Hetzner / DigitalOcean / Vultr) o PaaS (Railway / Render) |
| **Dominio propio** (bodega.cl) | Registrar dominio + DNS en Cloudflare |
| **HTTPS** (cert TLS valido) | Let's Encrypt via certbot O Cloudflare (modo Full/Strict) |
| **BD gestionada** (Postgres) | Servicio managed (Hetzner, Supabase, Neon) o self-hosted con backups |
| **Backups off-site** (DRP) | S3 / Backblaze B2 / Wasabi (~$5-10/mes por TB) |
| **Monitoreo 24/7** | UptimeRobot + Better Stack (free tier) + alertas Slack |
| **CDN + WAF** (anti-DDoS) | Cloudflare Free tier |
| **Email transaccional** (SMTP) | Amazon SES o Brevo (ex-Sendinblue), 10K emails/mes free |
| **Logs centralizados** | Better Stack Logs o Loki+Grafana self-hosted |

**Decision recomendada:** **VPS gestionado (Hetzner CAX11 o DigitalOcean
Basic) + Cloudflare Free + S3 para backups + SES para emails**.
Costo total: **~$30-50 USD/mes** para un sistema con 100-1000 usuarios
concurrentes y 10K transacciones/mes.

---

## 2. Arquitectura objetivo

```
                         [Internet]
                             |
                             v
                    +----------------+
                    |   Cloudflare   |  <- CDN + WAF + DDoS + DNS
                    |  (Free tier)   |  <- SSL termination (Full Strict)
                    +-------+--------+
                             |
                             v (HTTPS 443)
                    +----------------+
                    |  VPS Region    |  <- Hetzner FSN1 / DO NYC3
                    |  (Docker Host) |  <- Ubuntu 22.04 LTS
                    +-------+--------+
                            /|\
                           / | \
                          /  |  \
                         v   v   v
        +---------------+  +---------------+  +----------------+
        | bodegaje-     |  | bodegaje-     |  | bodegaje-      |
        | nginx         |  | api + worker  |  | web            |
        | (TLS/HSTS)    |  | (FastAPI/Arq) |  | (React/nginx)  |
        +---------------+  +-------+-------+  +----------------+
                                 |
                                 v
                          +-------------+
                          | bodegaje-   |
                          | db (Postgres|
                          | +Redis)     |
                          +------+------+
                                 |
                                 v
                          +-------------+
                          | Backup vol  |
                          | (volumen    |
                          |  local)     |
                          +------+------+
                                 |
                                 v (sync diaria)
                    +----------------+
                    |  S3 / B2       |  <- Backups cifrados off-site
                    |  (Backblaze)   |     retention 30d, daily + weekly
                    +----------------+
```

**Flujos de red en produccion:**

| Puerto | Servicio | Acceso |
|---|---|---|
| 80/443 | Nginx (TLS termination) | Publico (Cloudflare proxied) |
| 5432 | Postgres | Solo desde containers (red Docker interna) |
| 6379 | Redis | Solo desde containers (red Docker interna) |
| 8025 | Mailpit (dev) | NO expuesto en prod (usar SES) |
| 9090 | Prometheus | Solo via VPN o SSH tunnel |
| 3000 | Grafana | Solo via VPN o SSH tunnel |

---

## 3. Opciones de hosting

### Opcion A — VPS gestionado (RECOMENDADA para v1.0)

**Que es:** un servidor virtual (1-4 vCPU, 4-8 GB RAM) donde corres
tus propios containers Docker con `docker compose`.

| Proveedor | Plan | vCPU | RAM | SSD | Precio/mes | Region |
|---|---|---|---|---|---|---|
| **Hetzner Cloud** | CAX11 (ARM) | 2 | 4 GB | 40 GB | **$4.50** | Falkenstein, Helsinki |
| **Hetzner Cloud** | CAX21 (ARM) | 4 | 8 GB | 80 GB | **$9.50** | Falkenstein, Helsinki |
| **DigitalOcean** | Basic Droplet | 2 | 4 GB | 80 GB | $24 | NYC, SFO, AMS |
| **Vultr** | Cloud Compute | 2 | 4 GB | 80 GB | $24 | 32 locations |
| **Linode (Akamai)** | Dedicated 4GB | 2 | 4 GB | 80 GB | $24 | 11 regions |
| **OVH** | Starter | 2 | 4 GB | 40 GB | $7 | Strasbourg |

**Pros:**
- Control total del sistema (vos operas todo)
- Costo bajo, predecible, fijo
- Sin vendor lock-in
- Ideal para 10-1000 usuarios concurrentes

**Contras:**
- Vos operas el SO, Docker, backups, parches de seguridad
- Sin auto-scaling (hay que sobredimensionar)
- Sin redundancia geografica (single point of failure)
- Si el VPS cae, el sistema cae

**Para Bodegaje v1.0:** **Hetzner CAX11 (ARM, $4.50/mes)** es la opcion
optima. ARM es 30% mas eficiente para Python/Postgres. Si crece la
demanda, upgrade a CAX21 ($9.50/mes) sin downtime.

---

### Opcion B — PaaS (Platform-as-a-Service)

**Que es:** subis el codigo, la plataforma lo deploya y escala.

| Proveedor | Plan | Precio/mes | Notas |
|---|---|---|---|
| **Railway.app** | Starter | $5 + uso | Postgres incluido, deploy con `git push` |
| **Render** | Web Service + Postgres | $7 + $7 | Free tier limitado, SSL automatico |
| **Fly.io** | shared-cpu-1x | $3.74 + $1.94 (Postgres) | Multi-region, requiere Docker |
| **Heroku** | Eco dyno + Postgres Mini | $5 + $5 | El mas caro pero mas maduro |
| **Render** | Standard | $25 + $25 | Para produccion seria |
| **DigitalOcean App Platform** | Pro | $12 + $15 | SSL + CDN incluido |

**Pros:**
- Zero ops (no operas el OS)
- Deploy con `git push` o GitHub integration
- Auto-scaling, HTTPS automatico, backups incluidos
- Ideal para equipos chicos (<5 devs)

**Contras:**
- Mas caro que VPS a escala (3-5x)
- Vendor lock-in (cada PaaS tiene su formato)
- Menos control sobre el runtime (no podes tunear Postgres, por ej.)
- Free tier es muy limitado (se duerme despues de 15 min sin trafico)

**Para Bodegaje v1.0:** viable pero **3-5x mas caro** que VPS. Mejor
como **plan B** si el equipo decide no operar infra.

---

### Opcion C — Cloud (AWS / GCP / Azure)

**Que es:** servicios gestionados separados (EC2 + RDS + ElastiCache + S3 + CloudFront + ACM).

| Servicio | Precio/mes estimado |
|---|---|
| EC2 t3.medium (2 vCPU, 4GB) | $30 |
| RDS Postgres db.t3.micro (con backup) | $25 |
| ElastiCache Redis (cache.t3.micro) | $15 |
| S3 (100 GB backups) | $3 |
| CloudFront + ACM cert | $5 + free |
| Data transfer (1 TB/mes) | $10 |
| **Total** | **~$88/mes** |

**Pros:**
- Auto-scaling, multi-region, redundancia geografica
- Managed services (RDS hace backups automaticos, ElastiCache hace HA)
- Compliance y certificaciones (SOC2, HIPAA si aplica)
- Ideal para empresas con >1000 usuarios o SLAs estrictos

**Contras:**
- **5-10x mas caro** que VPS
- Complejidad alta (muchos servicios que aprender)
- Vendor lock-in fuerte
- Requiere DevOps dedicado

**Para Bodegaje v1.0:** **NO recomendado** hasta validar el modelo
de negocio. Costo minimo $88/mes vs $30/mes de VPS es 3x mas para
el mismo throughput.

---

### Tabla comparativa

| Criterio | VPS (Hetzner) | PaaS (Railway) | Cloud (AWS) |
|---|---|---|---|
| **Costo/mes (low traffic)** | **$4.50** | $5 + uso | $88+ |
| **Costo/mes (1000 users)** | **$9.50** | $30-50 | $200+ |
| **Costo/mes (10000 users)** | $50-100 | $200-500 | $1000+ |
| **Esfuerzo operacional** | Alto (vos operas) | Bajo | Medio |
| **Auto-scaling** | Manual | Automatico | Automatico |
| **SSL/HTTPS** | Manual (certbot) | Automatico | Automatico |
| **Vendor lock-in** | Ninguno | Medio | Alto |
| **Compliance** | DIY | Built-in | Built-in (SOC2) |
| **DRP geografico** | Manual (S3) | Built-in | Built-in |
| **Ideal para Bodegaje v1.0** | **SI** | SI (plan B) | NO (esperar v2) |

---

## 4. Opcion recomendada: VPS gestionado + Cloudflare

### 4.1 Setup del VPS

**Proveedor:** Hetzner Cloud (mejor relacion precio/rendimiento en EU/LATAM)

**Plan:** CAX11 (2 vCPU ARM, 4 GB RAM, 40 GB SSD) — **$4.50/mes**

**Region:** Falkenstein (FSN1, Alemania) o Helsinki (HEL1, Finlandia)
para latencia ~180-200ms desde Chile. Si tenes usuarios en LATAM,
considera **Hetzner Ashburn (US East)** o **DigitalOcean NYC3** para
~120-150ms desde Chile.

**OS:** Ubuntu 22.04 LTS (soporte hasta 2027, kernel estable, Docker oficial)

**Setup base (1 sola vez, via SSH):**

```bash
# Como root en el VPS
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2 ufw fail2ban

# Crear usuario no-root para operar
useradd -m -s /bin/bash deploy
usermod -aG docker deploy

# Firewall: solo 22 (SSH), 80 (HTTP->HTTPS), 443 (HTTPS)
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Fail2ban: proteccion contra brute-force SSH
systemctl enable fail2ban

# Instalar Docker
apt install -y docker.io
systemctl enable docker
```

### 4.2 Setup del DNS en Cloudflare

**Plan Cloudflare Free** (incluye DNS, CDN, WAF basico, DDoS protection, SSL):

```
bodega.cl         A    <IP_VPS>      Proxied  (Cloudflare CDN)
www.bodega.cl     A    <IP_VPS>      Proxied
api.bodega.cl     A    <IP_VPS>      Proxied
monitor.bodega.cl A    <IP_VPS>      DNS only  (no CDN, solo Grafana via VPN)
```

**Configuracion Cloudflare:**
- SSL/TLS → **Full (Strict)** mode
- Edge Certificates → **Always Use HTTPS: ON**
- Edge Certificates → **HSTS: max-age=31536000, includeSubDomains, preload**
- Speed → **Auto Minify: ON** (HTML, CSS, JS)
- Speed → **Brotli: ON**
- Caching → **Browser Cache TTL: 4 hours**
- Security → **Security Level: Medium**
- Security → **Challenge Passage: 30 minutes**

### 4.3 Setup del VPS para produccion

```bash
# Clonar el repo
sudo -u deploy git clone https://github.com/Renanakin/bodega.git /opt/bodega
cd /opt/bodega

# Crear el .env.production con secrets REALES (no commitear!)
sudo -u deploy cp infra/docker/.env.production.example infra/docker/.env.production
sudo -u deploy python infra/scripts/generate-secrets.py > /tmp/secrets.json
# Editar el .env.production con los secrets generados
sudo -u deploy nano infra/docker/.env.production

# Levantar la app en modo produccion
sudo -u deploy docker compose -f infra/docker/docker-compose.yml \
    --env-file infra/docker/.env.production \
    -f infra/docker/production.yml \
    up -d

# Validar
sleep 30
curl -sk https://api.bodega.cl/api/v1/health
# Esperado: {"status":"ok","environment":"production",...}
```

### 4.4 SSL/TLS automatico con Let's Encrypt (opcional, solo si NO usas Cloudflare proxy)

Si usas Cloudflare en modo Full (Strict), Cloudflare ya maneja el SSL
externo. **No necesitas certbot** en el VPS. Pero si el cliente quiere
acceder al VPS directamente (bypass Cloudflare), necesitas certs
locales con certbot:

```bash
# Instalar certbot
apt install -y certbot
certbot certonly --standalone -d api.bodega.cl -d www.bodega.cl

# Los certs quedan en /etc/letsencrypt/live/api.bodega.cl/
# Nginx los lee desde ahi.
```

**Recomendado:** dejar que Cloudflare maneje el SSL (Full Strict) y no
instalar certbot. Si Cloudflare cae, el sistema sigue accesible via IP
(pero sin cert valido, el browser mostrara warning).

---

## 5. Plan de deploy paso a paso

### Fase 1: Preparacion (Semana 1)

**Tareas (8-12 horas de trabajo):**

1. **Registrar el dominio `bodega.cl`** en NIC Chile (~15.000 CLP/ano)
2. **Crear cuenta en Cloudflare** (free) y agregar el dominio
3. **Configurar DNS en Cloudflare** (segun seccion 4.2)
4. **Contratar VPS en Hetzner** (CAX11, $4.50/mes)
5. **Setup base del VPS** (segun seccion 4.1)
6. **Crear bucket S3 en Backblaze B2** (free hasta 10 GB)
7. **Crear cuenta en Amazon SES o Brevo** para SMTP
8. **Crear secrets con `infra/scripts/generate-secrets.py`**
9. **Documentar runbook de deploy** (similar a `docs/operations/https-rollout-runbook.md`)

**Entregable:** VPS configurado, dominio apuntando, secrets generados.

### Fase 2: Deploy inicial (Semana 1, segundo dia)

**Tareas (4-6 horas):**

1. **Clonar el repo en el VPS** (`/opt/bodega`)
2. **Configurar `.env.production`** con secrets reales
3. **Levantar el stack** con `docker compose -f production.yml up -d`
4. **Validar health check** (`curl https://api.bodega.cl/api/v1/health`)
5. **Validar UI** (`https://www.bodega.cl`)
6. **Correr el E2E del manual de usuario** contra el sistema publico
7. **Configurar backup automatico** (cron en el VPS, output a S3)
8. **Configurar monitoreo basico** (UptimeRobot cada 5 min, alerta email)

**Entregable:** Sistema accesible en `https://www.bodega.cl`, E2E verde,
backups funcionando, monitoreo basico.

### Fase 3: Hardening + DRP (Semana 2)

**Tareas (8-12 horas):**

1. **Correr DRP drill** (`tests/perf/drp_drill.py` + escenario manual)
2. **Configurar restore desde S3** (verificar que se puede levantar
   una BD nueva a partir del ultimo backup en < 5 min)
3. **Configurar alertas en Slack** (Prometheus Alertmanager + webhook)
4. **Documentar procedimiento de rollback** (rollback a v1.0.0-rc4)
5. **Configurar Sentry** (error tracking, free tier 5K eventos/mes)
6. **Configurar log centralization** (Better Stack Logs o Loki+Grafana)
7. **Auditoria de seguridad** (nmap, nikto, OWASP ZAP)
8. **Configurar 2FA para admin** (mejora continua, ver pendientes v1.1)

**Entregable:** Sistema production-ready, monitoreado, con DRP probado.

### Fase 4: Migracion gradual (Semana 3-4)

**Tareas (ongoing):**

1. **Migrar usuarios reales** (los 4 precargados + crear nuevos segun necesidad)
2. **Capacitar a los operadores** (manual de usuario ya existe)
3. **Cargar catalogos reales** (productos, proveedores, bodegas)
4. **Migrar datos historicos** si los hay (de Excel/otro sistema)
5. **Monitorear activamente** durante 1-2 semanas
6. **Iterar** segun feedback de usuarios

**Entregable:** Sistema en uso productivo por usuarios reales.

---

## 6. DNS, dominio y TLS

### 6.1 Registrador de dominios recomendado

| Registrar | Precio .cl | Comentarios |
|---|---|---|
| **NIC Chile** (nic.cl) | ~$15.000 CLP/ano | Oficial, recomendado para .cl |
| **Cloudflare Registrar** | $10-12 USD/ano | Precio al costo, sin markup |
| **Namecheap** | $12-15 USD/ano | UI amigable, soporte 24/7 |

**Recomendado:** **NIC Chile** (oficial, soporta .cl) o **Cloudflare
Registrar** (si tenes varios dominios y queres simplificar la gestion).

### 6.2 Subdominios a configurar

```
bodega.cl              -> Marketing landing page (opcional, /index.html estatico)
app.bodega.cl          -> UI web (React + Vite, servido por Nginx)
api.bodega.cl          -> API REST (FastAPI, reverse-proxy via Nginx)
monitor.bodega.cl      -> Grafana (restringido por Cloudflare Access)
status.bodega.cl       -> Status page (UptimeRobot public)
```

### 6.3 Certificados TLS

**Opcion recomendada:** dejar que **Cloudflare maneje el SSL**.

| Capa | Manejado por |
|---|---|
| Visitante ↔ Cloudflare | Cloudflare Universal SSL (gratis) |
| Cloudflare ↔ VPS | Cloudflare Origin Certificate (gratis, 15 anos, auto-renovado) |
| VPS ↔ Containers | HTTP plano (dentro del Docker network) |

**Setup:**

1. Cloudflare → SSL/TLS → Origin Server → Create Certificate
2. Copiar el cert + private key al VPS en `/etc/nginx/certs/`
3. Configurar Nginx para usar ese cert

**Alternativa:** certbot + Let's Encrypt si el cliente quiere
acceder al VPS directamente (bypass Cloudflare):

```bash
certbot certonly --webroot -w /var/www/certbot \
    -d app.bodega.cl -d api.bodega.cl
```

---

## 7. Backups y DRP en produccion

### 7.1 Estrategia de backups

| Tipo | Frecuencia | Retencion | Storage | Costo |
|---|---|---|---|---|
| **Backup diario** (Postgres full) | 02:00 UTC | 7 dias | S3 / B2 | $0.50/mes |
| **Backup semanal** (Postgres full) | Domingos 03:00 | 4 semanas | S3 / B2 | $0.20/mes |
| **Backup mensual** (Postgres full) | 1ero del mes | 12 meses | S3 / B2 (Glacier) | $0.10/mes |
| **WAL archive** (continuous) | Continuo | 7 dias | S3 | $0.30/mes |
| **Configuracion** (.env, docker-compose) | Manual | Git + S3 versioning | $0 (Git) | - |

### 7.2 Setup de backups en el VPS

El sistema ya tiene `bodegaje-backup` configurado. Solo hay que:

1. **Crear bucket S3** en Backblaze B2 (10 GB free):
   ```
   B2_BUCKET=bodegaje-backups-prod
   B2_KEY_ID=<key-id>
   B2_APP_KEY=<app-key>
   ```

2. **Editar `infra/docker/.env.production`** con las credenciales

3. **Verificar que el cron del container `bodegaje-backup` este corriendo**:
   ```bash
   docker logs bodegaje-backup --tail 20
   # Debe mostrar "Backing up to s3://..." cada 24h
   ```

### 7.3 DRP drill trimestral

El sistema ya tiene `tests/perf/drp_drill.py` con 3 escenarios:
- DB down (recovery < 1 min)
- Code rollback (recovery < 2 min)
- Backup offsite restore (recovery < 5 min)

**Calendario:**
- Q1 2026: DRP drill completo (3 escenarios)
- Q2 2026: DRP drill completo
- ...

**Documentar resultados** en `docs/operations/DRP_DRILL_REPORT_YYYY-MM-DD.md`.

---

## 8. Monitoreo y alertas 24/7

### 8.1 Stack de monitoreo (todo free o casi free)

| Componente | Herramienta | Costo |
|---|---|---|
| **Uptime monitoring** (externo) | UptimeRobot (50 checks free) o Better Uptime | $0 |
| **APM / error tracking** | Sentry (5K eventos/mes free) | $0 |
| **Logs centralizados** | Better Stack Logs (5 GB free) | $0 |
| **Metricas + dashboards** | Grafana Cloud (free) o self-hosted | $0 |
| **Alertas** | Slack/PagerDuty webhook | $0 (Slack) o $21/user/mes (PagerDuty) |
| **Status page** (publica) | UptimeRobot status page o Instatus | $0 |

### 8.2 Alertas criticas (configurar desde dia 1)

| Alerta | Condicion | Destino |
|---|---|---|
| API down | Health check falla 2 veces seguidas (5 min) | Slack #alertas + SMS |
| Error rate alto | `rate(http_requests_total{status=~"5.."}[5m]) > 0.05` | Slack #alertas |
| Latencia p95 alta | `histogram_quantile(0.95, ...) > 1s` | Slack #alertas |
| Disco lleno | `disk_used_percent > 80%` | Slack #alertas |
| Backup fallo | Ultimo backup exitoso > 25h | Slack #alertas + email |
| Cert TLS expira | Cert expira en < 14 dias | Slack #alertas |
| Rate limit activado | `rate_limit_hits > 100/min` | Slack #seguridad |

### 8.3 Dashboard Grafana publico

**URL:** `https://monitor.bodega.cl` (protegido por Cloudflare Access,
solo accesible con email del equipo)

**Paneles:**
- API uptime (ultimas 24h / 7d / 30d)
- Latencia p50, p95, p99
- Error rate por endpoint
- Stock total por bodega
- Solicitudes pendientes de aprobacion
- OCs pendientes
- Big-O health (queries lentas)

---

## 9. Costos mensuales estimados

### Escenario bajo (Bodega unica, 5-10 usuarios, 1K transacciones/mes)

| Concepto | Proveedor | Plan | Costo/mes |
|---|---|---|---|
| **VPS** | Hetzner CAX11 | ARM 2 vCPU, 4 GB RAM | $4.50 |
| **Dominio** | NIC Chile | .cl | $1.25 (anual prorrateado) |
| **CDN + WAF + DNS** | Cloudflare | Free | $0 |
| **Backups** | Backblaze B2 | 5 GB | $0.05 |
| **Email transaccional** | Brevo (ex-Sendinblue) | Free 300 emails/dia | $0 |
| **Uptime monitoring** | UptimeRobot | Free 50 checks | $0 |
| **APM** | Sentry | Free 5K eventos | $0 |
| **Logs** | Better Stack | Free 5 GB | $0 |
| **Status page** | UptimeRobot status | Free | $0 |
| **TOTAL** | | | **~$6/mes** |

### Escenario medio (10-50 usuarios, 10K transacciones/mes)

| Concepto | Cambio | Costo/mes |
|---|---|---|
| **VPS** | Hetzner CAX21 (4 vCPU, 8 GB) | $9.50 |
| Resto igual | | $1.30 |
| **TOTAL** | | **~$11/mes** |

### Escenario alto (100-1000 usuarios, 100K transacciones/mes)

| Concepto | Cambio | Costo/mes |
|---|---|---|
| **VPS** | Hetzner CCX13 (AMD EPYC, 8 vCPU, 16 GB) | $32 |
| **BD gestionada** | Hetzner Managed Postgres 4 | $35 |
| **Redis gestionado** | Hetzner Managed Redis 2 | $15 |
| **Backups** | Backblaze B2 50 GB | $0.50 |
| Resto igual | | $1.30 |
| **TOTAL** | | **~$84/mes** |

### Escenario enterprise (1000+ usuarios, 1M+ transacciones/mes)

Migrar a **Cloud (AWS / GCP)** o **PaaS escalable**. Estimado:
**$300-500/mes** con auto-scaling, multi-region, y managed services
completos. Esto es para v2+ de Bodegaje.

---

## 10. Plan de migracion gradual

### Semana 1: Setup base
- Contratar dominio + Hetzner VPS
- Configurar DNS en Cloudflare
- Setup base del VPS (Docker, firewall, fail2ban)
- Clonar repo, configurar .env.production

### Semana 2: Deploy inicial
- Levantar el stack con `docker compose -f production.yml up -d`
- Validar health check
- Configurar backups a S3
- Configurar UptimeRobot + alertas basicas

### Semana 3: Hardening
- DRP drill completo
- Configurar Sentry + Better Stack
- Configurar 2FA para admin
- Auditar OWASP ZAP / nmap
- Documentar runbook de operacion

### Semana 4: Go-Live con 1 bodega piloto
- Cargar catalogos reales (productos, proveedores)
- Capacitar a 1-2 operadores
- Monitorear activamente
- Iterar segun feedback

### Mes 2-3: Expansion
- Agregar mas bodegas (multi-tenant via el campo `warehouse_id`)
- Optimizar performance si crece el trafico
- Considerar upgrade a Hetzner CAX21 si >50 usuarios

### Mes 6+: v1.1
- 2FA obligatorio (pendiente v1.1)
- Backup off-site a S3 con lifecycle policy
- WAF real (Cloudflare Pro $20/mes si hace falta)
- Pen-test externo (recomendado para SLA de pago)

---

## 11. Pendientes v1.1 (mejoras continuas)

Estos items son **mejoras continuas** post-launch. NO son bloqueantes
para v1.0, pero deberian implementarse en los primeros 3-6 meses.

| Prioridad | Item | Esfuerzo | Bloqueante? |
|---|---|---|---|
| 🟠 Media | 2FA obligatorio para admin | 8h | NO |
| 🟠 Media | Backup off-site a S3 con cifrado AES-256 | 4h | NO |
| 🟠 Media | Webhook Slack/PagerDuty real (reemplazar PLACEHOLDER) | 4h | NO |
| 🟠 Media | Pen-test externo (recomendado para SLA de pago) | - | NO |
| 🟢 Baja | Backup cada 1h (no diario) | 2h | NO |
| 🟢 Baja | WAF (Cloudflare Pro $20/mes) | 2h | NO |
| 🟢 Baja | Multi-region (Hetzner FSN + HEL) | 16h | NO |
| 🟢 Baja | CDN para assets estaticos del frontend | 2h | NO |
| 🟢 Baja | Status page publica (status.bodega.cl) | 4h | NO |
| 🟢 Baja | Documentacion de API con OpenAPI/Swagger | 8h | NO |
| 🟢 Baja | Mobile app (React Native) | 80h+ | NO |

---

## 12. Decision final y siguientes pasos

### Decision recomendada

**Opcion A — VPS gestionado (Hetzner CAX11) + Cloudflare Free + S3 (Backblaze) + SES/Brevo para email.**

| Concepto | Costo |
|---|---|
| **Costo mensual total** | **~$6-11/mes** (escala 10-50 usuarios) |
| **Costo anual total** | **~$70-130/ano** |
| **Costo de setup inicial** | **~$20** (1 mes de VPS + dominio) |
| **Tiempo de setup** | **3-4 semanas** (1 dev full-time) |

**Pros:**
- Costo minimo ($6/mes es muy accesible)
- Control total
- Sin vendor lock-in
- Cumple con todos los requisitos de F1-F7 del roadmap

**Contras:**
- Operar el VPS requiere alguien con experiencia Linux/Docker
- Si crece a >1000 usuarios, hay que migrar (lock-in bajo, no es problema)

### Plan inmediato (esta semana)

1. **Decidir** con el equipo si van con VPS (recomendado) o PaaS
2. **Contratar dominio** `bodega.cl` (15.000 CLP)
3. **Contratar VPS Hetzner CAX11** ($4.50/mes)
4. **Crear cuenta Cloudflare** (free)
5. **Seguir el plan de deploy paso a paso** (seccion 5)
6. **Validar el sistema** con el E2E del manual de usuario

### Proximos pasos

1. **Aprobar la propuesta** con el equipo
2. **Asignar budget** ($500 inicial: VPS + dominio + backups + email + monitoring)
3. **Ejecutar Fase 1** del plan de deploy (Semana 1)
4. **Documentar decisiones** en `docs/operations/DEPLOY_DECISIONS.md`
5. **Revisar el plan de migracion** (seccion 10) y adaptarlo a la realidad

### Contacto / preguntas

- **Slack:** #bodega-dev
- **Email:** dev@bodega.cl
- **Documentacion:** `docs/DEPLOY.md` (manual completo) + `docs/operations/`
- **Issues GitHub:** https://github.com/Renanakin/bodega/issues

---

## Anexo: Checklist de deploy a produccion

```bash
# 1. Pre-deploy (en tu laptop)
- [ ] Dominio registrado y DNS configurado en Cloudflare
- [ ] VPS contratado (Hetzner CAX11)
- [ ] Secrets generados con infra/scripts/generate-secrets.py
- [ ] .env.production completado con secrets REALES
- [ ] Repositorio clonado en el VPS (/opt/bodega)
- [ ] Bucket S3 creado para backups

# 2. Deploy inicial (en el VPS)
- [ ] docker compose -f production.yml up -d
- [ ] curl https://api.bodega.cl/api/v1/health → 200 OK
- [ ] https://www.bodega.cl → UI carga
- [ ] python e2e_manual_usuario.py → 43/43 verde

# 3. Hardening
- [ ] DRP drill ejecutado y documentado
- [ ] Backups automaticos a S3 (verificar primer backup)
- [ ] UptimeRobot configurado (check cada 5 min)
- [ ] Alertas Slack funcionando
- [ ] Sentry capturando errores
- [ ] Better Stack con logs centralizados
- [ ] OWASP ZAP / nmap ejecutados, sin findings criticos

# 4. Go-Live
- [ ] Usuarios reales cargados
- [ ] Catalogos reales (productos, proveedores, bodegas)
- [ ] Operadores capacitados
- [ ] Runbook de operacion documentado
- [ ] Status page publica (status.bodega.cl)
- [ ] DRP drill trimestral agendado

# 5. Post Go-Live (semanas 1-4)
- [ ] Monitoreo 24/7 activo
- [ ] Backups verificados (restore test)
- [ ] Performance baseline medido
- [ ] Plan de mejora continua (v1.1) definido
```

---

**Anexo: comandos utiles para el operador**

```bash
# Ver logs de la app en vivo
docker compose -f production.yml logs -f api

# Reiniciar la app despues de un cambio
docker compose -f production.yml restart api worker

# Ver el estado de los 13 containers
docker compose -f production.yml ps

# Entrar a un container para debug
docker compose -f production.yml exec api bash

# Backup manual (ademas del automatico)
docker compose -f production.yml exec backup /usr/local/bin/backup.sh

# Ver el tamano de la BD
docker exec bodegaje-db psql -U bodegaje -d bodegaje -c "SELECT pg_size_pretty(pg_database_size('bodegaje'));"

# Ver metricas en vivo
docker stats bodegaje-api bodegaje-db bodegaje-redis

# Actualizar el sistema (despues de un commit)
cd /opt/bodega
sudo -u deploy git pull origin main
sudo -u deploy docker compose -f production.yml up -d --build
```
