---
title: "ADR-0006: Coexistencia Tailwind CSS con CSS plano del MVP"
status: "Accepted"
date: "2026-07-14"
authors: "Equipo Bodegaje"
tags: ["arquitectura", "frontend", "tailwind", "css"]
supersedes: ""
superseded_by: ""
---

# ADR-0006: Coexistencia Tailwind CSS con CSS plano del MVP

## Status

**Accepted** — Decisión ratificada para la Fase 8 del roadmap.

## Context

El MVP actual de `apps/web` usa **CSS plano con variables personalizadas** (en `apps/web/src/styles.css`, ~830 líneas, define tokens como `--bg`, `--accent`, `--danger`, etc.). El componente principal `AppShell.jsx` y las 11 vistas están estiladas con clases semánticas tipo `login-card`, `kpi-strip`, `empty-state`, etc.

La spec del usuario exige "React.js + Tailwind CSS" como stack. Tailwind es utility-first y entraría en conflicto con la especificidad del CSS plano actual.

Hay tres formas de abordar esta coexistencia:

1. **Big-bang**: reescribir todo el CSS a Tailwind en una sola migración
2. **Gradual**: vistas nuevas en Tailwind, viejas en CSS plano
3. **Solo nuevas**: nunca migrar el CSS viejo, solo usar Tailwind en vistas nuevas

## Decision

Adoptar la **Estrategia 3: Solo nuevas**. Las 11 vistas actuales **siguen con CSS plano sin tocar**. Las 8 vistas nuevas (Multibodega, Solicitudes, Recepción, Consolidador, OC, Aprobación Pública, Supervisores, Categorías) **nacen en Tailwind desde el día 1**.

### Setup

```json
// apps/web/package.json
{
  "devDependencies": {
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }
}
```

```js
// tailwind.config.js
module.exports = {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        'bodega-bg': 'var(--bg)',
        'bodega-accent': 'var(--accent)',
        'bodega-danger': 'var(--danger)',
        'bodega-warning': 'var(--warning)',
        'bodega-success': 'var(--success)',
      }
    }
  },
  plugins: []
}
```

```css
/* tailwind-shim.css */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

### Orden de importación

```js
// src/main.jsx
import './styles.css';        // CSS plano (legacy)
import './tailwind-shim.css'; // Tailwind (nuevo, gana specificity por orden)
```

### Componentes nuevos (Tailwind)

- `MultibodegaGrid`
- `BarcodeInput`
- `KpiCard`
- `SupervisorSelector`
- `SolicitudLineItem`
- `ApprovalTokenBanner`
- `SearchSku`

### Componentes legacy (CSS plano, NO TOCAR)

- `AppShell`
- `KpiStrip`, `StatCard`
- `TableSimple`
- `EmptyState`, `DrawerPanel`, `FilterBar`
- `FormField`, `FormGrid`
- `ToastViewport`, `GlobalPendingBar`
- `ActivityFeed`, `MiniBarChart`, `StatusBadge`
- `SectionCard`, `PageHeader`

## Consequences

### Positive

- **POS-001**: Cero riesgo de regresión en componentes legacy (no se tocan).
- **POS-002**: PRs pequeños y enfocados por vista nueva.
- **POS-003**: Las variables CSS del CSS plano se exponen como tokens de Tailwind (consistencia visual).
- **POS-004**: Permite migrar gradualmente en el futuro, vista por vista, sin deadline.
- **POS-005**: Build incremental: solo se compila Tailwind para clases usadas (PurgeCSS implícito).

### Negative

- **NEG-001**: El bundle final contendrá ambos sistemas CSS (~10KB extra).
- **NEG-002**: Inconsistencia visual temporal entre vistas nuevas (Tailwind) y viejas (CSS plano).
- **NEG-003**: Nuevos developers deben aprender ambos sistemas durante la transición.
- **NEG-004**: Tests visuales deben cubrir ambos sistemas.

## Alternatives Considered

### Big-bang migration

- **ALT-001**: **Description**: Reescribir todo el CSS a Tailwind en un sprint.
- **ALT-002**: **Rejection Reason**: Riesgo altísimo de regresión visual, requiere QA extensivo, no hay valor inmediato.

### Gradual por componente (no por vista)

- **ALT-003**: **Description**: Migrar componente por componente, ej. `EmptyState` primero.
- **ALT-004**: **Rejection Reason**: Mezcla CSS en la misma vista, debugging más complejo, peor UX para QA.

### Solo Tailwind sin CSS plano (retirar legacy)

- **ALT-005**: **Description**: Eliminar `styles.css` desde el día 1.
- **ALT-006**: **Rejection Reason**: Rompe 11 vistas en producción, sin red de seguridad.

## Implementation Notes

- **IMP-001**: `npm i -D tailwindcss@3 postcss autoprefixer` desde la raíz de `apps/web`.
- **IMP-002**: `npx tailwindcss init -p` crea `tailwind.config.js` y `postcss.config.js`.
- **IMP-003**: Crear `apps/web/src/tailwind-shim.css` con las 3 directivas `@tailwind`.
- **IMP-004**: Modificar `apps/web/src/main.jsx` para importar el shim después de `styles.css`.
- **IMP-005**: Las 8 vistas nuevas usan solo Tailwind desde el primer commit.
- **IMP-006**: Variables CSS legacy expuestas en `tailwind.config.js` `theme.extend.colors` con prefijo `bodega-` (ej. `bg-bodega-bg`).
- **IMP-007**: NO migrar vistas legacy en esta fase; documentar como trabajo futuro.
- **IMP-008**: Verificar que `npm run build` sigue compilando sin warnings de PurgeCSS.

## References

- **REF-001**: `docs/architecture/aterrizaje-requerimiento-multi-bodega-2026-07-14.md` §7.1, §10 (decisión 7)
- **REF-002**: `apps/web/src/styles.css` (legacy a preservar)
- **REF-003**: Tailwind CSS v3 docs — https://tailwindcss.com/docs/installation
