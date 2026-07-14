# Workflows con agentes del proyecto

## Objetivo

Dejar un flujo simple para usar agentes especializados sobre el producto sin improvisar cada vez.

## Agentes

### `review-guardian`

Usar cuando:

- se quiera auditar el producto antes de mostrarlo
- se necesiten hallazgos de riesgo con prioridad

Salida esperada:

- hallazgos
- impacto
- riesgo de demo
- checklist de correccion

### `ux-redesign-lead`

Usar cuando:

- una pantalla no explica bien valor
- hay demasiada carga cognitiva
- se necesita reforzar narrativa comercial

Salida esperada:

- propuesta de rediseño
- nueva jerarquia visual
- mejores microcopys

### `step-tutorial-author`

Usar cuando:

- se quiera crear onboarding
- se necesite documentar flujos por rol
- se prepare material para piloto o capacitacion

Salida esperada:

- tutorial paso a paso
- checklist de ejecucion
- guion usable por comercial o implementador

## Flujo recomendado

1. correr `review-guardian`
2. aplicar o decidir cambios
3. correr `ux-redesign-lead`
4. estabilizar pantallas
5. correr `step-tutorial-author`
6. usar la salida en demo, onboarding o capacitacion

## Nota

Estos agentes no reemplazan validacion funcional. Complementan implementacion, demo y adopcion.
