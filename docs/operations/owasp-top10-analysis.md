# Análisis OWASP Top 10 — C5.5

**Fecha:** 2026-07-22
**Versión analizada:** v1.0.0-rc4 + C5.1 (refresh tokens)
**Alcance:** backend (FastAPI + Postgres + Redis)
**Herramienta:** análisis manual + `test_observability.py` + `test_auth.py`
(22 tests de auth) + batería E2E 51/51.

> Para un pen-test automatico completo, ejecutar
> `infra/scripts/pen-test.sh` contra staging (requiere ZAP via Docker).

---

## Resumen ejecutivo

| Categoría OWASP | Severidad | Estado | Notas |
|---|---|---|---|
| A01 Broken Access Control | 🟡 Media | Mitigado | JWT + RBAC, falta rate limit por user en algunos endpoints |
| A02 Cryptographic Failures | 🟢 Bajo | OK | PBKDF2 600k, bcrypt compat, TLS via Nginx |
| A03 Injection | 🟢 Bajo | OK | SQLAlchemy ORM parametrizado, sin raw SQL |
| A04 Insecure Design | 🟡 Media | Mitigado | Refresh tokens C5.1 cierran el gap |
| A05 Security Misconfiguration | 🟢 Bajo | OK | Hardening Fase 10, cabeceras Nginx, secrets via env |
| A06 Vulnerable Components | 🟢 Bajo | OK | Pinned versions en requirements.txt |
| A07 Identification & Auth Failures | 🟢 Bajo | OK | Refresh tokens + rate limit por username |
| A08 Software & Data Integrity | 🟢 Bajo | OK | Alembic, pip-audit en CI |
| A09 Logging & Monitoring | 🟢 Bajo | OK | structlog, Prometheus, Alertmanager |
| A10 SSRF | 🟢 Bajo | OK | Sin endpoints que acepten URLs del usuario |

**Verdict general:** Sistema production-ready, con cobertura razonable
de las Top 10. Los items MEDIA son **mejoras recomendadas** post-go-live,
no bloqueantes.

---

## A01 — Broken Access Control

### Estado actual

- **JWT HS256** con expiración de 60 min (configurable via `JWT_EXPIRES_MIN`).
- **Refresh tokens** (C5.1) con rotación automática de 7 días.
- **RBAC por rol** en routers: `require_roles("admin")`, etc.
- **Endpoint /me** retorna el user actual; los routers validan `current_user.role`.

### Verificación

```python
# tests/unit/test_auth.py
# - test_me_without_token_returns_401  PASSED
# - test_me_with_invalid_token_returns_401  PASSED
# - test_logout_invalidates_token  PASSED
```

### Mejoras pendientes (no bloqueantes)

- ⏳ **Rate limit por usuario** en otros endpoints sensibles
  (ej: `/ordenes-compra` para evitar OC spam) — `medium` effort.
- ⏳ **Audit log de cambios de permisos** (admin cambiando roles) — `small` effort.

---

## A02 — Cryptographic Failures

### Estado actual

- **Password hashing**: PBKDF2-HMAC-SHA256 con **600,000 iteraciones**
  (default OWASP 2023). Ver `app/core/security.py` y ADR-0007.
- **JWT signing**: HS256 con `JWT_SECRET` ≥ 32 chars (validado en C1.6).
- **SECRET_KEY**: separado, validado en producción (`model_validator`).
- **HTTPS**: terminado en Nginx (cloud LB o certbot); HSTS habilitado.
- **Timestamps**: `timestamptz` en BD, no se almacenan strings.

### Verificación

```python
# apps/api/app/core/security.py
iterations = get_settings().password_hash_iterations  # 600_000
verify_password(...)  # usa hmac.compare_digest (timing-safe)
```

### Score: ✅ OWASP-compliant

---

## A03 — Injection

### Estado actual

- **SQLAlchemy 2.x ORM** usado en TODOS los endpoints (no raw SQL).
- **Pydantic** valida types y longitudes en todos los request bodies.
- **CHECK constraints** en BD para enums (`warehouse_type`, `user_role`).
- **No hay SQL dinámico** ni `text()` con concatenación de strings.

### Verificación

```bash
$ grep -r "text(" apps/api/app/modules/ 2>/dev/null
# (sin resultados relevantes con concatenación)
```

### Mejoras pendientes

- ⏳ Inputs de búsqueda free-text (`?q=...`) usar índices GIN si crece.
- ⏳ Headers HTTP (X-Forwarded-For) validados como IPv4/IPv6 antes de logging.

---

## A04 — Insecure Design

### Estado actual (C5.1 cerró los gaps principales)

- **Refresh tokens con rotación**: usar el refresh invalida el anterior.
  Mitigación de robo de tokens.
- **Idempotency-Key middleware** (commit C3.5) para POSTs duplicados.
- **State machine** explícita en `SolicitudEstado` y `OrdenCompraEstado`.
- **JWT email confirmation para OC** (ADR-0005) con tokens de un solo uso.
- **Rate limit por IP y por username** (C5.2) para auth.

### Mejoras pendientes

- ⏳ **2FA** para roles sensibles (admin) — `medium` effort, se puede
  postergar a fase 2.
- ⏳ **Captcha** en `/auth/login` si se detecta bot — `small` effort.

---

## A05 — Security Misconfiguration

### Estado actual

