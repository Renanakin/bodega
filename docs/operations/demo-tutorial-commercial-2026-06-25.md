# Step Tutorial Author - Tutorial comercial guiado

## Objetivo

Guiar una presentacion comercial de 5 a 7 minutos mostrando valor, control operativo y trazabilidad.

## Perfil sugerido

- iniciar como `admin`
- cambiar luego a `origen` o `destino` si quieres demostrar permisos

## Paso 1. Iniciar sesion

- **Que ve el usuario:** pantalla de acceso demo con perfiles precargados.
- **Que debe hacer:** ingresar con `admin / demo123`.
- **Por que importa:** demuestra acceso controlado y perfiles listos para prueba.
- **Error comun:** intentar acceder a una ruta sin autenticacion.
- **Resultado esperado:** ingreso al dashboard.

## Paso 2. Leer el dashboard

- **Que ve el usuario:** alertas criticas, pendientes, cobertura demo y recorrido sugerido.
- **Que debe hacer:** explicar primero quiebres y backlog.
- **Por que importa:** instala el problema de negocio antes de mostrar botones.
- **Error comun:** empezar por crear registros.
- **Resultado esperado:** el cliente entiende que el sistema muestra riesgo y prioridad.

## Paso 3. Revisar inventario

- **Que ve el usuario:** stock por bodega, minimo, estado y movimientos recientes.
- **Que debe hacer:** filtrar por SKU o bodega.
- **Por que importa:** demuestra visibilidad operacional real.
- **Error comun:** no mostrar la relacion entre stock y alertas.
- **Resultado esperado:** el cliente entiende que existe control consolidado.

## Paso 4. Crear una transferencia

- **Que ve el usuario:** formulario de solicitud con origen, destino, producto y cantidad.
- **Que debe hacer:** crear una solicitud interna.
- **Por que importa:** muestra que el movimiento se formaliza antes de ejecutar stock.
- **Error comun:** olvidar mencionar que aun no descuenta stock.
- **Resultado esperado:** transferencia en estado `Solicitada`.

## Paso 5. Aprobar y despachar

- **Que ve el usuario:** acciones disponibles segun rol.
- **Que debe hacer:** aprobar y luego despachar.
- **Por que importa:** evidencia control por etapas y permisos.
- **Error comun:** ejecutar todo como si fuera una sola accion.
- **Resultado esperado:** transferencia pasa a `Despachada`.

## Paso 6. Registrar recepcion parcial

- **Que ve el usuario:** formulario de recepcion con cantidad recibida e incidencia.
- **Que debe hacer:** recibir solo una parte y marcar un faltante.
- **Por que importa:** esta es una escena fuerte de demo porque muestra manejo de excepciones reales.
- **Error comun:** hacer solo recepcion completa.
- **Resultado esperado:** transferencia queda en `Recepcion parcial` y la incidencia se ve en pantalla.

## Paso 7. Completar recepcion

- **Que ve el usuario:** mismo flujo de recepcion pero con saldo pendiente.
- **Que debe hacer:** completar la recepcion restante.
- **Por que importa:** muestra continuidad operativa sin perder trazabilidad.
- **Error comun:** no remarcar que el stock destino se va actualizando.
- **Resultado esperado:** transferencia queda `Recibida`.

## Paso 8. Mostrar auditoria

- **Que ve el usuario:** eventos recientes con acciones clave.
- **Que debe hacer:** mostrar login, creacion, aprobacion, despacho o recepcion.
- **Por que importa:** genera confianza en supervisores y tomadores de decision.
- **Error comun:** dejar la auditoria para el final sin conectar con acciones previas.
- **Resultado esperado:** el cliente entiende que nada relevante queda sin registro.

## Paso 9. Exportar reportes

- **Que ve el usuario:** botones para exportar inventario, backlog e historial filtrado.
- **Que debe hacer:** descargar un CSV en vivo.
- **Por que importa:** da una salida tangible y util.
- **Error comun:** no mencionar para que sirve el archivo exportado.
- **Resultado esperado:** el cliente percibe aplicacion practica inmediata.

## Checklist rapido de presentacion

- resetear demo antes de iniciar
- entrar como `admin`
- explicar problema antes que funciones
- mostrar una recepcion parcial con incidencia
- cerrar con auditoria y exporte

## Credenciales demo

- `admin / demo123`
- `supervisor / demo123`
- `origen / demo123`
- `destino / demo123`
