# Documentacion

Este directorio concentra la documentacion funcional, tecnica y operativa del sistema multi-bodega.

## Indice

- `product/`
  - `README.md`: mapa de documentacion funcional
  - `inventory-mvp.md`: alcance y reglas del primer MVP de API/DB
- `architecture/`
  - `README.md`: mapa de documentacion tecnica
  - `backend-modules.md`: modulos del backend por estado
  - `api-db-inventory-mvp.md`: diseno tecnico aprobado para API y base de datos
- `operations/`
  - `README.md`: mapa operativo
  - `workspace-usage.md`: uso del workspace multi-raiz
  - `api-db-validation-checklist.md`: checklist de validacion local para API y DB
  - `api-db-handoff-2026-03-18.md`: estado realizado, faltante y punto de reentrada para otra sesion

## Estado documental al 18-03-2026

- **API / backend**: existe un MVP funcional con rutas para bodegas, productos, stock, movimientos y resumen, implementado sobre persistencia en memoria para mantener limpio el dominio antes de conectar la base de datos.
- **Base de datos**: existe un modelo SQL alineado al MVP en `db/schema/initial-domain.sql`, una migracion versionada `db/migrations/0001_inventory_mvp.sql` y una semilla minima en `db/seeds/0001_inventory_mvp_seed.sql`.
- **Pendiente principal**: conectar la API a persistencia real reutilizando la separacion ya creada entre routers, servicios y repositorios.
- **Fuera de este ciclo**: `apps/web` e `infra`.
