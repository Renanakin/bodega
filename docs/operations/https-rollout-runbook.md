# Runbook de HTTPS para Producción (C5.3)

**Fecha:** 2026-07-22
**Audiencia:** operador de deploy

---

## TL;DR

Bodegaje usa **dos opciones** para HTTPS en producción, dependiendo del
proveedor cloud. La configuración Nginx ya viene con los headers de
seguridad (C5.4 — HSTS, X-Frame-Options, CSP); solo falta agregar
TLS al listener 443.

| Opción | Pros | Contras | ¿Cuándo? |
|---|---|---|---|
| **A) Cloud Load Balancer** (ALB, CloudFront, GCP LB) | Renovación automática de certs, DDoS básico, WAF opcional | Dependencia del proveedor | Recomendado para prod |
| **B) certbot + Nginx local** | Independiente, full control | Renovación manual (o cron),运维 propio | VPS dedicado |

---

## Opción A — Cloud Load Balancer (recomendado)

### A.1 — AWS (ALB + ACM)

```bash
# 1. Crear un certificado en ACM con el dominio
aws acm request-certificate \
    --domain-name bodega.cl \
    --subject-alternative-names "*.bodega.cl" \
    --validation-method DNS

# 2. Crear un ALB que apunte a las instancias EC2/VPS
# - Listener: HTTPS 443 con el cert de ACM
# - Target group: las instancias en puerto 80 (HTTP plano interno)
# - Security group: permitir 443 desde internet, 80 solo desde el ALB

# 3. El Nginx interno NO necesita TLS; recibe HTTP plano desde el ALB
#    que ya termino TLS.
```

### A.2 — GCP (Cloud Load Balancer + Managed SSL)

```bash
# 1. Crear el cert managed en GCP
gcloud compute ssl-certificates create bodega-cert \
    --domains=bodega.cl,*.bodega.cl

# 2. Crear un HTTPS proxy
gcloud compute target-https-proxies create bodega-https-proxy \
    --ssl-certificate=bodega-cert \
    --url-map=bodega-url-map

# 3. Configurar una regla de forwarding
gcloud compute forwarding-rules create bodega-https-fr \
    --address=bodega-ip \
    --global \
    --target-https-proxy=bodega-https-proxy \
    --ports=443
```

### A.3 — Render (todo-en-uno)

Si deployan en Render, no necesitan configurar nada:
1. Dashboard > Service > Custom Domain
2. Agregar `bodega.cl`
3. Render provisiona el cert automaticamente via Let's Encrypt
4. El servicio interno sigue siendo HTTP

---

## Opción B — certbot + Nginx local

### B.1 — Instalación inicial

```bash
# 1. Instalar certbot + plugin de Nginx
sudo apt install certbot python3-certbot-nginx

# 2. Obtener cert (modo standalone: detiene Nginx por 1 min)
sudo certbot certonly --standalone -d bodega.cl -d *.bodega.cl

# Esto genera:
#   /etc/letsencrypt/live/bodega.cl/fullchain.pem
#   /etc/letsencrypt/live/bodega.cl/privkey.pem
```

### B.2 — Configurar Nginx con TLS

Editar `infra/docker/nginx/conf.d/production.conf` y agregar el bloque
`listen 443 ssl http2` con los paths al cert:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name bodega.cl *.bodega.cl;

    # Redirigir HTTP → HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name bodega.cl *.bodega.cl;

    # Certificados (montar el volumen en docker-compose)
    ssl_certificate     /etc/letsencrypt/live/bodega.cl/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bodega.cl/privkey.pem;

    # Session cache (mejora perf)
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # Protocolos y ciphers modernos (OWASP recommended)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # HSTS preload (1 año + subdominios + preload)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Resto de la config (location blocks, etc)
    location /api/ {
        proxy_pass http://api:8000;
        # ... (igual que production.conf actual)
    }
    # ...
}
```

### B.3 — docker-compose con certs

```yaml
services:
  nginx:
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - ./nginx/conf.d/production.conf:/etc/nginx/conf.d/default.conf:ro
    ports:
      - "80:80"
      - "443:443"
```

### B.4 — Renovación automática (cron)

```bash
# 1. Editar crontab
sudo crontab -e

# 2. Agregar (corre cada día a las 03:00, intenta renovar si quedan <30 días)
0 3 * * * certbot renew --pre-hook "docker compose -f /opt/bodega/infra/docker/docker-compose.yml stop nginx" --post-hook "docker compose -f /opt/bodega/infra/docker/docker-compose.yml start nginx" >> /var/log/certbot-renew.log 2>&1
```

### B.5 — Verificar

```bash
# Test desde el host
curl -I https://bodega.cl/healthz

# Headers esperados:
#   HTTP/1.1 200 OK
#   Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
#   X-Frame-Options: DENY
#   X-Content-Type-Options: nosniff
#   Server: nginx  (sin version number)
```

```bash
# Test online: securityheaders.com
# https://securityheaders.com/?q=bodega.cl
# Objetivo: nota A o A+
```

---

## Cabeceras de seguridad (C5.4) — verificado en `production.conf`

El template `production.conf` ya incluye:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- `X-Frame-Options: DENY` (anti-clickjacking)
- `X-Content-Type-Options: nosniff` (anti-MIME confusion)
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'; ...` (anti-XSS)
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`
- `X-Correlation-ID: preserva para trazabilidad end-to-end`

Verificable en https://securityheaders.com — objetivo **A+**.

---

## Checklist pre-HTTPS

- [ ] DNS de `bodega.cl` apunta a la IP del servidor (o ALB)
- [ ] Cert valido (no auto-firmado)
- [ ] HSTS header presente
- [ ] `http://` redirige a `https://` con 301
- [ ] `securityheaders.com` da A+
- [ ] `ssllabs.com/ssltest` da A o A+ (si usaron Opción B)
- [ ] Renovar cert automaticamente (cron, Opción B) o via cloud (Opción A)
- [ ] Backups del cert y la key en lugar seguro (1Password / Vault)

---

## Troubleshooting

### "ERR_CERT_AUTHORITY_INVALID"
- Cert auto-firmado o expirado. Renovar o instalar cert de CA reconocida.

### HSTS no se aplica
- Verificar que el header se setea **después** del redirect HTTP→HTTPS.
- En `production.conf` está en el bloque 443, no en el 80.

### Nginx no levanta con el cert
- Verificar que el path al cert existe dentro del contenedor.
- `docker exec bodegaje-nginx ls -la /etc/letsencrypt/live/bodega.cl/`

### WebSocket rompe
- Si usan WS (todavía no implementado), agregar upgrade header en el bloque 443.

---

## Referencias

- [Let's Encrypt documentation](https://letsencrypt.org/docs/)
- [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/)
- [OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
- `infra/docker/nginx/conf.d/production.conf` (template con cabeceras)
- [disaster-recovery.md](disaster-recovery.md) — qué hacer si el cert expira
