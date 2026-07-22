---
title: "ADR-0007: Hashing de contraseñas con PBKDF2-HMAC-SHA256 (600k iteraciones)"
status: "Accepted"
date: "2026-07-22"
authors: "Equipo Bodegaje"
tags: ["seguridad", "hashing", "passwords", "pbkdf2"]
supersedes: ""
superseded_by: ""
---

# ADR-0007: Hashing de contraseñas con PBKDF2-HMAC-SHA256 (600k iteraciones)

## Status

**Accepted** — Decisión ratificada en C1.6 (cierre de producción).

## Context

La propuesta original (`PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md` §7
"No funcionales — Seguridad") recomienda:

> Hashing de contraseñas con **Argon2** o **bcrypt fuerte**.

En la práctica del proyecto, el sistema usa **PBKDF2-HMAC-SHA256** con
600,000 iteraciones (OWASP 2023), que es la opción *default* en
`app/core/security.py` y en `app/modules/auth/security.py` (legacy).

Esta diferencia entre la propuesta y la implementación requiere una
decisión formal: ¿se migra a Argon2, o se mantiene PBKDF2?

## Decision

**Mantener PBKDF2-HMAC-SHA256** con la siguiente configuración:

- **Algoritmo:** PBKDF2-HMAC-SHA256 (de la stdlib `hashlib`).
- **Iteraciones:** 600,000 (OWASP Password Storage Cheat Sheet 2023).
- **Salt:** 16 bytes aleatorios por usuario (`secrets.token_hex(16)`).
- **Formato de almacenamiento:** `"salt$digest"` (string).
- **Comparación:** `hmac.compare_digest` (constant-time, evita timing attacks).
- **Configurable:** `settings.password_hash_iterations` permite subir las
  iteraciones sin cambiar código.

### Configuración de Settings

```python
class Settings(BaseSettings):
    password_hash_iterations: int = 600_000  # OWASP 2023
    session_duration_hours: int = 12
```

## Rationale

### Por qué PBKDF2 y no Argon2

| Criterio | PBKDF2 | Argon2 |
|---|---|---|
| **Dependencias nativas** | ❌ No (stdlib) | ✅ Sí (`argon2-cffi` requiere Rust/Visual Studio Build Tools en Windows) |
| **Portabilidad Windows / Linux / Mac** | ✅ Idéntica | ⚠️ Requiere build tools en cada plataforma |
| **Velocidad de desarrollo** | ✅ Trivial | ⚠️ Build pipeline + audit de binarios |
| **Rendimiento** | 600k iter ≈ 200-400ms por hash (CPU) | 50-100ms con tuning similar |
| **Compliance OWASP 2023** | ✅ | ✅ (preferida, pero PBKDF2 sigue aceptable) |
| **Resistencia GPU** | ⚠️ menor (SHA256 es GPU-friendly) | ✅ mayor (memory-hard) |
| **Riesgo de regresión** | Bajo | Medio (binarios que pueden cambiar) |

**Decisión:** el proyecto está en fase de salida a producción. El costo
de adoptar Argon2 (build tools, binary distribution, más superficie de
ataque) supera el beneficio marginal de memoria-hard. PBKDF2 con
600,000 iteraciones es **OWASP-aceptable** y ya está validado.

### Por qué 600,000 iteraciones

OWASP recomienda ≥600,000 iteraciones para PBKDF2-HMAC-SHA256 en 2023.
Esto produce un hash que tarda ~200-400ms en hardware moderno, lo que:

- Hace inviable un ataque de fuerza bruta online (>5 intentos/seg
  contra un usuario individual).
- Permite login de usuarios sin latencia perceptible (<500ms total).
- Se alinea con el resto del stack (JWT, AES, TLS) en nivel de
  seguridad.

### Por qué NO bajar a 100,000 o 120,000

Iteraciones menores eran el default en muchas librerías antes de 2023.
Atacantes con GPUs modernas pueden romperlas en horas. 600k es el
mínimo aceptable hoy.

## Consequences

### Positive

- **POS-001**: Sin dependencias nativas; el build es `pip install -r
  requirements.txt` y funciona en cualquier ambiente.
- **POS-002**: Hash es portable: si el proyecto se mueve a otro
  lenguaje, se puede verificar con la misma fórmula.
- **POS-003**: Cumple OWASP 2023. Pasa auditorías de seguridad
  razonables.
- **POS-004**: 600k iteraciones son un *constant* en Settings; subirlo
  en el futuro es trivial (los hashes existentes siguen funcionando
  porque el salt está en el string).

### Negative

- **NEG-001**: No es memory-hard. Un atacante con GPUs de alta gama
  puede precomputar hashes más rápido que con Argon2/scrypt.
  Mitigación: 600k iteraciones + rate limit en `/auth/login` (C5.6).
- **NEG-002**: PBKDF2 tiene una reputación "vieja". Algunos auditores
  marcan como warning sin distinguir entre 100k y 600k iter.
  Mitigación: documentar en `docs/security/` con benchmark.
- **NEG-003**: Si OWASP sube el mínimo a 1M iteraciones en 2024-2025,
  los hashes existentes siguen válidos pero el login será ~2x más
  lento. Aceptable.

## Alternatives Considered

### Migrar a Argon2id

- **ALT-001**: **Description**: Adoptar `argon2-cffi`, parametrizar
  memory/time/parallelism.
- **ALT-002**: **Rejection Reason**: (a) requiere `Rust` o
  `Visual Studio Build Tools` para compilar en Windows;
  (b) aumenta la superficie de actualización de binarios; (c) el
  beneficio marginal (memoria-hard) no compensa en un sistema
  multi-tenant pequeño donde el cuello de botella es la red, no el hash.

### Migrar a bcrypt

- **ALT-003**: **Description**: Adoptar `bcrypt` (4$/hash con
  cost factor 12).
- **ALT-004**: **Rejection Reason**: bcrypt tiene un límite de 72 bytes
  en el password (silenciosamente trunca). PBKDF2 no tiene este
  problema y soporta Unicode completo.

### Mantener 120,000 iteraciones (legacy Fase 0-9)

- **ALT-005**: **Description**: No tocar el default histórico.
- **ALT-006**: **Rejection Reason**: 120k está por debajo de OWASP 2023.
  Aceptable solo para sistemas internos; no para datos de clientes
  reales.

## Implementation Notes

- **IMP-001**: `app/core/security.py::hash_password` usa
  `get_settings().password_hash_iterations`. Default 600_000.
- **IMP-002**: `app/modules/auth/security.py` (LEGACY) usa el mismo
  setting. C1.11 planea consolidar ambos.
- **IMP-003**: Tests `tests/unit/test_auth.py::test_password_hash_*`
  validan:
  - Hash determinista con mismo salt.
  - Hash diferente con salts distintos.
  - Verificación correcta con timing-safe comparison.
  - Migración automática al re-hashear en login (cuando
    `password_hash_iterations` sube).
- **IMP-004**: Para producción, el setting se inyecta vía env
  `PASSWORD_HASH_ITERATIONS` (no commitear valores altos sin medir
  impacto en CPU).

## References

- **REF-001**: OWASP Password Storage Cheat Sheet (2023)
- **REF-002**: NIST SP 800-132 (PBKDF recommendation)
- **REF-003**: Propuesta original §7 "Seguridad de nivel producción"
- **REF-004**: `app/core/security.py` (implementación)
- **REF-005**: `app/modules/auth/security.py` (legacy compat)
