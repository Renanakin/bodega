# Manual de usuario completo

## Que es Bodegaje

Bodegaje es un sistema para controlar productos, stock y movimientos entre bodegas.

Su objetivo es ayudar a que una empresa pueda:

- saber cuanto stock tiene
- saber en que bodega esta cada producto
- registrar entradas y salidas
- mover productos entre bodegas
- dejar trazabilidad de cada accion
- revisar reportes y auditoria

Este manual esta escrito para personas con conocimientos basicos de computacion.

## Antes de empezar

Para usar el sistema necesitas:

- un usuario
- una contrasena
- acceso a internet o a la red donde este publicado el sistema

Si estas usando una demo o ambiente de prueba, tu empresa o equipo puede darte usuarios de ejemplo.

## Como entrar al sistema

1. Abre la direccion web del sistema.
2. Escribe tu usuario.
3. Escribe tu contrasena.
4. Presiona el boton `Entrar`.

Si tus datos son correctos, entraras al panel principal.

Si no puedes entrar:

- revisa que el usuario este bien escrito
- revisa mayusculas y minusculas en la contrasena
- intenta escribir otra vez sin espacios extra
- si el problema sigue, pide ayuda al responsable del sistema

## Que veras al entrar

Al iniciar sesion veras el menu principal y una pantalla inicial llamada `Dashboard`.

Desde ahi puedes ir a:

- Dashboard
- Bodegas
- Recepciones
- Inventario
- Productos
- Transferencias
- Reportes
- Configuracion

Segun tu perfil, algunas acciones pueden estar disponibles y otras no.

## Que significa cada perfil

El sistema puede trabajar con distintos perfiles.

### Administrador

Puede hacer tareas amplias de control, como:

- crear bodegas
- crear productos
- revisar auditoria
- aprobar y revisar operaciones

### Supervisor

Puede controlar la operacion diaria, por ejemplo:

- aprobar transferencias
- revisar stock
- registrar ciertos movimientos
- revisar reportes

### Operador de origen

Trabaja en la bodega desde donde sale el producto.

Normalmente puede:

- crear solicitudes de transferencia
- despachar transferencias aprobadas
- ver stock y movimientos

### Operador de destino

Trabaja en la bodega que recibe el producto.

Normalmente puede:

- recibir transferencias
- registrar recepciones parciales
- informar incidencias
- revisar trazabilidad

## Dashboard

El `Dashboard` es la pantalla de resumen.

Sirve para ver rapidamente:

- alertas criticas
- solicitudes pendientes
- transferencias recibidas
- cobertura general del escenario

Tambien muestra:

- indicadores rapidos
- actividad reciente
- productos con stock bajo minimo
- recorrido sugerido para una presentacion

### Para que sirve

Sirve para responder preguntas como:

- que problemas hay hoy
- que cosas estan pendientes
- que tan bien esta fluyendo la operacion

### Que debes mirar primero

1. Alertas criticas
2. Solicitudes pendientes
3. Actividad reciente
4. Productos bajo minimo

### Boton `Cargar demo`

En algunos ambientes existe un boton `Cargar demo`.

Sirve para cargar informacion de ejemplo para una revision o presentacion.

Si tu empresa usa datos reales, este boton puede no estar disponible o no usarse.

## Bodegas

La pantalla `Bodegas` muestra las bodegas registradas en el sistema.

Cada bodega puede tener:

- codigo
- nombre
- tipo
- estado

### Para que sirve

Sirve para saber donde opera la empresa y desde que lugares puede recibir o mover productos.

### Crear una bodega

Si tu perfil lo permite:

1. Entra a `Bodegas`.
2. Presiona `Nueva bodega`.
3. Completa:
   - codigo
   - nombre
   - tipo
4. Presiona `Guardar bodega`.

### Recomendaciones

- usa codigos cortos y faciles de reconocer
- evita crear bodegas duplicadas
- revisa bien el tipo antes de guardar

## Productos

La pantalla `Productos` muestra el catalogo de productos disponibles.

Cada producto tiene:

- SKU o codigo de producto
- nombre
- unidad
- estado

### Para que sirve

Sirve para mantener ordenado el catalogo y asegurar que todos trabajen con el mismo producto.

### Crear un producto

Si tu perfil lo permite:

1. Entra a `Productos`.
2. Presiona `Nuevo producto`.
3. Completa:
   - SKU
   - nombre
   - unidad
4. Presiona `Guardar producto`.

### Buenas practicas

- no uses dos productos para representar lo mismo
- escribe nombres faciles de entender
- manten un formato consistente para los SKU

## Recepciones

La pantalla `Recepciones` sirve para registrar entradas de productos.

Una recepcion aumenta el stock disponible de una bodega.

### Para que sirve

Sirve para registrar:

- compras recibidas
- cargas iniciales
- ingresos manuales autorizados

### Registrar una recepcion

1. Entra a `Recepciones`.
2. Presiona `Nueva carga`.
3. Selecciona:
   - bodega
   - producto
