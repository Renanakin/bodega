# Roadmap 100% Producción — Bodegaje v1.0.0

**Fecha:** 2026-07-24
**Estado actual:** ~85% producción-ready (staging OK, faltan bloqueantes de go-live público)
**Tag actual:** v1.0.0
**Sistema en vivo:** 13 containers healthy, batería E2E 5/5 verde (65.6s)

## TL;DR

7 fases para llegar al 100%. Tiempos totales estimados:

| Modalidad | Tiempo total | Esfuerzo | Riesgo |
|---|---|---|---|
| **VPS propio (certbot + nginx local)** | 2-3 días | DevOps 0.5 FTE | Bajo |
| **Cloud (LB con TLS termination)** | 1-2 días | DevOps 0.25 FTE | Bajo |
| **Enterprise (pen-test + ISO 27001)** | 5-7 días | DevOps 0.5 + SecEng 0.5 FTE | Medio |

---

## Estado actual (auditoría 2026-07-24)

### ✅ Listo

- 13 containers healthy (api, web, db, redis, mailpit, nginx, prometheus, grafana, alertmanager, 2 exporters, worker, backup)
- Tag v1.0.0 pusheado, rama main limpia
- 5/5 tests E2E verde (`.\test-e2e.ps1`, 65.6s)
- 34 unit tests del backend
- Backup diario automático con supercronic + pg_dump -Fc + gzip (rotación 7d)
- Refresh tokens con rotación (C5.1)
- Rate limit por usuario (5 logins/min) y por IP en endpoints públicos (C5.2)
- Manual de usuario (43KB) + cheatsheet + go-live runbook
- HTTPS runbook + OWASP analysis + DRP
- Frontend dist/ construido y servido por nginx:alpine

### ⚠️ Bloqueantes para 100% producción

| # | Gap | Impacto | Fase |
|---|---|---|---|
| 1 | **HTTPS no configurado** (nginx sirve HTTP plano) | OWASP A02:2021 - critico | F1 |
| 2 | **Secrets en `.env` en texto plano** | OWASP A02:2021 + A05:2021 | F2 |
| 3 | **Sin CI** (no hay validación automática en PRs) | Calidad de código | F3 |
| 4 | **Sin monitoreo 24/7 conectado a on-call** | Detección tardía de incidentes | F4 |
| 5 | **Sin DRP probado** (runbook existe, no testeado) | RTO/RPO no validados | F5 |
| 6 | **Sin pen-test externo** | Vulnerabilidades desconocidas | F6 |
| 7 | **Sin hardening deHeaders HTTP** (HSTS, CSP, X-Frame-Options) | XSS/clickjacking | F1 |

---

## Las 7 fases

### F1 — HTTPS + Headers de seguridad (Día 1, 4-6h)

**Objetivo:** Servir todo el tráfico por TLS con certificados válidos y cabeceras de seguridad activas.

**Por qué es la primera:** Es el bloqueante OWASP A02:2021 (Cryptographic Failures). Sin esto, **todo lo demás da igual** porque las credenciales viajan en plano.

**Tareas:**

1. **Decisión de topología (30 min):**
   - **Opción A — Certbot en VPS** (gratis, recomendado si tenés VPS propio)
   - **Opción B — LB en cloud** (ALB, GCP LB, Cloudflare) — recomendado si vas a cloud
   - Documento de decisión: `docs/operations/https-rollout-runbook.md` ya cubre ambos

2. **Generar/renovar certificados (1h):**
   ```bash
   # Opción A: certbot
   certbot certonly --nginx -d api.bodega.cl -d app.bodega.cl
   # Output: /etc/letsencrypt/live/bodega.cl/fullchain.pem + privkey.pem
   ```
   - Auto-renovación: cron `0 3 * * * certbot renew --quiet`
   - Backup de los certs al volumen de backup

