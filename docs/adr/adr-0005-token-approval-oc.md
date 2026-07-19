---
title: "ADR-0005: Token de aprobación de Órdenes de Compra"
status: "Accepted"
date: "2026-07-14"
authors: "Equipo Bodegaje"
tags: ["arquitectura", "seguridad", "tokens", "ordenes-compra"]
supersedes: ""
superseded_by: ""
---

# ADR-0005: Token de aprobación de Órdenes de Compra

## Status

**Accepted** — Decisión ratificada para la Fase 7 del roadmap.

## Context

La spec exige que el email al supervisor contenga un **"enlace de acceso rápido único con token temporal para aprobación directa desde el correo"**. Esto significa que el supervisor (que probablemente no tiene cuenta en el sistema) debe poder aprobar o rechazar una OC con un solo clic, sin tener que hacer login.

Hay tres formas de implementar este token:

1. **JWT firmado** — autocontenido, verificable sin lookup en BD
2. **HMAC firmado** — similar a JWT pero más simple, con expiración corta
3. **UUID random en BD** — se guarda el token en una tabla y se valida contra la BD

Cada una tiene trade-offs de seguridad, operacionalidad y complejidad.

## Decision

Adoptar **HMAC firmado con expiración de 7 días**, almacenando un hash del token en la tabla `ordenes_compra` (no el token en claro). El token se genera una sola vez al enviar el email y se invalida al aprobar/rechazar o al expirar.

### Formato del token

```
<orden_id>.<exp>.<signature>

donde:
- orden_id = UUID de la OC
- exp = Unix timestamp de expiración
- signature = HMAC-SHA256(orden_id + "." + exp, SECRET_KEY) en base64url
```

### Validación

```python
def validate_token(token: str) -> tuple[bool, str | None, str | None]:
    orden_id, exp, signature = token.split(".")
    expected_sig = hmac.new(SECRET_KEY, f"{orden_id}.{exp}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, base64url_decode(signature)):
        return False, None, "Firma inválida"
    if int(exp) < time.time():
        return False, None, "Token expirado"
    # Verificar que la OC no haya sido aprobada/rechazada
    oc = db.get(orden_id)
    if oc.estado in ("Aprobado", "Rechazado", "Comprado"):
        return False, None, "OC ya procesada"
    return True, orden_id, None
```

### Configuración

- `SECRET_KEY` (mínimo 32 bytes random) en variable de entorno, no en código
- `TOKEN_EXPIRATION_DAYS=7` configurable
- Rotación anual del `SECRET_KEY` invalida todos los tokens pendientes (procedimiento documentado)

## Consequences

### Positive

- **POS-001**: No requiere login del supervisor — UX optimizada.
- **POS-002**: HMAC es criptográficamente robusto (sin colisiones prácticas).
- **POS-003**: No persiste el token en claro — si la BD se filtra, los tokens no son recuperables sin `SECRET_KEY`.
- **POS-004**: Stateless validation (no requiere lookup para verificar firma).
- **POS-005**: Expiración corta (7 días) limita ventana de ataque.
- **POS-006**: Un solo clic en el email lleva a `/ordenes-compra/aprobar/:token` con confirmación visual.

### Negative

- **NEG-001**: Si se rota `SECRET_KEY` antes de los 7 días, los tokens pendientes quedan inválidos.
- **NEG-002**: El supervisor podría reenviar el email (forward) y alguien más aprobaría — riesgo aceptable según spec.
- **NEG-003**: No hay auditoría de "quién" aprobó, sólo "qué OC y cuándo" (la auditoría dice `email_aprobado=true`, no `usuario_id`).
- **NEG-004**: Requiere guardar `email_token_hash` y `email_token_expires_at` en `ordenes_compra`.

## Alternatives Considered

### JWT firmado

- **ALT-001**: **Description**: Token estándar con header.payload.signature.
- **ALT-002**: **Rejection Reason**: Más complejo de lo necesario, mismo nivel de seguridad que HMAC, agrega una dependencia (`PyJWT`).

### UUID random en BD

- **ALT-003**: **Description**: `token = uuid4()` guardado en `ordenes_compra.email_token`.
- **ALT-004**: **Rejection Reason**: Token legible persiste en BD (fuga); validación requiere lookup; revocación más compleja.

### Login dedicado para supervisores

- **ALT-005**: **Description**: Usuario y contraseña por supervisor, flujo tradicional de auth.
- **ALT-006**: **Rejection Reason**: Fricción operacional alta, requiere gestión de credenciales, contradice la UX de "un solo clic" de la spec.

## Implementation Notes

- **IMP-001**: Migración `0008_ordenes_compra.sql` añade columnas `email_token_hash VARCHAR(128)`, `email_token_expires_at TIMESTAMPTZ`.
- **IMP-002**: Nuevo módulo `apps/api/app/modules/notifications/token.py` con `ApprovalTokenService.generate(oc_id)`, `validate(token)`, `invalidate(oc_id)`.
- **IMP-003**: Endpoint público (sin auth) `GET /api/v1/ordenes-compra/aprobar/:token` que muestra vista de confirmación.
- **IMP-004**: Endpoints públicos `POST /api/v1/ordenes-compra/aprobar/:token` y `POST /api/v1/ordenes-compra/rechazar/:token` con rate limiting (5 req/min por IP).
- **IMP-005**: `SECRET_KEY` se genera con `secrets.token_urlsafe(32)` en el primer arranque y se persiste en vault o `.env` (nunca en git).
- **IMP-006**: Al aprobar vía token, la OC pasa a `Aprobado`; al rechazar, a `Rechazado`. El token se invalida inmediatamente.
- **IMP-007**: Tests E2E: flujo completo de generación → envío email → click → aprobación → estado actualizado.

## References

- **REF-001**: `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md` §10 (decisión 8), §8.4
- **REF-002**: Spec del usuario (mensaje 2026-07-14) — sección 4.3 y regla de email
- **REF-003**: HMAC RFC 2104 — https://datatracker.ietf.org/doc/html/rfc2104
