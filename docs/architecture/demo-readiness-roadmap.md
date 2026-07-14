# Roadmap tecnico de demo vendible

**Estado:** en ejecucion  
**Alcance actual:** Prioridad 1 iniciada e implementada parcialmente

## Objetivo

Convertir el MVP actual en una demo estable, persistente y reiniciable que permita pruebas funcionales de punta a punta sin depender de datos en memoria ni configuracion manual.

## Prioridad 1

### Persistencia real

- reemplazar almacenamiento en memoria por persistencia SQLite local sin dependencias extra
- mantener servicios y contratos HTTP para minimizar el impacto
- aplicar migraciones versionadas al iniciar la app

**Archivos clave**

- `apps/api/app/core/config.py`
- `apps/api/app/db/session.py`
- `apps/api/app/modules/*/repository.py`

### Migraciones y versionado

- conservar esquema postgres como referencia del dominio
- agregar migraciones SQLite ejecutables por la API local
- versionar el dominio de transferencias ya implementado

**Archivos clave**

- `db/migrations/0002_transfers_workflow.sql`
- `db/migrations/sqlite/0001_inventory_mvp.sql`
- `db/migrations/sqlite/0002_transfers_workflow.sql`
- `db/schema/initial-domain.sql`

### Seed reproducible

- crear una base demo reseteable
- incluir bodegas, productos, stock y transferencias en distintos estados
- permitir revisar dashboard, inventario y pipeline de transferencias inmediatamente

**Archivos clave**

- `apps/api/app/db/demo.py`
- `infra/scripts/reset-demo.ps1`

## Prioridad 2

- login simple
- roles `admin`, `supervisor`, `origen`, `destino`
- restricciones por accion operativa

## Prioridad 3

- dashboard orientado a venta
- datos demo visibles al primer uso
- feedback, estados vacios y busqueda transversal

## Criterio de cierre de Prioridad 1

- la API persiste datos al reiniciar
- el flujo `bodegas -> productos -> carga -> transferencia` sobrevive reinicios
- existe comando simple para recrear la demo
- las pruebas backend pasan con la nueva persistencia
- el frontend sigue compilando sin romper el flujo actual