4. Ingresa:
   - cantidad
   - referencia
   - observacion si hace falta
5. Presiona `Registrar carga`.

### Resultado esperado

El producto quedara disponible en la bodega seleccionada.

### Errores comunes

- elegir la bodega equivocada
- escribir mal la cantidad
- olvidar la referencia

## Inventario

La pantalla `Inventario` muestra el stock actual por producto y por bodega.

Tambien permite revisar movimientos recientes.

### Para que sirve

Sirve para:

- revisar cuanto stock hay
- detectar productos bajo minimo
- confirmar disponibilidad antes de mover mercaderia

### Como filtrar el inventario

Puedes filtrar por:

- SKU o nombre del producto
- bodega
- estado

### Que significa cada estado

- `Disponible`: el producto esta en buen estado de stock
- `Bajo minimo`: el producto requiere atencion

### Registrar un ajuste

Si tu perfil lo permite:

1. Entra a `Inventario`.
2. Presiona `Nuevo ajuste`.
3. Selecciona bodega y producto.
4. Indica el motivo.
5. Escribe el ajuste en cantidad.
6. Agrega un comentario si corresponde.
7. Presiona `Registrar ajuste`.

### Cuando se usa un ajuste

Un ajuste se usa cuando hay diferencias entre lo esperado y lo encontrado, por ejemplo:

- conteo fisico
- merma
- error de carga previo

## Transferencias

La pantalla `Transferencias` sirve para mover productos entre bodegas.

Este proceso no ocurre en un solo paso. Tiene etapas para dar mas control.

### Etapas de una transferencia

1. Solicitada
2. Aprobada
3. Despachada
4. Recepcion parcial o recibida

### Crear una transferencia

1. Entra a `Transferencias`.
2. Presiona `Nueva transferencia`.
3. Selecciona:
   - bodega origen
   - bodega destino
   - producto
4. Ingresa:
   - cantidad
   - prioridad
   - observacion
5. Presiona `Crear solicitud`.

### Que pasa despues

La transferencia queda creada como solicitud.

Todavia no se considera cerrada ni recibida.

### Aprobar una transferencia

Si tu perfil lo permite:

1. Busca la transferencia.
2. Presiona `Aprobar`.

### Despachar una transferencia

Si tu perfil lo permite:

1. Busca una transferencia aprobada.
2. Presiona `Despachar`.
3. Agrega una observacion si hace falta.
4. Confirma el despacho.

Cuando una transferencia se despacha:

- el stock sale de la bodega origen
- queda en transito hacia la bodega destino

### Recibir una transferencia

Si tu perfil lo permite:

1. Busca una transferencia despachada.
2. Presiona `Recibir`.
3. Ingresa la cantidad recibida.
4. Agrega observacion si corresponde.
5. Si hubo problema, marca una incidencia.
6. Confirma la recepcion.

### Recepcion parcial

Una recepcion parcial se usa cuando llega solo una parte del producto.

Ejemplo:

- se enviaron 10 unidades
- llegaron 6
- faltan 4

En ese caso:

- el sistema registra las 6 recibidas
- la transferencia queda como `Recepcion parcial`
- luego se puede completar cuando llegue el resto

### Incidencias

Una incidencia es un problema ocurrido durante la recepcion.

Ejemplos:

- faltante
- dano
- problema documental

Registrar una incidencia ayuda a dejar evidencia de lo ocurrido.

### Editar una solicitud

Mientras una transferencia aun este como `Solicitada`, puede editarse si tu perfil lo permite.

Se puede cambiar:

- cantidad
- prioridad
- observacion

### Cancelar una solicitud

Mientras una transferencia aun no haya avanzado, puede cancelarse si tu perfil lo permite.

Se usa cuando:

- ya no se necesita el movimiento
- hubo un error en la solicitud
- se tomara otra decision

### Como leer la pantalla de transferencias

La pantalla muestra:

- estado actual
- cantidad solicitada
- cantidad recibida
- prioridad
- historial de hitos
- acciones disponibles

Tambien muestra incidencias recientes si existieron.

## Reportes

La pantalla `Reportes` sirve para consultar informacion y descargar archivos.

### Para que sirve

Sirve para:

- exportar inventario
- exportar transferencias abiertas
- exportar historial filtrado

### Exportar inventario

1. Entra a `Reportes`.
2. Presiona `Exportar inventario`.

### Exportar transferencias

1. Entra a `Reportes`.
2. Presiona `Exportar transferencias`.

### Filtrar historial

En la parte de historial puedes filtrar por:

- SKU
- bodega

Luego puedes exportar el resultado.

### Para que es util esto

Sirve para:

- enviar informacion a otra persona
- guardar respaldo
- revisar operaciones de una bodega o producto especifico

## Configuracion

La pantalla `Configuracion` sirve para revisar informacion general del sistema.

En esta etapa, lo mas importante para el usuario comun es la parte de auditoria.

## Auditoria

La auditoria registra acciones importantes del sistema.