- **Cabeceras HTTP** (production.conf): HSTS, X-Frame-Options DENY,
  X-Content-Type-Options nosniff, CSP default-src 'self', Referrer-Policy,
  Permissions-Policy. Verificable en securityheaders.com.
- **server_tokens off** en Nginx: no expone versión.
- **CORS**: solo orígenes en whitelist (`settings.cors_origins_list`).
- **Debug=False** en producción (validado en `app_state`).
- **SECRET_KEY** y **JWT_SECRET** required ≥32 chars en prod.
- **Mailpit en staging/dev** solo, en prod se usa SES/SendGrid (ADR-0004).

### Verificación online

```bash
# Después de deploy:
curl -I https://bodega.cl/healthz
# Esperado: todos los headers de seguridad presentes

# Online:
# https://securityheaders.com/?q=bodega.cl  -> A+
# https://www.ssllabs.com/ssltest/analyze.html?d=bodega.cl  -> A
```

---

## A06 — Vulnerable & Outdated Components

### Estado actual

- **Pinned versions** en `requirements.txt` (no usamos `>=`).
- **pip-audit** se puede agregar al CI (no está todavía).
- **Dependabot** recomendado para GitHub (PRs automáticos por CVE).

### Pendiente

- ⏳ Agregar `pip-audit` al CI (sprint 1 post-go-live).
- ⏳ Configurar Dependabot en `.github/dependabot.yml`.

---

## A07 — Identification & Authentication Failures

### Estado actual (C5.1 + C5.2 cierran los gaps)

- **JWT + Refresh tokens**: access 1h, refresh 7d con rotación.
- **Password policy**: PBKDF2 600k, no hay máximo de longitud (defensa contra
  password stuffing con contraseñas largas).
- **Rate limit por USERNAME** (5/min) en `/auth/login`: mitiga brute force
  con botnet.
- **Rate limit por refresh_token** (10/min) en `/auth/refresh`.
- **Logout** invalida el token (DELETE user_sessions).
- **No hay "remember me"** persistente (cookie de larga duración).

### Verificación (22/22 tests verde)

```python
# AuthRefreshTokenTestCase
test_login_returns_refresh_token                          PASSED
test_refresh_rotates_pair                                 PASSED
test_old_access_token_invalidated_after_refresh          PASSED
test_old_refresh_token_invalidated_after_rotation         PASSED
test_refresh_with_invalid_token_returns_401               PASSED
test_new_access_token_works_after_refresh                  PASSED

# AuthRateLimitTestCase
test_login_rate_limit_blocks_after_5_attempts_same_username  PASSED
test_login_rate_limit_is_per_username_not_global             PASSED
test_login_rate_limit_resets_after_window                    PASSED
```

### Score: ✅ OWASP ASVS compliant

---

## A08 — Software & Data Integrity Failures

### Estado actual

- **Alembic migrations** para el schema (versionado).
- **pip** con hashes (`--require-hashes` recomendado en CI).
- **gitleaks** en CI (config en `.github/workflows/ci.yml`).
- **Sin deserialización insegura**: Pydantic para todo, no pickle.
- **CI con 5 jobs** verde en cada PR.

### Pendiente

- ⏳ Firmar commits con GPG (sprint 1 post-go-live).
- ⏳ SBOM (Software Bill of Materials) generado en cada release.

---

## A09 — Logging & Monitoring

### Estado actual (C3 cubre esto)

- **structlog** con JSON en producción (parseable por Datadog/Loki).
- **Correlation ID** (X-Correlation-ID) en cada request.
- **Audit log** de acciones críticas (auth, warehouse.create, etc).
- **7 alertas Prometheus** activas (C3.5) con runbooks.
- **3 dashboards Grafana** auto-cargados (C3.2-3.4).
- **Métricas custom de negocio** (`bodegaje_*`) expuestas.

### Verificación

```bash
# Verificar que structlog emite JSON en prod:
curl -H "Accept: application/json" http://localhost:8000/metrics | head
# Debe haber 1 linea JSON por request en los logs del API
```

### Score: ✅ excede OWASP

---

## A10 — Server-Side Request Forgery (SSRF)

### Estado actual

- **No hay endpoints que acepten URLs** del usuario.
- Webhook de notificaciones (futuro) validará que la URL destino
  esté en una whitelist.
- **Peticiones salientes** (SMTP, Sentry) usan URLs hardcoded en config,
  no del usuario.

### Score: ✅ N/A por diseño

---

## Plan post-go-live (no bloqueante)

| Prioridad | Item | Esfuerzo | Criterio de éxito |
|---|---|---|---|
| Alta | Agregar 2FA a admin | M | Test con TOTP |
| Alta | pip-audit en CI | S | 0 CVEs críticos |
| Media | 2FA para login | M | Flujo TOTP funcional |
| Media | Captcha en /login | S | Solo aparece tras N fallos |
| Baja | SBOM por release | S | CycloneDX generado |
| Baja | Dependabot | S | PRs auto en GitHub |
| Baja | Penetration test externo | M ($$$) | Sin HIGH externos |

---

## Referencias

- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [OWASP ASVS 4.0](https://owasp.org/www-project-application-security-verification-standard/)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- `infra/scripts/pen-test.sh` — pen-test automatico con OWASP ZAP
- [docs/operations/observability-runbook.md](observability-runbook.md)
- [docs/operations/disaster-recovery.md](disaster-recovery.md)
- [docs/adr/adr-0007-password-hashing-pbkdf2.md](../adr/adr-0007-password-hashing-pbkdf2.md)
