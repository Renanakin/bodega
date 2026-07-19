# Manual de Usuario — Sistema Multi-Bodega

> **Bienvenido al sistema de inventario multi-bodega.**
> Este manual cubre el uso operativo diario para cada rol.

## Indice

1. [Primeros pasos](#1-primeros-pasos)
2. [Roles y permisos](#2-roles-y-permisos)
3. [Operador Auxiliar](#3-operador-auxiliar)
4. [Operador Destino](#4-operador-destino)
5. [Bodeguero Central](#5-bodeguero-central)
6. [Supervisor](#6-supervisor)
7. [Administrador](#7-administrador)
8. [Flujos completos](#8-flujos-completos)
9. [Preguntas frecuentes](#9-preguntas-frecuentes)

---

## 1. Primeros pasos

### 1.1 Acceder al sistema

1. Abre el navegador y ve a `https://app.bodega.example` (o `http://localhost` en dev).
2. Ingresa tu **usuario** y **contraseña**.
3. Click en **Entrar**.

![Login](images/login.png)

### 1.2 Cambiar tu contraseña

(Proximamente en el modulo de perfil de usuario.)

### 1.3 Navegacion principal

La aplicacion tiene 3 areas principales:
- **Sidebar izquierdo**: menu de modulos.
- **Header superior**: busqueda global + acciones.
- **Contenido central**: vistas operativas.

---

## 2. Roles y permisos

El sistema tiene 4 roles:

| Rol | Que puede hacer |
|---|---|
| **admin** | Todo. Configuracion, usuarios, bodegas, productos, etc. |
| **supervisor** | Aprobar/rechazar solicitudes de recarga, aprobar OC externas, ver reportes. |
| **origin_operator** (operador origen) | Crear solicitudes de recarga desde bodegas auxiliares, despachar (cuando auxiliar es origen), cancelar. |
| **destination_operator** (operador destino) | Recibir transferencias, registrar ingresos. |

> **Nota**: en una organizacion pequena, un mismo usuario puede tener varios roles.

---

## 3. Operador Auxiliar (Bodega Auxiliar)

> **Perfil tipico**: bodeguero de un taller. Maneja el stock del taller y pide reposicion a Central.

### 3.1 Ver mis bodegas

1. En el sidebar, click en **Bodegas**.
2. Veras la lista de bodegas donde tienes rol de operador origen.
3. Click en una bodega para ver su stock.

### 3.2 Ver el stock de mi bodega

1. En el sidebar, click en **Inventario**.
2. Filtra por tu bodega.
3. Veras una tabla con: SKU, Producto, Disponible, Minimo, Maximo, Estado.

**Codigo de colores:**
- 🟢 **Verde** (normal): stock entre minimo y maximo.
- 🟡 **Amarillo** (alerta): stock <= minimo.
- 🔴 **Rojo** (critico): stock = 0 o negativo.

### 3.3 Crear una solicitud de recarga

Cuando tu stock esta bajo minimo, puedes pedir reposicion a Central.

1. En el sidebar, click en **Solicitudes**.
2. Click en **Nueva Solicitud**.
3. Completa el formulario:
   - **Bodega origen**: tu bodega (autoseleccionada).
   - **Bodega destino**: Central.
   - **Productos**: agrega uno o mas con cantidad solicitada.
4. Click en **Enviar Solicitud**.

> **Tip**: el sistema calcula automaticamente la cantidad sugerida (maximo - actual) para cada producto bajo minimo.

### 3.4 Aprobar / cancelar una solicitud

1. Ve a **Solicitudes** > filtra por **Pendientes**.
2. Click en una solicitud para ver el detalle.
3. Si tienes rol supervisor, click en **Aprobar**.
4. Si la solicitud no fue aprobada, puedes **Cancelar** (solo PENDING).

### 3.5 Despachar una solicitud aprobada

Una vez que el supervisor aprueba tu solicitud:

1. Ve a **Solicitudes** > filtra por **Aprobadas**.
2. Click en **Despachar**.
3. El sistema descuenta automaticamente el stock de tu bodega (lock pesimista para evitar oversell).
4. El estado pasa a **En transito**.

---

## 4. Operador Destino (Bodega Principal o Auxiliar)

> **Perfil tipico**: bodeguero de la bodega central o auxiliar que recibe transferencias.

### 4.1 Bandeja de recepcion

1. En el sidebar, click en **Bandeja Recepcion**.
2. Veras todas las solicitudes **En transito** con destino a una bodega donde tienes rol.
3. Para cada solicitud, veras una tabla con los productos despachados.

### 4.2 Recibir con escaneo de codigo de barras

1. Click en una solicitud para abrir el detalle.
2. Por cada linea:
   - **Escanea** el codigo de barras con tu lector.
   - El sistema lo validara automaticamente.
   - Si el codigo no coincide con el SKU, veras una alerta amarilla (no bloqueante, solo log).
3. Click en **Confirmar Recepcion** para registrar toda la recepcion.

**Recepcion parcial:**
- Si no recibes todo, puedes hacer **multiples recepciones parciales**.
- El sistema mantiene el estado `partially_received` hasta que se complete.
- Solo se valida que la cantidad acumulada no exceda la cantidad despachada.

### 4.3 Recibir sin escanner (manual)

Si no tienes lector, puedes:
1. Dejar el campo barcode vacio.
2. Click en **Confirmar Recepcion** directamente.
3. El sistema registra sin validacion de codigo.

---

## 5. Bodeguero Central

> **Perfil tipico**: bodeguero de la bodega central. Despacha transferencias a auxiliares y gestiona ordenes de compra externas.

### 5.1 Consolidador central

El consolidador agrega todas las solicitudes pendientes de las auxiliares para tomar decisiones:

1. En el sidebar, click en **Consolidador**.
2. Veras una **vista agregada por producto** con la cantidad total pedida por todas las auxiliares.
3. Marca los productos que NO se pueden cubrir con stock interno (quiebres).
4. Click en **Agregar a OC** para cada producto que ira a una orden de compra.
5. Selecciona un supervisor y un proveedor.
6. Click en **Crear OC y enviar a supervisor**.

### 5.2 Despachar desde Central a Auxiliares

Igual que el operador auxiliar pero en sentido inverso:

1. Ve a **Solicitudes** > filtra por **Aprobadas**.
2. Click en **Despachar** (necesitas rol origin_operator).

### 5.3 Gestion de ordenes de compra

1. En el sidebar, click en **Ordenes Compra**.
2. Veras la lista de OC en distintos estados.
3. Para una OC en **Borrador**: click en **Enviar a supervisor**.
4. El sistema genera un token de aprobacion, lo encola en el email outbox, y actualiza el estado a **Enviado a supervisor**.
5. El supervisor recibe el email con un enlace; al hacer click, aprueba o rechaza (sin login).

### 5.4 Ver la cola de emails

1. En el sidebar, click en **Notificaciones** (solo admin/supervisor).
2. Veras todos los emails pendientes, enviados y fallidos.
3. Los emails fallidos pueden re-enviarse manualmente.

---

## 6. Supervisor

> **Perfil tipico**: jefe de turno o jefe de bodega. Autoriza solicitudes de recarga y ordenes de compra.

### 6.1 Aprobar solicitudes de recarga

Recibes notificaciones (toast) cuando hay solicitudes pendientes. Tambien puedes:

1. Ve a **Solicitudes** > filtra por **Pendientes**.
2. Revisa los detalles (origen, destino, productos, cantidades).
3. Click en **Aprobar** o **Rechazar** (con motivo).

### 6.2 Aprobar ordenes de compra via email

1. Recibes un email con el formato:
   ```
   Asunto: Aprobacion requerida: OC-0042
   
   Estimado [Tu nombre],
   
   Se requiere tu aprobacion para la siguiente orden de compra:
   ...
   
   [Aprobar OC]  [Rechazar]
   ```
2. Click en el boton.
3. Se abre una pagina publica (no requiere login).
4. Click en **Aprobar** o **Rechazar** con motivo.
5. El sistema registra la decision y notifica al bodeguero central.

> **Importante**: el enlace expira en **7 dias**. Pasado ese tiempo, el bodeguero debe reenviar la OC.

### 6.3 Ver reportes y metricas

1. En el sidebar, click en **Reportes** (proximamente).
2. Aqui encontraras:
   - Stock valorizado
   - Quiebres por periodo
   - Rotacion ABC
   - Tiempos de aprobacion

---

## 7. Administrador

> **Perfil tipico**: administrador del sistema. Configura bodegas, productos, usuarios, supervisores, proveedores.

### 7.1 Gestion de bodegas

1. Ve a **Bodegas** en el sidebar.
2. Click en **Nueva bodega**.
3. Completa:
   - **Codigo**: identificador unico (ej. `AUX-NORTE`).
   - **Nombre**: nombre legible.
   - **Tipo**: Principal / Auxiliar / Box de mecanico.
   - **Bodega padre** (solo para boxes): la auxiliar a la que pertenece.
4. Click en **Guardar**.

### 7.2 Gestion de productos

1. Ve a **Productos** en el sidebar.
2. Click en **Nuevo producto**.
3. Completa:
   - **SKU**: codigo unico.
   - **Nombre**: nombre legible.
   - **Unidad**: unidad, kg, m, etc.
   - **Categoria** (opcional).
   - **Precios**: costo y venta.
   - **Codigo de barras** (opcional): EAN-13, Code 128, etc.
4. Si es un neumatico, completa el detalle con ancho, perfil, aro, indices.

### 7.3 Gestion de usuarios

(Proximamente en el modulo de administracion de usuarios.)

### 7.4 Gestion de supervisores

1. Ve a **Supervisores** en el sidebar.
2. Click en **Nuevo supervisor**.
3. Completa: nombre, email (unico), telefono, cargo.
4. Los supervisores desactivados no aparecen en dropdowns pero conservan historial.

### 7.5 Gestion de proveedores

(Proximamente. Por ahora los proveedores se gestionan directamente en la OC.)

---

## 8. Flujos completos

### 8.1 Flujo: Reposicion de stock (Taller -> Central)

```
1. Operador auxiliar ve stock bajo minimo en su bodega.
2. Va a Solicitudes > Nueva Solicitud.
3. Agrega los productos y cantidades. Sistema sugiere (max - actual).
4. Envia solicitud.
   -> Solicitud queda PENDING.

5. Supervisor recibe notificacion. Va a Solicitudes > Pendientes.
6. Aprueba la solicitud.
   -> Solicitud pasa a APPROVED.

7. Operador auxiliar (con rol origin_operator) ve su solicitud aprobada.
8. Va a Solicitudes > Aprobadas > Despachar.
   -> Sistema descuenta stock de la bodega auxiliar.
   -> Solicitud pasa a IN_TRANSIT.

9. Operador destino ve la solicitud en Bandeja Recepcion.
10. Escanea codigos de barras (opcional) y confirma.
    -> Sistema suma stock a la bodega destino.
    -> Si todo: RECEIVED. Si parcial: PARTIALLY_RECEIVED.
```

### 8.2 Flujo: Orden de Compra externa

```
1. Bodeguero central identifica quiebres que no puede cubrir.
2. Va a Consolidador > agrega productos a OC.
3. Selecciona supervisor y proveedor.
4. Crea OC.
   -> OC queda en BORRADOR.

5. Bodeguero central va a Ordenes Compra > selecciona OC.
6. Click "Enviar a supervisor".
   -> Sistema genera token de aprobacion (7 dias).
   -> Sistema encola email al supervisor.
   -> OC pasa a ENVIADO_A_SUPERVISOR.

7. Supervisor recibe email, click en enlace.
8. Aprueba o rechaza.
   -> Si aprueba: APROBADO. Si rechaza: RECHAZADO (con motivo).

9. Bodeguero central contacta al proveedor y compra.
10. Cuando recibe la mercaderia, registra ingreso (Carga en Bandeja Recepcion).
```

---

## 9. Preguntas frecuentes

### P: Que pasa si el codigo de barras no coincide?
R: El sistema loguea la advertencia pero **no bloquea** la recepcion. El bodeguero puede confirmar manualmente.

### P: Puedo cancelar una solicitud ya aprobada?
R: No. Las solicitudes aprobadas o en transito no se pueden cancelar. Si necesitas revertir, crea una solicitud de retorno.

### P: Como cambio mi bodega?
R: Las bodegas son configuradas por el administrador. Contacta al admin para reasignacion.

### P: Donde veo metricas del sistema?
R: El dashboard principal muestra KPIs. Para metricas tecnicas detalladas (latencia, errores, etc.) visita `/metrics` (solo accesible para infraestructura).

### P: Como reporto un bug?
R: Contacta al administrador del sistema o crea un ticket en el sistema de soporte de tu organizacion.

### P: Puedo usar el sistema desde el celular?
R: La interfaz web es responsive y funciona en tablets. En celulares pequenos algunas tablas pueden requerir scroll horizontal.

### P: Que pasa si pierdo conexion a internet?
R: El sistema no funciona offline. Cualquier operacion no enviada se pierde. Recomendamos hacer la operacion cuando vuelva la conexion.

### P: Como auditar quien hizo que?
R: Las acciones criticas (crear OC, aprobar solicitud, etc.) se registran en `audit_logs`. Proximamente habra un modulo de auditoria visible.

---

## Soporte

- **Email**: soporte@bodega.example
- **Telefono**: +56 2 2345 6789
- **Horario**: Lun-Vie 9:00-18:00 (Chile continental)

---

**Version del manual**: 1.0
**Ultima actualizacion**: 2026-07-14
**Sistema**: v0.1.0