3. **Configurar nginx con TLS (2h):**
   - Copiar `infra/production/nginx/conf.d/production.conf` (ya existe, verificar)
   - Habilitar HTTP→HTTPS redirect (301)
   - TLS 1.2+ only, cipher suite moderna (Mozilla intermediate)
   - HSTS con `max-age=31536000; includeSubDomains; preload`
   - CSP: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'`
   - X-Frame-Options: DENY
   - X-Content-Type-Options: nosniff
   - Referrer-Policy: strict-origin-when-cross-origin

4. **Validación (1h):**
   - `curl -I https://bodega.cl` debe responder 200 con HSTS
   - `https://www.ssllabs.com/ssltest/analyze.html?d=bodega.cl` debe dar A+
   - `nmap --script ssl-enum-ciphers -p 443 bodega.cl` no debe listar TLS 1.0/1.1

**Criterio Go/No-Go:**
- [ ] `curl -I https://bodega.cl` → 200 + HSTS
- [ ] SSLLabs A o A+
- [ ] `nmap ssl-enum-ciphers` sin TLS 1.0/1.1
- [ ] Redirect HTTP→HTTPS funcional

**Entregable:** URL pública `https://bodega.cl` con A+ en SSLLabs.

---

### F2 — Secrets manager + rotación de credenciales (Día 1-2, 4-6h)

**Objetivo:** Eliminar secretos en texto plano de `.env` y rotar las credenciales actuales.

**Tareas:**

1. **Inventario de secretos actuales (1h):**
   - DB passwords (postgres, redis)
   - JWT secret
   - SMTP credenciales (si se cambia de Mailpit a SES/SendGrid en prod)
   - API keys internas
   - Archivo: `docs/operations/SECRETS_INVENTORY.md`

2. **Elegir secrets manager (1h):**
   - **VPS:** HashiCorp Vault self-hosted (gratis, robusto)
   - **Cloud:** AWS Secrets Manager / GCP Secret Manager / Azure Key Vault
   - **Lightweight:** Doppler / Infisical (SaaS, gratis hasta N secrets)

3. **Migrar docker-compose para leer de secrets (2h):**
   ```yaml
   # Antes:
   environment:
     - DB_PASSWORD=admin12345
   # Después:
   environment:
     - DB_PASSWORD_FILE=/run/secrets/db_password
   secrets:
     - db_password
   secrets:
     db_password:
       external: true  # viene del secrets manager
   ```

4. **Rotar TODAS las credenciales que están en `.env` actual (1h):**
   - ⚠️ **CRÍTICO:** `infra/docker/.env` tiene `POSTGRES_PASSWORD=changeme` y similares
   - Cambiar ANTES de salir a producción
   - Invalidar todas las sesiones activas (forzar re-login)

5. **Validación (30min):**
   - El sistema arranca sin `.env` (solo con secrets manager)
   - Login funciona con credenciales nuevas
   - Las credenciales viejas no funcionan

**Criterio Go/No-Go:**
- [ ] `.env` borrado o no commiteado
- [ ] Secrets manager activo y consultado por el stack
- [ ] Credenciales rotadas y testeadas
- [ ] `git log --all --full-history -- infra/.env` no muestra secretos en texto plano

**Entregable:** `docs/operations/SECRETS_MANAGEMENT.md` + sistema sin secretos en disco.

---

### F3 — CI con GitHub Actions (Día 2, 6-8h)

**Objetivo:** Cada PR corre automáticamente la batería E2E + unit tests + linters.

**Por qué antes que F4-F6:** Sin CI, no podés saber si los cambios rompen algo. Esto blinda el camino a producción.

**Tareas:**

1. **Workflow de PRs (3h):** `.github/workflows/pr.yml`
   - Trigger: PR abierto/actualizado a `main`
   - Job 1: lint backend (`ruff check`, `black --check`)
   - Job 2: lint frontend (`eslint`, `prettier --check`)
   - Job 3: unit tests backend (`pytest apps/api/tests/unit`)
   - Job 4: build frontend (`npm run build`)
   - Job 5 (opcional): E2E con servicios levantados via `docker compose`
   - Cache: pip, npm

