# Propuesta de Producción — Documentos Ejecutables

Esta carpeta contiene los **4 documentos derivados de la sección 22.1 de
`PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md`**, producidos a partir del
código y de los esquemas vigentes al 2026-07-22.

## Los 4 documentos

| # | Documento | Tamaño | Qué responde |
|---|---|---|---|
| 1 | [`01_requerimientos_funcionales_y_no_funcionales.md`](./01_requerimientos_funcionales_y_no_funcionales.md) | ~22 KB | ¿Qué hace el sistema? ¿Qué reglas aplica? ¿Qué tan rápido/seguro/auditable es? |
| 2 | [`02_modelo_datos_3fn.md`](./02_modelo_datos_3fn.md) | ~29 KB | ¿Cómo están organizadas las tablas? ¿Qué está normalizado y qué no, y por qué? |
| 3 | [`03_arquitectura_tecnica.md`](./03_arquitectura_tecnica.md) | ~27 KB | ¿Cómo se conectan los componentes? ¿Dónde corre cada cosa? ¿Qué patrones se aplican? |
| 4 | [`04_plan_desarrollo_sprints.md`](./04_plan_desarrollo_sprints.md) | ~16 KB | ¿Qué se hace primero? ¿Cuánto tarda? ¿Qué dependencias hay entre tareas? |

## Cómo leerlos

- **Si vienes de producto/operaciones:** lee solo el **Doc 1** (RF-01..120)
  y la sección de criterios de aceptación. Te da el "qué" sin entrar en
  detalle técnico.
- **Si vienes de ingeniería y te toca implementar:** lee **Doc 2** + **Doc 3**
  para tener el modelo y la arquitectura, y **Doc 4** para saber en qué
  sprint entras.
- **Si vienes de QA:** lee **Doc 1** completo (incluye RNF) y la sección
  6 del **Doc 1** (criterios de aceptación). La batería E2E ya valida
  ~50% de los RF.
- **Si vienes a hacer go-live:** lee **Doc 1 §6** (cumplimiento de criterios
  de aceptación) + **Doc 4 §6** (qué falta para producción completa).

## Estado de los documentos

Estos documentos son **versionados con la base de código**. Cuando
modifiques el código que afecta un RF, una tabla o un componente,
actualiza el documento correspondiente en el mismo commit.

| Doc | Trazabilidad al código |
|---|---|
| 1 | Cada `RF-NN` referencia `path:linenumbers` o nombre de test |
| 2 | Cada tabla referencia `db/migrations/NNNN_*.sql` o modelo en `app/db/models/` |
| 3 | Cada componente referencia `app/modules/<x>/` o `app/core/<x>.py` |
| 4 | Cada tarea referencia el commit donde se cerró o el issue abierto |

## Lo que NO está en estos documentos

- **Tutorial de uso de la app.** Eso está en `docs/product/manual-de-usuario-completo.md`.
- **Runbook operacional del día a día.** Eso está en
  `docs/operations/runbook.md` y `docs/go_live_runbook.md`.
- **Informes de sprint ya cerrados.** Esos están en `docs/fases/` y
  `docs/HANDOFF_SESION_2026-07-15.md`.
- **Decisiones arquitectónicas individuales (ADRs).** Esos están en
  `docs/adr/`.

## Conexión con la propuesta original

Estos 4 documentos son la **implementación verificable** de lo que la
propuesta original describe como愿景 y alcance. La propuesta vive en
`PROPUESTA_PRODUCCION_SISTEMA_MULTI_BODEGA.md` (raíz del repo). Este
directorio es el "puente" entre esa propuesta y el código.

Si la propuesta dice "RF-50: stock disponible = stock actual − stock
reservado", el Doc 1 lo traduce a "RF-51" + "RF-52" verificables en el
código actual. Si dice "Postgres + Redis + WebSockets", el Doc 3
muestra qué porcentaje está implementado y qué fase lo cubre.

## Mantenimiento

- **Frecuencia de actualización:** cada sprint cerrado debe revisar si
  los RF, las tablas o los componentes cambiaron.
- **Owner:** equipo de ingeniería (revisar en PR de cierre de sprint).
- **Formato:** Markdown con tablas. Sin dependencias externas (no usa
  Mermaid, no usa imágenes binarias) — los diagramas están en ASCII.