### Para que sirve

Sirve para saber:

- que se hizo
- sobre que registro
- cuando se hizo

### Que acciones pueden verse

Por ejemplo:

- inicio de sesion
- creacion de producto
- creacion de bodega
- aprobacion de transferencia
- despacho
- recepcion

### Cuando conviene revisarla

Conviene revisarla cuando:

- hay dudas sobre una operacion
- se quiere confirmar una accion
- se necesita seguimiento

## Modo presentacion

El sistema tiene un `Modo presentacion`.

### Para que sirve

Sirve para mostrar el producto de forma guiada, con menos distracciones.

### Que cambia cuando esta activo

- el menu lateral se reduce
- aparece una guia de presentacion
- se priorizan las pantallas mas fuertes para una demo

### Como activarlo

Puedes activarlo desde:

- el Dashboard
- la parte superior del sistema

### Recorrido sugerido

1. Dashboard
2. Inventario
3. Transferencias
4. Reportes
5. Configuracion

## Busqueda y filtros

En varias pantallas encontraras filtros y cajas de busqueda.

### Para que sirven

Sirven para encontrar informacion mas rapido.

### Recomendaciones

- busca por SKU si quieres precision
- usa bodega si buscas operaciones de un lugar especifico
- usa estado si quieres ver solo pendientes o casos criticos

## Exportaciones

Algunas pantallas permiten descargar archivos CSV.

### Que es un CSV

Es un archivo que puede abrirse con:

- Excel
- Google Sheets
- otras planillas

### Cuando conviene usarlo

- para compartir informacion
- para armar reportes propios
- para revisar datos fuera del sistema

## Mensajes comunes del sistema

### "Sesion iniciada"

Significa que entraste correctamente.

### "No se pudo iniciar sesion"

Significa que el usuario o la contrasena no fueron aceptados, o hubo un problema de conexion.

### "No se pudo ejecutar la accion"

Significa que la accion no fue aceptada por alguna regla o por permisos.

### "Sin datos"

Significa que aun no hay informacion para esa vista o que el filtro no encontro resultados.

### "Sin incidencias registradas"

Significa que no hay problemas documentados en ese conjunto de transferencias.

## Errores comunes y como resolverlos

### No puedo entrar

Prueba:

- revisar usuario y contrasena
- recargar la pagina
- pedir validacion de acceso

### No puedo ver una accion

Puede deberse a tu perfil.

Ejemplo:

- algunos usuarios pueden solicitar
- otros pueden aprobar
- otros pueden recibir

### No puedo aprobar o despachar

Revisa:

- estado actual de la transferencia
- rol del usuario activo

### No puedo recibir todo

Puede ser porque:

- llego menos cantidad
- hay una incidencia

En ese caso usa `Recepcion parcial`.

### No encuentro un producto o movimiento

Prueba:

- quitar filtros
- buscar por SKU exacto
- revisar la bodega seleccionada

## Buenas practicas de uso

- registra las acciones apenas ocurren
- revisa bien bodega y producto antes de confirmar
- usa observaciones cuando algo no sea normal
- registra incidencias si hubo diferencia real
- revisa auditoria cuando necesites confirmar que paso
- exporta reportes cuando necesites compartir informacion

## Recomendaciones para trabajo diario

### Al comenzar el dia

- revisa el Dashboard
- mira alertas criticas
- revisa transferencias pendientes

### Durante la operacion

- registra recepciones al momento de recibir
- revisa inventario antes de mover productos
- completa cada etapa de transferencia en orden

### Al cerrar el dia

- revisa incidencias
- revisa transferencias parciales
- exporta reportes si hace falta

## Preguntas frecuentes

### El sistema descuenta stock cuando creo una transferencia?

No. La solicitud crea el pedido interno.

El descuento ocurre al despachar.

### El sistema aumenta stock en destino al aprobar?

No. El stock aumenta cuando se registra la recepcion.

### Puedo recibir una parte y despues el resto?

Si. Para eso existe la recepcion parcial.

### Puedo cancelar una transferencia?

Si, mientras siga en estado de solicitud y tu perfil lo permita.

### Puedo cambiar una solicitud ya creada?

Si, mientras aun no haya avanzado y tu perfil lo permita.

## Resumen rapido del flujo principal

1. Entrar al sistema
2. Revisar Dashboard
3. Crear o revisar bodegas
4. Crear o revisar productos
5. Registrar recepciones
6. Revisar inventario
7. Crear transferencia
8. Aprobar transferencia
9. Despachar transferencia
10. Recibir total o parcialmente
11. Revisar auditoria
12. Exportar reportes

## Cierre

Si usas este sistema siguiendo el orden correcto, podras:

- mantener el stock actualizado
- controlar movimientos entre bodegas
- registrar problemas reales
- dejar evidencia de cada accion
- compartir informacion con reportes exportables

Si algo no aparece o no puedes hacer una accion, lo primero que debes revisar es:

- tu perfil
- el estado actual del registro
- los filtros aplicados
