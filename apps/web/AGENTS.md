# AGENTS

## Folder

`apps/web`

## Objetivo

Construir el frontend operacional del sistema multi-bodega.

## Skills del area

- interfaces para operadores y supervisores
- dashboards de inventario
- formularios de movimientos
- tablas y filtros operativos
- integracion con APIs y tiempo real

## Skills prioritarias para los siguientes pasos

- construir formularios reales de recepcion, ajuste, transferencia y reposicion
- agregar validacion visual de campos y estados de error
- implementar estados globales de UI: loading, empty, error y success
- conectar vistas a endpoints reales sin acoplar reglas de negocio
- incorporar feedback operacional: toasts, banners y confirmaciones
- preparar componentes reutilizables para tablas, filtros, modales y drawer panels
- asegurar experiencia responsive en desktop y tablet
- preparar base para WebSockets y actualizacion en tiempo real

## Secuencia sugerida

1. formularios operativos
2. estado global de interfaz
3. integracion con API
4. feedback y notificaciones
5. tiempo real

## Agente ideal

- frontend engineer
- UI engineer
- especialista en experiencia operacional

## Plugins recomendados

- ESLint
- Prettier
- JavaScript and TypeScript
- Tailwind CSS IntelliSense

## Reglas

- priorizar claridad operacional sobre complejidad visual
- las pantallas criticas deben ser rapidas y legibles en desktop
- no acoplar reglas de negocio al frontend
- los formularios deben poder usarse en contexto de bodega con pocos clics
- toda vista nueva debe contemplar loading, empty y error state
- no introducir dependencias pesadas sin justificar su necesidad
