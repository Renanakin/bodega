# AGENTS

## Folder

`infra`

## Objetivo

Mantener la infraestructura local y de despliegue del sistema.

## Skills del area

- Docker
- composicion de servicios
- configuracion de proxy
- observabilidad
- despliegue por ambientes

## Skills prioritarias para los siguientes pasos

- preparar perfil de produccion separado de local y staging
- endurecer Nginx con headers, limites y proxy consistente
- definir variables de entorno por ambiente
- agregar healthchecks y politicas de reinicio
- documentar flujo de despliegue y rollback
- preparar base para monitoreo y logs centralizados
- dejar checklist operativa para salida a produccion

## Secuencia sugerida

1. cerrar perfil production
2. validar proxy y exposicion de puertos
3. definir secretos y variables por ambiente
4. preparar monitoreo y logs
5. documentar despliegue y rollback

## Agente ideal

- DevOps engineer
- platform engineer
- release engineer

## Plugins recomendados

- Docker
- YAML
- EditorConfig

## Reglas

- separar local, staging y produccion con claridad
- no hardcodear secretos
- documentar puertos, variables y dependencias
- no exponer puertos internos en staging o produccion sin necesidad
- cualquier cambio de red o proxy debe quedar documentado
- la infraestructura debe favorecer rollback simple y diagnostico rapido
