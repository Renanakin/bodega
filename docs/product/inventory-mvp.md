# MVP de inventario API/DB

**Fecha:** 17-03-2026  
**Estado:** implementacion en progreso

## Objetivo

Definir el primer entregable funcional del backend y de la base de datos del sistema multi-bodega sin introducir logica improvisada ni reglas de stock repartidas en las rutas HTTP.

## Estado actual

Actualmente el proyecto tiene:

- un backend FastAPI funcional con:
  - alta, listado y consulta de bodegas
  - alta, listado y consulta de productos
  - consulta de stock
  - registro y listado de movimientos
  - resumen de inventario
- servicios de dominio y repositorios separados por modulo
- persistencia temporal en memoria dentro de la API
- un esquema SQL del MVP con migracion versionada y seed local

### Pendiente actual

La API todavia no esta conectada a una base de datos persistente; el siguiente paso tecnico es reemplazar los repositorios en memoria por repositorios respaldados por la BD real.

## Alcance del MVP aprobado

### Incluye

- alta y listado de bodegas
- alta y listado de productos
- consulta de stock actual por producto y bodega
- registro de movimientos de inventario
- historial de movimientos
- resumen simple de inventario para validacion operativa

### Queda para una fase futura

- transferencias entre bodegas
- reposicion automatica o semiautomatica
- compras
- autenticacion y permisos
- reportes avanzados
- chat y notificaciones

## Reglas de negocio

1. El stock solo cambia a traves del modulo de inventario.
2. Ninguna ruta HTTP debe modificar stock directamente.
3. Toda salida debe validar saldo suficiente antes de confirmar el movimiento.
4. Cada movimiento debe dejar trazabilidad auditable.
5. Los codigos de bodega y los SKU de producto deben ser unicos.
6. Las cantidades deben ser positivas; el signo del movimiento lo define su tipo.

## Tipos de movimiento del MVP

- `in`
- `out`
- `adjustment_in`
- `adjustment_out`

## Flujos funcionales del MVP

### 1. Gestion de bodegas

Permite crear y listar bodegas operativas del sistema.

### 2. Gestion de productos

Permite crear y listar el catalogo base de productos inventariables.

### 3. Consulta de stock

Permite revisar el saldo actual por combinacion de bodega y producto.

### 4. Registro de movimientos

Permite registrar entradas, salidas y ajustes con referencia y observaciones.

### 5. Historial auditable

Permite revisar la secuencia de movimientos por bodega, producto y tipo.

## Criterios de aceptacion

El MVP se considera listo cuando se cumpla lo siguiente:

- la API permite crear y listar bodegas
- la API permite crear y listar productos
- la API permite registrar movimientos validando reglas de dominio
- el stock se actualiza a partir de los movimientos
- una salida con stock insuficiente es rechazada
- existe esquema versionado alineado al flujo de inventario
- existe cobertura de pruebas sobre las reglas criticas
