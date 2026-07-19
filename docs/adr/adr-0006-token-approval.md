---
title: "ADR-0006: Token de aprobación de Órdenes de Compra"
status: "Proposed"
date: "2026-07-14"
authors: "Backend Lead, Security"
tags: ["architecture", "security", "decision", "phase-8"]
supersedes: ""
superseded_by: ""
---

# ADR-0006: Token de aprobación de Órdenes de Compra

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

## Context

La spec §3.3 define que cada email de Orden de Compra debe incluir **"Enlace con token temporal para aprobación"**. El receptor del email (supervisor) debe poder:

1. Click en el enlace sin necesidad de hacer login en la plataforma.
2. Aprobar o rechazar la OC con un click.
3. El token debe expirar (recomendado: 7 días).
4. El enlace no debe poder ser reutilizado después de la primera decisión (one-shot) o permitir cambios mientras esté vigente.

La decisión impacta: el módulo `ordenes_compra`, el template de email (ADR-0005), el endpoint público, y el modelo de seguridad.

## Decision

Adoptar **tokens firmados con HMAC-SHA256** (`itsdangerous.URLSafeTimedSerializer`), con las siguientes propiedades:

### Propiedades del token

- **Algoritmo**: HMAC-SHA256 con `settings.jwt_secret` como clave.
- **Vigencia**: 7 días desde la generación.
- **Payload**: `{orden_id: UUID, supervisor_id: UUID, action: "approve"|"reject", jti: UUID}`.
- **Transporte**: query string en la URL (`?token=...`).
- **Validación**: `itsdangerous.URLSafeTimedSerializer.loads(token, max_age=7*24*3600)`.
- **Idempotencia**: al primer uso, se marca `ordenes_compra.aprobado_por_token_at = now()`; usos posteriores devuelven 410 Gone.

### Endpoint público

```
GET  /api/v1/ordenes-compra/aprobar/{token}    # redirige a UI pública con detalles
POST /api/v1/ordenes-compra/aprobar/{token}    # body: {} → 200 + marca como aprobada
POST /api/v1/ordenes-compra/rechazar/{token}   # body: {motivo: "..."} → 200 + marca como rechazada
```

- **Sin autenticación**: el token ES la credencial.
- **Rate limit**: 10 requests/min por IP en estos endpoints (defensa contra fuerza bruta).
- **Auditoría**: cada uso del token genera `audit_logs` con `action=orden_compra.approved_by_token`.

### Seguridad

- **SEC-001**: el token NUNCA se loguea completo; solo su `jti` (UUID) y la IP de origen.
- **SEC-002**: `settings.jwt_secret` se rota anualmente; rotación invalida tokens vigentes (aceptable: emails con tokens viejos se reenvían).
- **SEC-003**: TLS obligatorio en producción (forzado en Nginx).
- **SEC-004**: `jti` se persiste en `ordenes_compra.token_jti` para detectar reuso.

## Consequences

### Positive

- **POS-001**: Implementación minimalista con `itsdangerous` (ya en stack FastAPI).
- **POS-002**: Sin base de datos adicional: el token se self-valida; solo se persiste `jti` para idempotencia.
- **POS-003**: 7 días es suficiente para que un supervisor responda; tokens viejos se invalidan automáticamente.
- **POS-004**: HMAC es estándar; verificable; no requiere infraestructura adicional.
- **POS-005**: La rotación anual de `jwt_secret` no requiere migrar tokens viejos (son one-shot).

### Negative

- **NEG-001**: Si se rota `jwt_secret` a mitad de vigencia, todos los tokens pendientes se invalidan (mitigar: avisar a supervisores con OC pendientes).
- **NEG-002**: El token en query string puede quedar en logs de proxies/HTTP_REFERER; mitigable con `Referrer-Policy: no-referrer` en la respuesta de la UI pública.
- **NEG-003**: HMAC no permite "revocar" un token antes de su expiración natural (mitigar: si se detecta compromiso, rotar `jwt_secret`).
- **NEG-004**: El payload visible para el supervisor (URL larga) puede parecer poco profesional (mitigar: usar un slug corto).

## Alternatives Considered

### JWT firmado con RS256

- **ALT-001**: **Description**: JWT estándar con par de claves RSA.
- **ALT-002**: **Rejection Reason**: overkill para tokens one-shot; gestión de claves RSA añade complejidad; no se gana nada sobre HMAC para este caso.

### Token aleatorio (UUID v4) almacenado en BD

- **ALT-003**: **Description**: generar `uuid.uuid4()`, guardar en `ordenes_compra.token`, validar contra BD.
- **ALT-004**: **Rejection Reason**: requiere leer BD en cada validación; HMAC se valida en memoria (más rápido); el UUID sin firma puede ser adivinado o manipulado si la BD tiene un SQL injection.

### Magic link con sesión temporal en Redis

- **ALT-005**: **Description**: crear sesión temporal en Redis al clickear, con TTL de 7 días.
- **ALT-006**: **Rejection Reason**: añade estado en Redis que puede perderse si Redis se reinicia; más complejo de revocar; HMAC es stateless y suficiente.

### Token sin expiración (one-shot, marcado al usar)

- **ALT-007**: **Description**: sin expiración, pero `ordenes_compra.aprobado_at` lo invalida al primer uso.
- **ALT-008**: **Rejection Reason**: si el email es interceptado y el token nunca se usa, sigue siendo válido indefinidamente. La expiración es defensa en profundidad.

## Implementation Notes

- **IMP-001**: Helper en `apps/api/app/shared/approval_token.py`:
  ```python
  def issue_approval_token(orden_id: UUID, supervisor_id: UUID, action: str) -> str: ...
  def verify_approval_token(token: str) -> dict: ...  # raises ExpiredSignatureError, BadSignature
  ```
- **IMP-002**: Tabla `ordenes_compra` añade columnas: `token_jti UUID NULL`, `aprobado_por_token_at TIMESTAMPTZ NULL`, `rechazado_por_token_at TIMESTAMPTZ NULL`, `token_motivo_rechazo TEXT NULL`.
- **IMP-003**: El endpoint público `GET /ordenes-compra/aprobar/{token}` NO muta; solo muestra detalles y CTAs. La mutación ocurre en `POST`.
- **IMP-004**: Test: emitir token → verificar OK → usar → reusar debe devolver 410 Gone.
- **IMP-005**: Test: token con firma manipulada → 401 Unauthorized.
- **IMP-006**: Test: token expirado (mockear `time`) → 410 Gone con código `token_expired`.
- **IMP-007**: En la UI pública, usar `noreply@bodega.local`风格的 email headers y `List-Unsubscribe` header (compliance).

## References

- **REF-001**: [itsdangerous docs](https://itsdangerous.palletsprojects.com/)
- **REF-002**: [OWASP Cheat Sheet — Insecure Direct Object Reference Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html)
- **REF-003**: ADR-0001 (Postgres, donde se persisten los `jti`)
- **REF-004**: ADR-0005 (SMTP, que transporta el token en el email)
- **REF-005**: `PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md` §3.3 (regla de token temporal)