2. **Workflow de deploy (2h):** `.github/workflows/deploy-prod.yml`
   - Trigger: push a tag `v*.*.*`
   - Build de imágenes de producción
   - Push a registry (Docker Hub, GHCR, ECR)
   - Deploy via SSH al VPS o `kubectl apply`/terraform

3. **Secrets del CI (1h):**
   - `DATABASE_URL`, `JWT_SECRET`, etc. en GitHub Secrets
   - `SSH_KEY` para deploy
   - `DOCKER_REGISTRY_TOKEN` para push

4. **Branch protection (30min):**
   - `main` requiere: 1 approval, CI verde, no commits directos

5. **Validación (1h):**
   - PR de prueba dispara el CI
   - Todos los jobs pasan
   - El badge en README.md se actualiza

**Criterio Go/No-Go:**
- [ ] PR de prueba corre CI en < 10 min
- [ ] Todos los linters y tests pasan
- [ ] Deploy workflow hace push de imágenes a registry

**Entregable:** Badge verde de CI en el README + deploy automatizado.

---

### F4 — Monitoreo 24/7 con on-call (Día 2-3, 6-8h)

**Objetivo:** Las alertas de Alertmanager llegan a un humano disponible 24/7.

**Tareas:**

1. **Configurar Alertmanager (2h):**
   - SMTP a PagerDuty/OpsGenie (webhook)
   - Slack channel `#alertas-bodega` (webhook entrante)
   - Reglas de severidad:
     - **Critical (pagina):** API down, DB down, backup fallado 2 días seguidos
     - **Warning (Slack):** p95 latency > 500ms, error rate > 1%, disco > 80%
     - **Info (Slack):** deploy exitoso, backup OK

2. **Dashboards de Grafana (2h):**
   - Dashboard "Operaciones": CPU, memoria, disco, red
   - Dashboard "API": RPS, latencia p50/p95/p99, errores por endpoint
   - Dashboard "BD": conexiones activas, queries lentas, replication lag
   - Dashboard "OC": OC pendientes, OC en estado inconsistente, outbox backlog

3. **SLO/SLI definidos (1h):**
   - **Disponibilidad:** 99.5% mensual (~3.6h downtime/mes permitido)
   - **Latencia:** p95 < 300ms para endpoints autenticados
   - **Error rate:** < 0.5% de 5xx en endpoints públicos
   - Documento: `docs/operations/SLO.md`

4. **Sintético de monitoreo (1h):**
   - Cron cada 5min que hace GET /health y POST /auth/login
   - Si falla → alerta crítica
   - Puede ser un worker Arq o un script independiente

5. **Validación (1h):**
   - Bajar el API a propósito → llega alerta en Slack
   - Subir tráfico artificial → alerta de latencia
   - Llenar disco → alerta de espacio

**Criterio Go/No-Go:**
- [ ] Alertas de Critical llegan a PagerDuty en < 2 min
- [ ] Alertas de Warning llegan a Slack
- [ ] 3 dashboards de Grafana exportados a JSON en el repo
- [ ] SLO documentado con números concretos

**Entregable:** Canal de Slack con alertas + dashboards versionados en `infra/grafana/dashboards/`.

---

### F5 — DRP probado end-to-end (Día 3, 4-6h)

**Objetivo:** Validar que el procedimiento de disaster recovery funciona, con tiempos medidos.

**Por qué:** El runbook existe (`docs/operations/disaster-recovery.md`) pero **nunca se ha ejecutado en condiciones reales**. El primer incidente NO es el momento de descubrir que el procedimiento falla.

**Tareas:**

1. **Simular灾难 (1h):**
   - Escenario 1: `docker compose down bodegaje-db` y levantar desde backup
   - Escenario 2: borrar volumen `postgres_data` y restaurar
   - Escenario 3: rollback de código a v0.9.0

2. **Medir RTO/RPO reales (2h):**
   - **RTO** (Recovery Time Objective): tiempo desde desastre hasta servicio restaurado
   - **RPO** (Recovery Point Objective): cuántos datos se pierden (entre último backup y el incidente)
   - Tabla con los 3 escenarios medidos

