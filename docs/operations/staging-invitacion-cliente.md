# Plantilla de invitación al cliente piloto (C4.6)

> **Uso:** copiar este texto a un email, llenar los campos entre
> corchetes, y enviar al cliente 1-2 días antes del inicio del período
> de prueba.

---

**Asunto:** Bienvenido al período de prueba de Bodegaje

Hola [NOMBRE],

¡Ya estamos listos para que pruebes **Bodegaje**! Te hemos preparado un
ambiente de **staging** (idéntico al de producción pero con datos de
prueba) para que puedas recorrer el sistema sin riesgo.

## Lo que necesitas

### 1. Acceso a la plataforma

- **URL:** https://staging.bodega.cl
- **Usuario:** [USUARIO]  (ej: `admin1-12345`)
- **Contraseña:** [PASSWORD]  (te la enviamos por separado por seguridad)

Una vez dentro, puedes cambiar tu contraseña en `Mi perfil`.

### 2. Recomendaciones de prueba

Te sugerimos recorrer el sistema en este orden (es el flujo real de uso):

1. **Inicio (5 min):** Inicia sesión y recorre el dashboard principal.
2. **Catálogo (10 min):** Ve a `Productos` y `Bodegas`. Crea al menos
   una bodega auxiliar y un producto nuevo.
3. **Stock (10 min):** Registra movimientos de inventario (entradas y
   salidas). Verifica que el stock se actualice en tiempo real.
4. **Solicitud de reposición (15 min):** Como operador origen, crea
   una solicitud a la bodega principal. Apruébala, despáchala y recíbela.
5. **Orden de compra (20 min):** Crea una OC a un proveedor. Apruébala
   usando el link que llega al supervisor por email.
6. **Reportes (10 min):** Ve a `Reportes` y revisa los KPIs.

**Tiempo total:** ~1 hora para el happy path completo.

### 3. Recursos

- **Manual de usuario:** [URL del manual]  (o `docs/product/manual-de-usuario-completo.md`)
- **Soporte:** [EMAIL/SLACK]  (respondo en horario hábil)

### 4. Tu feedback es oro

Durante el período de prueba, registra lo que encuentres:

- 🐛 **Bugs:** anota el flujo exacto que seguiste y qué pasó vs qué esperabas.
- 💡 **Ideas de mejora:** aunque parezca obvio, anótalo.
- ❓ **Confusiones:** si algo no es intuitivo, es un bug de UX.

Puedes mandarme todo por email, Slack, o agendar una llamada de 30 min
para el [FECHA].

## Alcance del período de prueba

- **Inicio:** [FECHA_INICIO]
- **Fin:** [FECHA_FIN]
- **Datos:** la BD se reinicia al final del período (no se conserva nada).

## Lo que NO debes probar

- ❌ No cargues datos reales de tu negocio (clientes, precios). Usa datos ficticios.
- ❌ No invites a usuarios externos. El ambiente es solo para ti.
- ❌ No modifiques la configuración (bodegas base, supervisores). Si necesitas
   algo, pídemelo.

¡Gracias por probar! Cualquier duda, escríbeme.

Saludos,
[NOMBRE]
[CARGO]
[CONTACTO]
