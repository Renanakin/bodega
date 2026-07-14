# Review Guardian - 2026-06-25

## Resumen ejecutivo

El producto ya permite una demo funcional fuerte: login por rol, dashboard comercial, flujo de inventario, transferencias por etapas, incidencias, auditoria y exportes. No se detectan bloqueos criticos para una presentacion comercial controlada.

El mayor riesgo actual no esta en el flujo base, sino en la profundidad limitada de algunos modulos secundarios y en detalles de experiencia que pueden reducir percepcion de madurez si el cliente explora mas alla del recorrido guiado.

## Hallazgos priorizados

### Alto

#### 1. Modulos secundarios con sensacion de placeholder

- **Problema:** vistas como `chat`, `slotting` y parte de `reposicion` siguen luciendo mas conceptuales que operativas.
- **Impacto:** si el cliente navega libremente, puede percibir inconsistencia entre el nivel de madurez del flujo principal y el resto del producto.
- **Evidencia:** el producto concentra la profundidad real en `dashboard`, `inventario`, `transferencias`, `reportes` y `auditoria`.
- **Recomendacion:** para demo libre, ocultar o etiquetar modulos secundarios como “proxima fase” o reducir su protagonismo en navegacion.

#### 2. Exportes solo en CSV

- **Problema:** los reportes exportan CSV, pero no existe formato ejecutivo listo para compartir con gerencia.
- **Impacto:** el cliente operativo lo valora, pero el decisor comercial puede querer una salida mas presentable.
- **Evidencia:** `Reportes` ya exporta historiales e inventario, pero no hay PDF o snapshot ejecutivo.
- **Recomendacion:** agregar exporte ejecutivo o al menos una vista “resumen gerencial”.

### Medio

#### 3. Auditoria visible pero no enriquecida con nombre de usuario

- **Problema:** la auditoria muestra eventos, pero puede quedar corta si el cliente espera lectura humana inmediata.
- **Impacto:** la trazabilidad existe, pero la percepcion de control podria mejorar.
- **Evidencia:** el registro se enfoca en `action`, `entity_type`, `entity_id`, `detail`.
- **Recomendacion:** enriquecer filas con nombre visible del usuario y etiquetas mas humanas.

#### 4. Falta de modo demo bloqueado

- **Problema:** aunque existe recorrido sugerido, el producto no limita ni encauza completamente la navegacion durante una demo.
- **Impacto:** un usuario curioso puede desviarse a pantallas menos convincentes.
- **Evidencia:** el dashboard sugiere pasos, pero no existe “present mode” real.
- **Recomendacion:** agregar un interruptor de presentacion que reduzca menu y destaque el recorrido ideal.

### Bajo

#### 5. Textos de estado internos aun visibles

- **Problema:** algunos estados o campos siguen mostrando nomenclatura mas tecnica que comercial.
- **Impacto:** no rompe la demo, pero baja refinamiento.
- **Evidencia:** algunos valores internos como estados de transferencia vienen del dominio y no siempre del lenguaje comercial final.
- **Recomendacion:** normalizar todo el copy a lenguaje de negocio.

## Riesgos para demo o piloto

- el flujo principal responde bien si el recorrido es guiado
- la percepcion baja si el cliente inspecciona modulos menos maduros
- el piloto operativo aun requerira endurecer persistencia multiusuario real y politicas de sesion

## Checklist sugerido

- reducir protagonismo de modulos secundarios en demo
- enriquecer auditoria visual
- agregar modo presentacion
- reforzar copy ejecutivo en reportes y dashboard
- preparar salida exportable pensada para decisores