3. **Documentar gaps del DRP (1h):**
   - Si RTO > 4h, considerar réplicas de lectura + failover automático
   - Si RPO > 1h, considerar backup cada 1h o WAL archiving

4. **Mejorar backup si es necesario (1h):**
   - Backup más frecuente si RPO es alto
   - Réplica read-replica si RTO es alto

5. **Validación (1h):**
   - Documento: `docs/operations/DR_TEST_REPORT_2026-07-XX.md`
   - Tabla con RTO/RPO por escenario
   - Plan de mejora si no cumple SLO

**Criterio Go/No-Go:**
- [ ] RTO < 4h validado
- [ ] RPO < 1h validado
- [ ] Runbook actualizado con los gaps encontrados
- [ ] Backup off-site configurado (S3, GCS, B2)

**Entregable:** Reporte de DRP con RTO/RPO medidos + backup off-site.

---

### F6 — Pen-test externo (Día 4-5, 8-16h)

**Objetivo:** Que un equipo externo valide la postura de seguridad antes de salir a producción.

**Por qué:** OWASP Top 10 + pruebas de penetración son estándar para producción. Un bug de seguridad encontrado en pen-test es 10x más barato de arreglar que uno encontrado en producción.

**Tareas:**

1. **Selección del vendor (2h):**
   - Opciones: HackerOne, Bugcrowd, Cobalt, Synack
   - Costo típico: $5k-$15k para un engagement de 1 semana
   - O alternativa:，邀请 comunidad (bug bounty público)

2. **Scope del pen-test (2h):**
   - API REST (autenticada + endpoints públicos)
   - Frontend (XSS, CSRF, clickjacking)
   - Infraestructura (containers, red, secrets)
   - Documento: `docs/operations/PENTEST_SCOPE.md`

3. **Engagement (5-10 días hábiles):**
   - El vendor prueba
   - Reuniones diarias de status
   - Reporte preliminar al final

4. **Triage de hallazgos (2-4h):**
   - Critical: fix en < 24h antes de go-live
   - High: fix en < 1 semana
   - Medium: backbox de 30 días
   - Low: documentar y aceptar riesgo

5. **Re-test (1-2 días):**
   - Después de fixear los Critical/High
   - El vendor valida que están resueltos

**Criterio Go/No-Go:**
- [ ] 0 hallazgos Critical sin resolver
- [ ] 0 hallazgos High sin resolver (o con plan de mitigación < 1 semana)
- [ ] Reporte de pen-test firmado y archivado

**Entregable:** `docs/operations/PENTEST_REPORT_2026-XX.pdf` + fixes deployados.

---

### F7 — Go-live + post-mortem (Día 6-7, 6-8h)

**Objetivo:** Salir a producción, monitorear 72h, escribir post-mortem.

**Tareas:**

1. **Pre-go-live checklist (2h):**
   - [ ] F1, F2, F3, F4, F5, F6 todas en verde
   - [ ] `git tag v1.0.0` (o v1.1.0 si hubo cambios)
   - [ ] DNS configurado
   - [ ] Secrets en producción (no staging)
   - [ ] Backup off-site verificado
   - [ ] DRP reciente (< 7 días)
   - [ ] On-call de guardia

2. **Deploy a producción (2h):**
   - Seguir `docs/go_live_runbook.md`
   - Generar `.env.production` con secrets del manager
   - `docker compose -f infra/docker/docker-compose.yml -f infra/docker/compose.production.yml up -d`
   - Smoke post-deploy

3. **Monitoreo 72h (ongoing, ~2h de gestión):**
   - Revisar dashboards cada 6h
   - Atender cualquier alerta
   - Latencia debe ser estable
   - Error rate < 0.5%

4. **Post-mortem (1h):**
   - `docs/operations/POST_MORTEM_2026-XX.md`
   - Métricas observadas
   - Incidentes (si los hubo) y resolución
   - Aprendizajes

5. **Cleanup (30min):**
   - Cerrar features flags
   - Limpiar logs viejos (> 90 días)
   - Archivar backups antiguos

