# Manual de Usuario — Bodegaje v1.0.0

> **Para:** operador nuevo, supervisor o admin que va a usar el sistema por primera vez.
> **Lee esto de arriba a abajo la primera vez**, despues usa el indice para saltar al modulo que necesites.

---

## Tabla de contenidos

1. [Conceptos basicos](#1-conceptos-basicos)
2. [Acceso y roles](#2-acceso-y-roles)
3. [Mapa mental de modulos](#3-mapa-mental-de-modulos)
4. [Modulo 1: Dashboard](#4-modulo-1-dashboard)
5. [Modulo 2: Bodegas](#5-modulo-2-bodegas)
6. [Modulo 3: Productos y Categorias](#6-modulo-3-productos-y-categorias)
7. [Modulo 4: Inventario y movimientos](#7-modulo-4-inventario-y-movimientos)
8. [Modulo 5: Recepciones](#8-modulo-5-recepciones)
9. [Modulo 6: Solicitudes de recarga](#9-modulo-6-solicitudes-de-recarga)
10. [Modulo 7: Consolidador central](#10-modulo-7-consolidador-central)
11. [Modulo 8: Reposicion automatica](#11-modulo-8-reposicion-automatica)
12. [Modulo 9: Multibodega](#12-modulo-9-multibodega)
13. [Modulo 10: Ordenes de compra](#13-modulo-10-ordenes-de-compra)
14. [Modulo 11: Reportes](#14-modulo-11-reportes)
15. [Modulo 12: Notificaciones y chat](#15-modulo-12-notificaciones-y-chat)
16. [Modulo 13: Supervisores y usuarios](#16-modulo-13-supervisores-y-usuarios)
17. [Modulo 14: Configuracion y slotting](#17-modulo-14-configuracion-y-slotting)
18. [Modulo 15: Auditoria y trazabilidad](#18-modulo-15-auditoria-y-trazabilidad)
19. [Flujos completos paso a paso](#19-flujos-completos-paso-a-paso)
20. [Documentos que genera el sistema](#20-documentos-que-genera-el-sistema)
21. [Glosario](#21-glosario)
22. [Que hacer si algo falla](#22-que-hacer-si-algo-falla)

---

## 1. Conceptos basicos

### 1.1 Que es Bodegaje

Bodegaje es un sistema operativo para controlar **multiples bodegas** en tiempo real. Centraliza stock, movimientos, recepciones, solicitudes entre bodegas, reposicion automatica, ordenes de compra a proveedores, y reporteria.

El caso de uso principal es: una **bodega principal** que distribuye stock a varias **bodegas auxiliares** (sucursales, puntos de despacho, talleres), con reposicion automatica cuando el stock cae bajo minimo.

### 1.2 Arquitectura minima

- **UI web** (http://localhost:8080): SPA React + Vite, todo en una sola pagina con rutas.
- **API REST** (http://localhost:8080/api/v1): FastAPI + Postgres 17 + SQLAlchemy async.
- **Worker Arq**: corre la cola de emails + el cron de reposicion automatica cada 5 minutos.
- **Redis**: rate limit, cola de emails, cache.
- **Mailpit** (http://localhost:8025): bandeja para ver emails enviados en dev/staging.
- **Observabilidad**: Prometheus, Grafana, Alertmanager, exporters.

### 1.3 Estados que vas a ver repetidos

| Estado | Significa |
|---|---|
| `pending` | Solicitud creada, esperando aprobacion |
| `approved` | Aprobada, lista para despachar |
| `in_transit` | Despachada, en camino |
| `partially_received` | Recibida parcialmente (algunas lineas, otras no) |
| `received` | Recepcion completa |
| `rejected` | Rechazada con motivo (no se puede revertir) |
| `cancelled` | Cancelada (solo estando en `pending`) |

---

## 2. Acceso y roles

### 2.1 URL de acceso

http://localhost:8080

### 2.2 Usuarios precargados

| Usuario | Password | Rol | Para que sirve |
|---|---|---|---|
| `admin` | `admin12345` | `admin` | Acceso total, gestion de usuarios, configuracion |
| `supervisor` | `admin12345` | `supervisor` | Aprobar/rechazar solicitudes, supervisar operaciones |
| `origen` | `admin12345` | `origin_operator` | Operador de bodega origen: despachar solicitudes |
| `destino` | `admin12345` | `destination_operator` | Operador de bodega destino: recibir solicitudes |

> **Cambiar el password** la primera vez que entres: Configuracion -> Mi cuenta (si esta disponible) o pedirle al admin que lo resetee.

### 2.3 Que puede hacer cada rol

| Accion | admin | supervisor | origin | destination |
|---|:---:|:---:|:---:|:---:|
| Ver Dashboard | ✅ | ✅ | ✅ | ✅ |
| Crear/editar bodegas | ✅ | ❌ | ❌ | ❌ |
| Crear/editar productos | ✅ | ✅ | ❌ | ❌ |
| Crear movimientos de inventario manuales | ✅ | ✅ | ✅ | ❌ |
| Crear recepciones | ✅ | ✅ | ❌ | ✅ |
| Crear solicitudes de recarga | ✅ | ✅ | ✅ | ❌ |
| Aprobar/rechazar solicitudes | ✅ | ✅ | ❌ | ❌ |
| Despachar solicitudes | ✅ | ✅ | ✅ | ❌ |
| Recibir solicitudes | ✅ | ✅ | ❌ | ✅ |
| Generar reposicion automatica | ✅ | ✅ | ❌ | ❌ |
| Crear ordenes de compra | ✅ | ✅ | ❌ | ❌ |
| Aprobar ordenes de compra | ✅ | ✅ | ❌ | ❌ |
| Ver reportes | ✅ | ✅ | ❌ | ❌ |
| Gestionar supervisores/usuarios | ✅ | ❌ | ❌ | ❌ |
| Configuracion del sistema | ✅ | ❌ | ❌ | ❌ |

> Si ves "403 Forbidden" o "Acceso denegado", es tu rol.

### 2.4 Sesion y token

- Al hacer login recibes un **access_token** (1 hora) y un **refresh_token** (7 dias).
- El sistema **renueva el access_token automaticamente** cuando expira — no tienes que volver a loguearte cada hora.
- Si el refresh_token expira (7 dias sin entrar), tienes que volver a loguearte.

---

## 3. Mapa mental de modulos

```
                    ┌─────────────────────┐
                    │     Dashboard       │ ← vista ejecutiva, KPIs
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
   ┌────▼─────┐         ┌──────▼──────┐        ┌──────▼──────┐
   │ Bodegas  │◄────────┤ Productos   ├───────►│ Categorias  │
   └────┬─────┘         └──────┬──────┘        └─────────────┘
        │                      │
        │  tiene stock de      │  tiene stock en
        ▼                      ▼
   ┌────────────┐         ┌──────────────┐
   │ Inventario │◄────────┤  Movimientos │  (aumentan/disminuyen stock)
   └────┬───────┘         └──────────────┘
        │
        │  llega mercaderia
        ▼
   ┌────────────┐         ┌────────────────┐
   │Recepciones │────────►│ Ordenes Compra │  (a proveedores externos)
   └────┬───────┘         └────────┬───────┘
        │                          │
        │  genera o completa       │  se aprueba con link publico firmado
        ▼                          ▼
   ┌────────────────┐         ┌────────────────┐
   │  Solicitudes   │         │  Proveedores   │
   │ (entre bodegas)│         └────────────────┘
   └────┬───────────┘
        │
        ├────► Aprobar ───► Despachar ───► Recibir
        │      (supervisor) (origen)       (destino)
        │
        └──► Reposicion automatica (cron cada 5 min)
             detecta stock bajo minimo y crea solicitudes
```

---

## 4. Modulo 1: Dashboard

**Ruta:** `/dashboard`
**Roles:** todos
**Para que sirve:** ver el estado general de la operacion de un vistazo.

### Que muestra

El Dashboard tiene tres zonas:

**Bloque superior (Centro de control):**
- Ambiente actual (Local / Pre-produccion / Produccion)
- Buscador global (productos, solicitudes, bodegas)
- Botones rapidos: Productos, Exportar inventario, Nuevo movimiento (lleva a `/inventory` con drawer abierto)
- Modo presentacion (oculta menus para capturas de demo)

**KPIs principales (4 tarjetas grandes):**
- **Alertas criticas**: productos que exigen reposicion o traslado
- **Solicitudes pendientes**: transferencias que requieren aprobacion
- **Transferencias recibidas**: cierres completos que actualizaron stock destino
- **Cobertura demo**: indicador de que bodegas, productos, stock y auditoria estan visibles

**KPIs secundarios (4 tarjetas chicas):**
- **Bodegas visibles**: cantidad de bodegas activas en el sistema
- **Productos activos**: SKUs no desactivados
- **OTIF demo**: % On Time In Full (placeholder, valor demo)
- **Despachos en transito**: solicitudes en estado `in_transit`

**Bloque inferior (modo presentacion):**
- **Mensaje comercial**: guion de demo para presentar el sistema a un cliente en 2 minutos
- **Recorrido sugerido**: guia corta paso a paso para la demo

### Como usarlo

1. Entra a la URL, te redirige a `/dashboard` despues del login.
2. Si "Alertas criticas" es > 0, ya sabes por donde empezar: ve a Reposicion (modulo 8).
3. Si "Solicitudes pendientes" es > 0, tienes trabajo de aprobacion (modulo 6).
4. Para presentar a un cliente: click "Activar presentacion" (esconde menus y muestra el guion).

---

## 5. Modulo 2: Bodegas

**Ruta:** `/warehouses`
**Roles:** solo `admin`
**Para que sirve:** dar de alta, editar y dar de baja las bodegas del sistema.

### 5.1 Tipos de bodega

| Tipo | Codigo | parent_warehouse_id | Reglas |
|---|---|---|---|
| `principal` | BOD-PPAL-XXX | NULL | Bodega madre. Solo ENTREGA stock, no recibe. Es la unica que puede ser destino de solicitudes internas. |
| `auxiliar` | BOD-AUX-XXX | NULL | Recibe stock de la principal y lo reparte. Es la unica que dispara reposicion automatica. |
| `mecanico_box` | BOX-XXX | requerido (auxiliar) | Punto de despacho chico, depende de un auxiliar padre. NO dispara reposicion automatica. |

### 5.2 Crear una bodega

1. Click en **"+ Nueva bodega"**.
2. Completa:
   - **Codigo** (unico, sin espacios, ej: `BOD-AUX-NORTE`)
   - **Nombre** (visible para el usuario, ej: "Bodega Auxiliar Norte")
   - **Tipo** (principal/auxiliar/mecanico_box)
   - **Bodega padre** (solo si tipo=mecanico_box, seleccionar la auxiliar padre)
   - **Activa** (si la desactivas, no aparece en selectores)
3. Click en **Crear**.

### 5.3 Editar / desactivar

- Click en la fila de la bodega -> se abre el drawer de edicion.
- Cambiar `Activa` a `false` es la forma "blanda" de dar de baja: la bodega sigue existiendo pero no aparece en los selectores nuevos. **No borra su stock historico.**

### 5.4 Restricciones

- Solo puede haber **una bodega `principal` activa** a la vez. Si intentas crear otra, el sistema lo rechaza.
- Si una bodega es `principal` o `auxiliar`, NO puede tener `parent_warehouse_id`. Si es `mecanico_box`, es OBLIGATORIO.
- Bodegas inactivas no cuentan para el replenishment automatico.

---

## 6. Modulo 3: Productos y Categorias

**Ruta:** `/products` (Productos), `/categorias` (Categorias)
**Roles:** admin y supervisor (crear/editar), todos (ver)

### 6.1 Productos

**Campos del producto:**

| Campo | Obligatorio | Ejemplo |
|---|---|---|
| `sku` | si | `PROD-001` |
| `name` | si | `Tornillo 1/4 pulgada` |
| `unit` | no | `unidad`, `kg`, `litro`, `caja` |
| `categoria` | no | UUID de la categoria |
| `codigo_barras` | no | EAN-13, se usa en recepciones |
| `precio_costo` | no | Decimal, para valorizacion |
| `precio_venta` | no | Decimal |
| `is_active` | si | Si esta en false, no aparece en selectores pero sigue en BD |

**Como crear un producto:**

1. `/products` -> **"+ Nuevo producto"**.
2. Completa los campos. SKU debe ser unico.
3. Crear.

**Como asignar categoria:**

1. En la lista de productos, click en la fila.
2. Selecciona categoria del dropdown. Guardar.

### 6.2 Categorias

Jerarquia simple (1 nivel). Ejemplos: "Repuestos", "Insumos", "Herramientas".

1. `/categorias` -> **"+ Nueva categoria"**.
2. Nombre. Guardar.
3. Para asignar productos, ve a Productos y editalos.

---

## 7. Modulo 4: Inventario y movimientos

**Ruta:** `/inventory`
**Roles:** admin, supervisor, origin_operator (para crear movimientos manuales)

### 7.1 Que muestra

- **Header**: "INVENTARIO - Stock por bodega y disponibilidad operativa".
- **Botones arriba a la derecha**: "Importar conteo" (carga masiva desde archivo) y "Nuevo ajuste" (movimiento manual).
- **Filtros**: barra de busqueda por SKU o producto + selectores de bodega y estado.
- **Tabla "Resumen de stock"** con columnas: SKU, Producto, Bodega, Stock Actual, Minimo, Estado.
- El estado se muestra con badge: "Disponible" (verde) o "Bajo minimo" (ambar).

### 7.2 Tipos de movimiento

| Tipo | Signo | Cuando se usa |
|---|---|---|
| `entry` (entrada) | + | Llega mercaderia, devolucion, ajuste al alza |
| `exit` (salida) | - | Merma, venta, consumo interno |
| `adjustment` | +/- | Correccion de inventario, conteo fisico |

### 7.3 Crear un movimiento manual

1. Click en **"Nuevo ajuste"** (boton en la pagina de Inventario) **o** en **"Nuevo movimiento"** (boton verde del topbar).
2. Completa:
   - **Bodega** (selector buscable, ordenado por tipo)
   - **Producto** (selector buscable por SKU o nombre)
   - **Tipo** (entry/exit/adjustment)
   - **Cantidad** (positiva para sumar, negativa para restar — el hint te lo recuerda)
   - **Notas** (motivo del movimiento, importante para auditoria)
3. Crear. El stock se actualiza inmediatamente.

### 7.4 Cuando usar cada uno

- **Entrada**: recibiste mercaderia sin orden de compra (no deberia pasar si usas Recepciones).
- **Salida**: vendiste/perdiste producto sin pasar por solicitud (tambien raro, mejor usar Solicitudes).
- **Ajuste**: conteo fisico encontro diferencia con el sistema. SIEMPRE documentar el motivo en notas.

### 7.5 Exportar a CSV

Boton **"Exportar"** del topbar -> descarga `inventario-YYYY-MM-DD.csv` con columnas: bodega, SKU, producto, stock, minimo. Util para inventarios fisicos en Excel.

---

## 8. Modulo 5: Recepciones

**Ruta:** `/receipts` y `/recepciones`
**Roles:** admin, supervisor, destination_operator

### 8.1 Que hace

Registra la entrada de mercaderia de un proveedor. Crea automaticamente movimientos de tipo `entry` en la bodega destino.

### 8.2 Crear una recepcion

1. `/receipts` -> **"+ Nueva recepcion"**.
2. Completa:
   - **Bodega destino** (donde llega la mercaderia)
   - **Proveedor** (selector, o "+ Nuevo" si no esta)
   - **Numero de documento** (numero de factura/guia del proveedor)
   - **Lineas**: una por cada producto:
     - SKU (buscable, o escanear codigo de barras con el campo de barra)
     - Cantidad recibida
     - Precio unitario (para valorizacion)
3. Crear.

### 8.3 Que pasa despues

- Se crea la recepcion en estado `pending`.
- **NO** se actualiza el stock todavia. La bodega destino debe confirmar la recepcion (boton "Confirmar" en la lista).
- Al confirmar, se generan movimientos `entry` automaticamente en la bodega destino.

### 8.4 Bandeja de recepciones

**Ruta:** `/recepcion/bandeja`

Lista todas las recepciones pendientes de confirmar. Filtros por bodega, proveedor, fecha.

---

## 9. Modulo 6: Solicitudes de recarga

**Ruta:** `/solicitudes`
**Roles:** todos pueden ver; admin/supervisor/origen pueden crear

### 9.1 Que es una solicitud

Es un documento interno que **mueve stock de una bodega a otra** dentro del sistema. NO es contra un proveedor externo (eso es una Orden de Compra).

- **Origen**: bodega que ENTREGA stock (siempre auxiliar o box)
- **Destino**: bodega que RECIBE stock (siempre la principal)
- **Lineas**: lista de (producto, cantidad_solicitada)
- **Estados**: pending -> approved -> in_transit -> (partially_received | received)

### 9.2 Crear una solicitud manual

1. `/solicitudes` -> **"+ Nueva solicitud"**.
2. Completa:
   - **Bodega origen** (selector — solo muestra bodegas que pueden entregar)
   - **Bodega destino** (fija en la principal)
   - **Prioridad** (normal/alta)
   - **Lineas**: una por producto (SKU + cantidad)
   - **Notas** (opcional)
3. Crear. Se genera un codigo tipo `SOL-YYYYMMDD-NNNN`.

### 9.3 Ciclo de vida

```
   CREADA              APROBADA             DESPACHADA            RECIBIDA
   pending  ──────►   approved  ──────►   in_transit  ──────►   received
      │                   │                    │
      │ cancelar          │ rechazar           │ recibir parcial
      ▼                   ▼                    ▼
   cancelled          rejected         partially_received
   (solo desde        (cualquier       (estado final posible
    pending)           estado)          desde in_transit)
```

### 9.4 Quien hace que cosa

| Accion | Quien la hace | Cuando |
|---|---|---|
| Crear | admin, supervisor, origin | Cuando el operador sabe que necesita reponer |
| Aprobar | admin, supervisor | Cuando se valida que la solicitud tiene sentido |
| Rechazar | admin, supervisor | Si la solicitud es incorrecta o innecesaria |
| Cancelar | admin, supervisor, origin | Solo si esta en `pending` |
| Despachar | admin, supervisor, origin | Cuando el operador de la bodega origen prepara el pedido |
| Recibir | admin, supervisor, destination | Cuando llega la mercaderia a la bodega destino |

### 9.5 Despachar una solicitud

1. En la lista de solicitudes, click en la fila -> se abre el detalle.
2. Si esta en `approved`, aparece el boton **"Despachar"**.
3. Click -> modal de despacho:
   - Por cada linea, ingresa la **cantidad despachada** (puede ser menor a la solicitada, eso seria despacho parcial).
   - Opcional: escanea el codigo de barras del producto (si lo definiste) para validar.
4. Confirmar. La solicitud pasa a `in_transit` y **se descuenta stock del origen**.

### 9.6 Recibir una solicitud

1. En la lista, click en la fila en estado `in_transit`.
2. Boton **"Recibir"**.
3. Por cada linea, ingresa la **cantidad recibida**.
4. Si recibes todo -> pasa a `received`. Si recibes menos -> pasa a `partially_received`.
5. Al recibir, **se suma stock al destino**.

### 9.7 Reporte agregado (Consolidador)

**Ruta:** `/consolidador` (modulo aparte, ver seccion 10).

---

## 10. Modulo 7: Consolidador central

**Ruta:** `/consolidador`
**Roles:** admin, supervisor

### 10.1 Que hace

Es el **panel tactico de la bodega principal**. Permite ver de un vistazo:

- Todas las solicitudes activas agrupadas por producto.
- Cuanto pidio cada auxiliar, cuanto se aprobo, cuanto esta en transito, cuanto se recibio.
- Diferencias entre solicitado y recibido (quiebres).
- Exportable a CSV.

### 10.2 Como se usa

1. `/consolidador` -> vista por defecto: solicitudes en estado `pending/approved/in_transit` (todas las activas).
2. Filtros: por estado, por bodega origen, por fecha.
3. La tabla agrupa por SKU y muestra el total agregado.
4. Click en una fila para ir al detalle de la solicitud.

### 10.3 Para que sirve

- Antes de **despachar un grupo de solicitudes**, ver el consolidado para preparar el picking.
- Despues de una corrida de reposicion, validar que se generaron las solicitudes correctas.
- Para detectar SKUs con muchos pedidos parciales (problema de supply chain).

---

## 11. Modulo 8: Reposicion automatica

**Ruta:** `/replenishment` o `/reposicion` (en el menu lateral: "Reposicion")
**Roles:** admin, supervisor (para disparar), todos (para ver)

### 11.1 Que hace

Cada **5 minutos**, un cron (worker Arq) corre el **ReplenishmentEvaluator** que:

1. Revisa todas las bodegas **auxiliares activas**.
2. Detecta SKUs con `stock_actual <= stock_minimo`.
3. Por cada (bodega, producto) bajo minimo, crea una solicitud automatica a la principal con la cantidad sugerida.
4. Si ya hay una solicitud activa (pending/approved/in_transit/partially_received) para ese (bodega, producto), NO crea otra (idempotencia).

### 11.2 Cantidad sugerida

- Si el producto tiene `stock_maximo` definido: `sugerida = maximo - actual`
- Si no: `sugerida = (minimo * 2) - actual`
- Si el resultado es <= 0, se omite.

### 11.3 Prioridad automatica

- **alta**: `stock_actual < minimo * 0.5` (critico)
- **normal**: en caso contrario

### 11.4 Que muestra la UI

- **Lista de SKUs bajo minimo** que aun no tienen solicitud activa.
- **Boton "Previsualizar (dry run)"**: corre el Evaluator SIN crear solicitudes, solo muestra el reporte.
- **Boton "Generar solicitudes"**: dispara el Evaluator manualmente.
- **Boton por fila "Generar solicitud"**: para una sola bodega.

### 11.5 Empty states

- **Si no hay bajo minimo y no hay solicitudes activas**: "Todas las bodegas tienen stock sobre el minimo".
- **Si no hay bajo minimo pero hay solicitudes activas**: muestra el bloque **"SKUs bajo minimo cubiertos por solicitudes activas"** con la lista y links a cada solicitud. Asi entiendes por que no aparecen como alertas.

### 11.6 Ultima corrida

Arriba se muestra cuando fue la ultima corrida, cuantos SKUs bajo minimo se detectaron, cuantas solicitudes se crearon, cuantas se omitieron (ya cubiertas).

---

## 12. Modulo 9: Multibodega

**Ruta:** `/multibodega`
**Roles:** todos (lectura)

### 12.1 Que es

Una **consulta bajo demanda** de distribucion de un SKU especifico:

- En el campo de busqueda, ingresa un SKU (ej: `PROD-NORMAL-44E53D`).
- La grilla resultado muestra: para ESE producto, cuanto stock hay en CADA bodega.
- Colores por celda: verde (sobre minimo), amarillo (cerca del minimo), rojo (bajo minimo).
- NO es una vista general: hay que buscar SKU por SKU.

### 12.2 Para que sirve

- Ver donde esta concentrado el stock de un producto especifico antes de tomar decisiones de redistribucion.
- Detectar bodegas con sobrestock y bodegas con deficit del mismo SKU (candidato a transferir).
- Caso de uso tipico: "tengo que mover 50 unidades de PROD-X de BOD-PPAL a BOD-AUX-SUR, hay?" → lo consultas aqui.

### 12.3 Como buscar

1. `/multibodega` -> campo de busqueda "SKU".
2. Escribe o pega el SKU (autocomplete te ayuda).
3. Enter o click en buscar.
4. La grilla aparece abajo.

---

## 13. Modulo 10: Ordenes de compra

**Ruta:** `/ordenes-compra`
**Roles:** admin, supervisor (crear y aprobar)

### 13.1 Que es

Una orden de compra (OC) es un documento para **comprar mercaderia a un proveedor externo**. NO es lo mismo que una solicitud (que es interna entre bodegas).

### 13.2 Crear una OC

1. `/ordenes-compra` -> **"+ Nueva orden"**.
2. Completa:
   - **Proveedor** (selector)
   - **Bodega destino** (donde llegara la mercaderia)
   - **Lineas**: SKU + cantidad + precio unitario esperado
3. Crear. Se genera codigo tipo `OC-YYYYMMDD-NNNN`.

### 13.3 Aprobacion publica

A diferencia de las solicitudes internas, las OC se aprueban **por link publico firmado**:

1. Al crear la OC (en estado `pending`), el sistema genera un **approval_token**.
2. El supervisor (o quien designe el admin) recibe un email con el link.
3. El link es: `https://<host>/ordenes-compra/aprobacion/<token>`.
4. Quien hace click puede:
   - **Aprobar**: la OC pasa a `approved`, se envia email al proveedor.
   - **Rechazar**: con motivo, la OC pasa a `rejected`.
5. El token expira en 7 dias.

### 13.4 Recepcion de una OC

Cuando la mercaderia llega, va a **Recepciones** (modulo 5) con la OC como referencia. Al confirmar la recepcion, se crea el movimiento `entry` en la bodega destino.

### 13.5 Bandeja de aprobacion publica

**Ruta:** `/ordenes-compra/aprobacion/<token>`

Acceso sin login, pero requiere el token firmado. Si el token expira o es invalido, muestra error.

---

## 14. Modulo 11: Reportes

**Ruta:** `/reports`
**Roles:** admin, supervisor

### 14.1 Que hay

- **Reporte ejecutivo**: KPIs consolidados (valorizacion, rotacion, quiebres).
- **Reporte de inventario**: stock por bodega, con totales.
- **Reporte de transferencias**: solicitudes filtradas por estado/fecha.
- **Reporte de historial**: auditoria de movimientos.

### 14.2 Exportar

Todos los reportes se pueden exportar a CSV desde la UI (boton "Exportar" en cada vista).

### 14.3 Reportes automaticos

El sistema no envia reportes automaticos por email. Si lo necesitas, configura un cron externo que llame a los endpoints y envie el email.

---

## 15. Modulo 12: Notificaciones y chat

### 15.1 Notificaciones

**Ruta:** icono de campana en el topbar.
**Roles:** todos

- El sistema envia notificaciones automaticas por:
  - Solicitud creada (a aprobadores)
  - Solicitud aprobada (a origen)
  - Solicitud rechazada (a quien la creo)
  - Solicitud despachada (a destino)
  - Solicitud recibida (a quien la creo)
  - Stock bajo minimo (a admin/supervisor)
- Cada notificacion tiene: titulo, mensaje, link a la entidad, timestamp.
- Click en la campana -> dropdown con las ultimas 10.
- "Marcar como leida" quita el contador rojo.

### 15.2 Chat (interno)

**Ruta:** `/chat`
**Roles:** todos

- Chat simple entre usuarios del sistema.
- NO es un chat con clientes ni proveedores. Es para coordinacion interna ("oye, ya despache la SOL-001", etc.).
- Los mensajes persisten en BD y se pueden buscar.

---

## 16. Modulo 13: Supervisores y usuarios

**Ruta:** `/supervisores`
**Roles:** solo `admin`

### 16.1 Gestion de usuarios

1. `/supervisores` -> lista de todos los usuarios.
2. **"+ Nuevo usuario"**:
   - username (unico)
   - password (la app lo hashea con PBKDF2, no se guarda en plano)
   - full_name
   - role (admin/supervisor/origin_operator/destination_operator)
   - is_active
3. Crear.

### 16.2 Soft delete

- "Eliminar" usuario -> lo marca como `is_active=false`. NO se borra de la BD (preserva trazabilidad).
- El usuario ya no puede loguearse pero su historial de acciones sigue visible.

### 16.3 Resetear password

- Click en el usuario -> "Resetear password" -> genera uno nuevo temporal que el admin debe comunicarle.

---

## 17. Modulo 14: Configuracion y slotting

**Ruta:** `/settings`, `/slotting`
**Roles:** solo `admin`

### 17.1 Configuracion general

- **Nombre de la organizacion**
- **IVA / impuestos**
- **Politica de reposicion** (umbrales de prioridad, ventana de no-reposicion)
- **SMTP** (en staging usa Mailpit, en prod hay que configurar SES/SendGrid)

### 17.2 Slotting

**Ruta:** `/slotting`

- Ubicaciones fisicas dentro de cada bodega (`pasillo-estanteria-nivel`).
- Asignacion de productos a ubicaciones para picking rapido.
- No es obligatorio: si no lo usas, el sistema funciona igual.

---

## 18. Modulo 15: Auditoria y trazabilidad

**Ruta:** menu lateral (si esta habilitado para el rol)
**Roles:** admin, supervisor

### 18.1 Que registra

Cada accion del sistema genera un evento de auditoria con:

- `timestamp`
- `user_id` (quien lo hizo)
- `action` (login, create, update, delete, approve, etc.)
- `entity_type` (solicitud, producto, bodega, etc.)
- `entity_id` (UUID)
- `ip_address`
- `metadata` (cambios especificos)

### 18.2 Como consultarla

- Filtros por usuario, fecha, tipo de accion, entidad.
- Exportable a CSV.

### 18.3 Para que sirve

- Debugging: "quien cambio este stock a 0?"
- Compliance: demostrar trazabilidad en auditorias externas.
- Post-mortem: "que paso entre las 14:00 y las 15:00 cuando todo se rompio?"

---

## 19. Flujos completos paso a paso

### 19.1 Flujo: "Recibir mercaderia de un proveedor"

```
ADMIN/SUPERVISOR/DEST_OPERATOR                          API                       BD
  │
  ├── 1. /receipts -> "+ Nueva recepcion"
  │      (proveedor, bodega destino, lineas)
  │                                                          │
  │   POST /api/v1/receipts ────────────────────────────────►  crea receipt(pending)
  │                                                          │   NO toca stock aun
  │
  ├── 2. /recepcion/bandeja -> click "Confirmar" ────────►  POST /receipts/{id}/confirm
  │                                                          │   crea movimientos entry
  │                                                          │   stock += cantidad
  │                                                          ▼
  │                                                  bd: stock_levels actualizado
  │
  └── 3. Verificacion: /inventory -> la bodega muestra el stock nuevo
```

### 19.2 Flujo: "Mover stock entre bodegas (solicitud interna)"

```
ORIGEN              SUPERVISOR          API                       BD
  │
  ├── 1. /solicitudes -> "+ Nueva solicitud"
  │   (bodega_origen=aux, destino=principal, lineas)
  │      │
  │   POST /solicitudes ────────────────────────────────────►  crea solicitud(pending)
  │
  ├── 2. (automatico o por UI) ◄───────────────────────────  notif al supervisor
  │
  │              ├── 3. Click en notif o ir a /solicitudes/{id}
  │              │   Boton "Aprobar" ────► POST /solicitudes/{id}/approve
  │              │                          │
  │              │                          ▼
  │              │                     solicitud(approved)
  │              │                     notif al origen
  │
  ├── 4. /solicitudes/{id} -> "Despachar"
  │   (cantidades despachadas, opcional barcode)
  │      │
  │   POST /solicitudes/{id}/dispatch ─────────────────────►  descuenta stock origen
  │                                                          solicitud(in_transit)
  │                                                          notif al destino
  │
  │              (DEST_OPERATOR)
  ├── 5. /solicitudes/{id} -> "Recibir"
  │   (cantidades recibidas)
  │      │
  │   POST /solicitudes/{id}/receive ──────────────────────►  suma stock destino
  │                                                          solicitud(received|partial)
  │
  └── 6. Consolidador: /consolidador muestra el cierre
```

### 19.3 Flujo: "Reposicion automatica detecta bajo minimo"

```
CRON (cada 5 min)         API                              BD
  │
  ├── 1. evaluate_all()
  │   │
  │   for bodega_aux in auxiliares_activas:
  │     for (bodega, producto) con stock <= min:
  │       if (bodega, producto) NOT in solicitudes_activas:
  │         cantidad = max - actual (o min*2 - actual)
  │         prioridad = "alta" si actual < min*0.5 sino "normal"
  │         crear solicitud(origen=bodega, destino=principal)
  │
  ├── 2. UI: /replenishment muestra la lista de alertas
  │
  └── 3. UI: /solicitudes muestra la nueva solicitud
```

### 19.4 Flujo: "Comprar mercaderia a proveedor"

```
ADMIN/SUPERVISOR                API                       BD                  EMAIL
  │
  ├── 1. /ordenes-compra -> "+ Nueva orden"
  │   (proveedor, bodega destino, lineas)
  │      │
  │   POST /ordenes-compra ────────────────────────────────►  OC(pending)
  │                                                          │   genera approval_token
  │                                                          ▼
  │                                                  notif a aprobadores (con link)
  │
  ├── 2. Aprobador hace click en el link
  │   GET /ordenes-compra/aprobacion/{token}
  │      │
  │      "Aprobar" ────► POST .../aprobacion/{token} ──────►  OC(approved)
  │                                                          │   envia email al proveedor
  │                                                          │
  │                                                          ▼
  │                                                  proveedor recibe email
  │                                                  con la OC adjunta
  │
  ├── 3. Llega la mercaderia
  │   /receipts -> "+ Nueva recepcion" (con link a la OC)
  │      │
  │   POST /receipts ────────────────────────────────────────►  receipt(pending)
  │
  ├── 4. /recepcion/bandeja -> "Confirmar" ───────────────►  POST /receipts/{id}/confirm
  │                                                          │   crea entry en bodega destino
  │                                                          │   OC(received)
  │                                                          ▼
  │                                                  bd: stock += cantidad
  │                                                  OC marcada como cumplida
  │
  └── 5. /reports -> ver OC cerrada
```

### 19.5 Flujo: "Auditoria post-incidente"

```
ADMIN/SUPERVISOR               API                       BD
  │
  ├── 1. /auditoria (o /audit)
  │   Filtros: usuario=X, fecha=2026-07-23, accion=update_stock
  │      │
  │   GET /audit?... ────────────────────────────────────────►  query log_auditoria
  │                                                          │
  │                                                          ▼
  │                                                  retorna eventos con metadata
  │
  ├── 2. Click en evento -> ver el antes/despues
  │      │
  │      ej: "stock_actual: 100 -> 0"
  │          "usuario: origen (origin_operator)"
  │          "ip: 192.168.1.50"
  │          "timestamp: 2026-07-23 14:32:11"
  │
  └── 3. Si fue un error humano: corregir con un movimiento de ajuste
       /inventory -> "+ Nuevo movimiento" -> adjustment con notas
```

---

## 20. Documentos que genera el sistema

### 20.1 Documentos internos (visibles en la UI)

| Documento | Como se genera | Como se ve | Como se exporta |
|---|---|---|---|
| **Recepcion** (interna) | `/receipts` -> "+ Nueva" | Lista en `/receipts` con codigo REC-YYYYMMDD-NNNN | UI detalle, no CSV nativo |
| **Solicitud de recarga** | Manual o auto (cron) | Lista en `/solicitudes` con codigo SOL-YYYYMMDD-NNNN | UI detalle, link publico no |
| **Orden de compra** | `/ordenes-compra` -> "+ Nueva" | Lista en `/ordenes-compra` con codigo OC-YYYYMMDD-NNNN | UI detalle, email al proveedor |
| **Aprobacion publica OC** | Link firmado con token | `/ordenes-compra/aprobacion/{token}` | Email al aprobador con link |
| **Notificacion** | Auto por eventos | Dropdown campana + `/notifications` | UI |

### 20.2 Exportaciones CSV (boton "Exportar" en UI)

| Documento | Donde se genera | Contenido | Frecuencia tipica |
|---|---|---|---|
| **inventario-YYYY-MM-DD.csv** | Topbar -> "Exportar" | bodega, sku, producto, stock, minimo | Diaria, para inventario fisico |
| **Consolidador (CSV)** | `/consolidador` | solicitudes activas agrupadas | Semanal, para reunion |
| **Reporte de transferencias (CSV)** | `/reports` -> transferencias | solicitudes con filtros | Bajo demanda |
| **Reporte de inventario (CSV)** | `/reports` -> inventario | stock por bodega | Bajo demanda |
| **Auditoria (CSV)** | `/auditoria` | eventos con metadata | Bajo demanda |

### 20.3 Documentos externos (enviados por email)

| Documento | Cuando se envia | Destinatario | Contenido |
|---|---|---|---|
| **Email: solicitud creada** | Al crear solicitud | Supervisores | Asunto, link a la solicitud |
| **Email: solicitud aprobada** | Al aprobar | Operador origen | Link para despachar |
| **Email: solicitud rechazada** | Al rechazar | Quien la creo | Motivo del rechazo |
| **Email: solicitud despachada** | Al despachar | Operador destino | Link para recibir |
| **Email: solicitud recibida** | Al recibir (total) | Quien la creo | Confirmacion de cierre |
| **Email: bajo minimo** | Cada vez que se crea solicitud auto | Admin/supervisor | Resumen de la corrida |
| **Email: aprobacion OC** | Al crear OC | Aprobador designado | Link firmado publico |
| **Email: OC aprobada** | Al aprobar OC | Proveedor | Datos de la OC + plazo |
| **Email: OC rechazada** | Al rechazar OC | Quien la creo | Motivo del rechazo |

> En dev/staging, los emails NO se envian: van a **Mailpit** (http://localhost:8025).
> En prod, hay que configurar SMTP real (ver `.env` -> `SMTP_HOST`).

### 20.4 Reportes de respaldo automatico

- **Backup de Postgres**: `/backups/bodegaje-YYYYMMDDTHHMMSSZ.dump.gz`
  - Generado por el servicio `bodegaje-backup` diariamente a las 03:00 UTC.
  - Retencion: 7 dias (configurable con `BACKUP_RETENTION_DAYS`).
  - Volumen Docker `postgres_backups` (no se borra con `docker compose down`).
  - Ver `infra/docker/backup/README.md` para restaurar.

### 20.5 Logs estructurados

- **API**: stdout del contenedor `bodegaje-api` (accesible con `docker logs`).
- **Worker**: stdout del contenedor `bodegaje-worker`.
- **Nginx**: stdout del contenedor `bodegaje-nginx`.
- Cada log line es JSON con `timestamp`, `level`, `event`, `correlation_id`, `user_id`, `path`, `elapsed_ms`, etc.
- En Grafana/Loki se pueden hacer queries estructuradas (ver `docs/propuesta_ejecutables/`).

---

## 21. Glosario

| Termino | Significado |
|---|---|
| **Auxiliar** | Tipo de bodega que recibe stock de la principal y lo reparte |
| **Bodega principal** | Unica bodega que entrega stock a las auxiliares (origen de reposicion) |
| **Box / mecanico_box** | Punto de despacho chico, depende de una auxiliar padre |
| **Categoria** | Agrupacion logica de productos (jerarquia de 1 nivel) |
| **Codigo de barras** | EAN-13 del producto, opcional, permite escaneo en recepciones/despachos |
| **Consolidador** | Vista agregada de solicitudes activas para la bodega principal |
| **Cron** | Tarea programada que corre periodicamente (en este sistema: reposicion cada 5 min, backup diario) |
| **Detalle (de solicitud)** | Linea individual de una solicitud: (producto, cantidad_solicitada) |
| **Dry run** | Ejecucion que calcula pero NO persiste cambios (util para preview) |
| **Evaluador (Replenishment)** | Logica que detecta bajo minimo y crea solicitudes automaticas |
| **Idempotencia** | Propiedad de que ejecutar 2 veces no causa duplicados |
| **LPN / Linea** | Sinonimo de "detalle" en una solicitud |
| **mecanico_box** | Ver "Box" arriba |
| **Min_quantity** | Stock minimo: si actual <= min, se dispara alerta |
| **Max_quantity** | Stock objetivo: la cantidad sugerida es `max - actual` |
| **OC** | Orden de Compra (a proveedor externo) |
| **Operador destino** | Rol: usuario de bodega destino (recibe mercaderia) |
| **Operador origen** | Rol: usuario de bodega origen (despacha mercaderia) |
| **parent_warehouse_id** | FK de un box a su auxiliar padre |
| **Principal** | Ver "Bodega principal" |
| **Producto** | SKU individual (puede estar en muchas bodegas con stock distinto) |
| **Receipt / Recepcion** | Registro de mercaderia entrante de un proveedor |
| **Refresh token** | Token de larga duracion (7d) que sirve para renovar el access_token |
| **Replenishment** | Sinonimo de "Reposicion automatica" |
| **Reposicion automatica** | Proceso que detecta bajo minimo y crea solicitudes sin intervencion humana |
| **Solicitud** | Documento interno que mueve stock entre bodegas |
| **Stock actual** | Cantidad fisica disponible ahora mismo |
| **Stock minimo** | Umbral de alerta |
| **Stock maximo** | Cantidad objetivo al reponer |
| **Transfer (legacy)** | Sinonimo antiguo de "Solicitud" (sigue funcionando pero deprecated) |
| **Unidad** | Unidad de medida del producto (unidad, kg, litro, caja, etc.) |
| **warehouse_type** | Tipo de bodega: principal / auxiliar / mecanico_box |

---

## 22. Que hacer si algo falla

### 22.1 Tabla de sintomas rapidos

| Sintoma | Que hacer |
|---|---|
| "401 Unauthorized" en todo | Tu sesion expiro. Click en "Cerrar sesion" y volver a entrar. |
| "403 Forbidden" en una accion | Tu rol no tiene permiso. Pedirle a un admin. |
| "429 Too Many Requests" en login | Rate limit: esperar 1 minuto o pedirle al admin que limpie Redis. |
| "500 Internal Server Error" | Ver `docker logs --tail 100 bodegaje-api` y reportar. |
| Replenishment no genera solicitudes | Hay solicitudes activas (pending/approved/in_transit) que ya cubren esos SKUs. Ver `/replenishment` -> bloque "cubiertos por solicitudes activas". |
| UI no carga | `docker restart bodegaje-web bodegaje-nginx`. |
| Emails no salen | `docker ps \| Select-String "mailpit\|worker"`. En staging van a Mailpit (8025). |
| Stock no se actualiza al despachar | Verificar que la solicitud esta en `approved` y no `pending`. |
| Stock no se actualiza al recibir | Verificar que la solicitud esta en `in_transit`. |
| "La bodega principal no se puede eliminar" | Es correcto. El sistema la protege. |
| Backup no se genera | `docker logs --tail 50 bodegaje-backup`. Verificar que `db` esta healthy. |
| "Cannot connect to Docker daemon" | Docker Desktop no esta corriendo. Iniciarlo. |

### 22.2 Cuando TODO falla

1. Ver estado de la pila: `docker ps --format "table {{.Names}}\t{{.Status}}"`
2. Ver logs del servicio afectado: `docker logs --tail 100 bodegaje-<servicio>`
3. Si la BD no responde y hay backup reciente (<25h): restaurar (ver seccion 22.3).
4. Si no hay backup: `docker compose -f infra/docker/docker-compose.yml down -v` y llorar.

### 22.3 Restaurar un backup de la BD

Ver el procedimiento completo en `infra/docker/backup/README.md` y `docs/cheatsheet.md` seccion 7.

TL;DR:
```powershell
# 1. Bajar API y worker
docker compose -f G:\PROYECTOS\bodega\infra\docker\docker-compose.yml stop api worker

# 2. Copiar backup al host
docker cp bodegaje-backup:/backups/bodegaje-latest.dump.gz C:\Users\Tranquilidad\restore.dump.gz

# 3. Restaurar
gunzip -c C:\Users\Tranquilidad\restore.dump.gz | docker exec -i bodegaje-db pg_restore -U bodegaje -d bodegaje --clean --if-exists --no-owner --no-privileges

# 4. Levantar
docker compose -f G:\PROYECTOS\bodega\infra\docker\docker-compose.yml start api worker
```

### 22.4 Contactos utiles

- **Repositorio**: https://github.com/Renanakin/bodega
- **Documentacion tecnica**: `docs/propuesta_ejecutables/`
- **Cheatsheet rapido**: `docs/cheatsheet.md`
- **Auditorias de cambios**: `C:\Users\Tranquilidad\auditoria-fase0\` y `auditoria-fase5\` (gitignored)

---

## Apendice A: Atajos de teclado

| Tecla | Accion |
|---|---|
| `Ctrl+K` (o click en el topbar) | Buscar productos / solicitudes / bodegas |
| `Esc` | Cerrar drawer / modal / dropdown |
| `Enter` en formularios | Submit |
| `Tab` | Siguiente campo |
| `/` | Focus en el buscador (en algunas vistas) |

## Apendice B: Permisos granulares

Si tu rol no aparece en la tabla de seccion 2.3 con check ✅, NO podras hacer esa accion. El backend rechaza con 403 y la UI muestra "Acceso denegado" en rojo.

## Apendice C: Versionado

- **v1.0.0** (actual): estable, con todos los modulos basicos + seguridad C5 (refresh tokens, rate limit).
- Tags previos (`v1.0.0-rc1` a `rc4`): pre-produccion, no usar.
- Para volver a una version anterior: `git checkout v1.0.0 && docker compose up -d --build`.

---

**Ultima actualizacion:** 2026-07-23
**Version del sistema:** v1.0.0
**Autor del manual:** generado para operador unipersona.