**Criterio Go/No-Go final:**
- [ ] Sistema en producción 72h sin incidente crítico
- [ ] SLO cumplido
- [ ] Post-mortem escrito y revisado
- [ ] Backups off-site verificados post-go-live

**Entregable:** Tag v1.0.0 (o v1.1.0) en producción + post-mortem.

---

## Resumen visual

```
F1 HTTPS ──┐
           ├──> F2 Secrets ──┐
F3 CI ─────┘                  │
                              ├──> F4 Monitoreo ──┐
                              │                   │
                              │                   ├──> F5 DRP ──┐
                              │                   │             │
                              │                   │             ├──> F6 Pen-test ──┐
                              │                   │             │                  │
                              │                   │             │                  ├──> F7 Go-live
                              │                   │             │                  │
                              ▼                   ▼             ▼                  ▼
                          (security)         (operación)   (resiliencia)    (auditoría)   (producción)
```

## Dependencias

- **F1 debe ir antes de F2** (necesitamos HTTPS para el secrets manager remoto)
- **F3 puede ir en paralelo con F1-F2** (no depende)
- **F4 depende de F3** (CI deploya el agente de monitoring)
- **F5 puede ir en paralelo con F4** (no depende)
- **F6 depende de F1-F5** (no tiene sentido pen-test sin HTTPS)
- **F7 es la última** (integra todo)

## Recursos necesarios

| Recurso | Costo | Notas |
|---|---|---|
| Dominio `.cl` | ~$10k CLP/año | Obligatorio para HTTPS |
| Certbot | Gratis | Si vamos por VPS |
| LB cloud (si aplica) | $20-50 USD/mes | ALB, GCP LB |
| Secrets manager | $5-30 USD/mes | Vault, AWS SM, Doppler |
| Pen-test externo | $5-15k USD | Engagement de 1 semana |
| Sentry (error tracking) | Gratis hasta 5k events/mes | Recomendado |
| PagerDuty/OpsGenie | $10-30 USD/usuario/mes | Solo 1-2 personas en on-call |
| **TOTAL estimado** | **$8-20k USD one-time + $50-100 USD/mes** | Sin contar infra cloud |

## Riesgos identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Certbot falla en la primera request | Media | Bajo | Runbook tiene troubleshooting; probar en staging primero |
| Pen-test encuentra bug crítico | Media | Alto | Buffer de 2-3 días antes de go-live para fixear |
| DNS no se propaga a tiempo | Baja | Medio | Bajar TTL 48h antes del go-live |
| Backup off-site no restaura | Baja | Crítico | Hacer prueba de restore ANTES de go-live (F5) |
| On-call no disponible | Media | Alto | Mínimo 2 personas en rotación |

## Definition of Done (100%)

- [ ] F1: HTTPS con A+ en SSLLabs
- [ ] F2: 0 secretos en `.env`, todos en secrets manager
- [ ] F3: CI verde en cada PR, deploy automatizado
- [ ] F4: Alertas conectadas a on-call 24/7, SLO definido
- [ ] F5: DRP probado, RTO < 4h, RPO < 1h
- [ ] F6: Pen-test firmado, 0 Critical/High sin resolver
- [ ] F7: Tag v1.0.0+ en producción 72h+ sin incidente crítico

Cuando todo esté ✅, **el sistema está al 100% para producción**.

---

## Referencias

- `docs/go_live_runbook.md` — Runbook de deploy
- `docs/operations/https-rollout-runbook.md` — Runbook HTTPS (F1)
- `docs/operations/disaster-recovery.md` — Runbook DRP (F5)
- `docs/operations/owasp-top10-analysis.md` — Análisis OWASP (F6)
- `docs/operations/observability-runbook.md` — Runbook monitoring (F4)
- `docs/operations/api-db-validation-checklist.md` — Checklist pre-deploy
- `docs/roadmap_cierre_produccion.md` — Roadmap previo (este lo complementa)
- `tests/e2e/run_all.py` — Batería E2E (F3)
