# Roadmap de Hardening Pre-Producción — Bodegaje

> **Origen**: evaluación integral del 2026-07-18.
> **Estado del proyecto al inicio**: spec cubierto 100%, 83 tests verdes, CI con 5 jobs, listo para staging. Deuda estructural concentrada en archivos grandes, secretos en disco y legacy duplicado.
> **Horizonte**: 4–5 semanas para producción con clientes reales.

---

## Convenciones del pipeline

Cada fase sigue este molde:

- **Objetivo** — qué entrega al final.
- **Pre-requisitos** — qué fases/estados deben estar listos antes de empezar.
- **Pasos** — numerados, con comandos exactos.
- **Criterios de salida** — qué se valida para declarar la fase cerrada.
- **Riesgos** — qué puede romperse y cómo mitigarlo.

Reglas globales durante todo el roadmap:

- **No commit directo a `main`**: PR por fase.
- **CI debe pasar antes de pedir review**.
- **No avanzar a la fase siguiente sin cerrar la actual**.
- **El `.env.production` local se trata como quemado hasta Fase 0 cerrada**.

---

## FASE 0 — Higiene crítica de secretos (Día 0, ~2 h)

### Objetivo
Eliminar el archivo `.env.production` con secretos reales del disco, rotar esos secretos, y garantizar que nunca más vuelva a ocurrir.

### Pre-requisitos
- Acceso al repo en `G:\PROYECTOS\bodega`.
- Confirmar que el archivo está fuera de git (ya lo está, pero se revalida).

### Pasos

1. **Validar que el archivo no está en git**
   ```powershell
   cd G:\PROYECTOS\bodega
   git ls-files | Select-String "\.env\.production$"
   # Si imprime vacío: OK. Si imprime path: abortar y limpiar git primero.
   ```

2. **Borrar el archivo del disco**
   ```powershell
   mavis-trash G:\PROYECTOS\bodega\.env.production
   ```

3. **Generar nuevos secretos con el script oficial**
   ```powershell
   cd G:\PROYECTOS\bodega
   python infra/scripts/generate-secrets.py --print-only | Tee-Object -FilePath .secrets-rotacion-$(Get-Date -Format yyyyMMdd).txt
   ```
   **No commitear ese archivo `.secrets-rotacion-*`**. Se guarda en una caja fuerte o se inyecta directo al sistema destino.

4. **Actualizar el `.env.production.example` con placeholders reforzados** (si aún tiene valores plausibles)
   - Reemplazar cualquier `JWT_SECRET=...` o `SECRET_KEY=...` por `JWT_SECRET=__GENERAR_CON_generate-secrets.py__`.
   - Aplicar la misma regla a `infra/.env.example` y `apps/api/.env.example`.

5. **Instalar `gitleaks` como pre-commit hook**
   ```powershell
   # Opción A: binario portable
   Invoke-WebRequest -Uri "https://github.com/gitleaks/gitleaks/releases/download/v8.18.4/gitleaks_8.18.4_windows_x64.zip" -OutFile gitleaks.zip
   Expand-Archive gitleaks.zip -DestinationPath C:\Tools\gitleaks
   $env:PATH += ";C:\Tools\gitleaks"
   gitleaks version
   ```
   Crear `.gitleaks.toml` en la raíz copiando la config de `infra/` si existe, o usando la default. Luego:
   ```powershell
   # Instalar framework de hooks
   pip install pre-commit
   pre-commit install
   ```
   Añadir `.pre-commit-config.yaml` en la raíz con:
   ```yaml
   repos:
     - repo: https://github.com/gitleaks/gitleaks-precommit
       rev: v1.0.0
       hooks:
         - id: gitleaks
   ```

6. **Correr `gitleaks` sobre todo el historial** para confirmar que no haya otros secretos:
   ```powershell
   gitleaks detect --source . --no-banner
   ```
   Si encuentra algo, evaluar `git filter-repo` para purgar (operación destructiva, hacer backup primero).

7. **Endurecer el job `security-scan` del CI** añadiendo un paso explícito:
   ```yaml
   - name: gitleaks full scan
     run: |
       curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/scripts/install.sh | sh -s -- -b /usr/local/bin
       gitleaks detect --source . --no-banner --redact
   ```

### Criterios de salida
- [ ] `git ls-files` confirma que `.env.production` nunca fue commiteado.
- [ ] El archivo no existe en el filesystem de la máquina de trabajo.
- [ ] `gitleaks detect` corre limpio en el repo completo.
- [ ] Pre-commit hook instalado y probado (`echo "SECRET=x" >> test.txt && git add test.txt` debe bloquear).
- [ ] CI corre `gitleaks` y falla si encuentra secretos.

### Riesgos
- **R1**: si `gitleaks` genera falsos positivos, ajustar `.gitleaks.toml` antes de mergear, no después.
- **R2**: los secretos rotados deben comunicarse al equipo vía canal seguro (no Slack público), y a cualquier sistema que los use (SES, RDS, etc.).

---

## FASE 1 — Refactor de backend (Semana 1, ~16 h)

### Objetivo
Reducir los archivos `service.py` gigantes a unidades cohesivas, eliminar el módulo `notifications/` legacy, y bajar el módulo `solicitudes` a un tamaño manejable.

### Pre-requisitos
- Fase 0 cerrada.
- Branch `refactor/fase-1-backend` creada desde `main`.

### Pasos

#### 1.1 Partir `solicitudes/service.py` (43 KB)

1. Crear estructura nueva:
   ```
   apps/api/app/modules/solicitudes/
   ├── service.py              # Orquestador delgado (< 8 KB)
   ├── actions/
   │   ├── __init__.py
   │   ├── crear.py
   │   ├── aprobar.py
   │   ├── despachar.py
   │   ├── recibir.py
   │   ├── rechazar.py
   │   └── cancelar.py
   └── replenishment.py        # Sin cambios
   ```

2. Mover cada acción a su archivo siguiendo la firma actual `async def accion_xxx(`. Mantener la exportación en `service.py` con `from app.modules.solicitudes.actions.crear import crear_solicitud` para no romper imports.

3. `service.py` queda como fachada que re-exporta las funciones públicas. Verificar:
   ```powershell
   grep -rn "from app.modules.solicitudes.service" apps/api/app
   grep -rn "from app.modules.solicitudes import" apps/api/app
   ```

4. Correr tests específicos:
   ```powershell
   cd G:\PROYECTOS\bodega\apps\api
   pytest tests/unit/test_solicitudes.py -x
   pytest tests/integration/test_solicitudes.py -x
   ```

#### 1.2 Partir `ordenes_compra/service.py` (24 KB)

1. Misma estrategia: `actions/crear.py`, `actions/enviar.py`, `actions/aprobar.py`, `actions/rechazar.py`. Dejar `service.py` como fachada.

2. Prestar atención al `public_router.py`: usa `aprobar_oc` y `rechazar_oc` que tocan la firma HMAC. No cambiar la firma pública.

3. Validar con:
   ```powershell
   pytest tests/unit/test_ordenes_compra.py -x
   pytest tests/integration/test_ordenes_compra.py -x
   ```

#### 1.3 Eliminar `notifications/` legacy (Fase 7)

1. Auditar usos:
   ```powershell
   grep -rn "from app.modules.notifications" apps/api
   ```
2. Reemplazar cada uso por `from app.modules.notificaciones import ...`.
3. Borrar el módulo:
   ```powershell
   mavis-trash G:\PROYECTOS\bodega\apps\api\app\modules\notifications
   ```
4. Limpiar el `api/router.py`: eliminar la línea `api_router.include_router(notifications_router, ...)`.
5. Actualizar el ADR-0003 marcando la migración como cerrada.

#### 1.4 Reducir `db/session.py` (27 KB)

1. Extraer la lógica de compatibilidad dual backend a `db/compat/`. Dejar `session.py` solo con la fábrica activa.
2. Si la compatibilidad dual ya no se necesita (Fase 1 de producción), considerar borrar `db/sqlite.py` y `db/postgres.py` separadas y unificarlas.

### Criterios de salida
- [ ] `solicitudes/service.py` ≤ 8 KB.
- [ ] `ordenes_compra/service.py` ≤ 8 KB.
- [ ] `db/session.py` ≤ 12 KB.
- [ ] Carpeta `notifications/` borrada, sin imports rotos.
- [ ] 83 tests siguen verdes (más los que se agreguen).
- [ ] CI pasa (lint + mypy + tests).

### Riesgos
- **R1**: romper el lock pesimista del `MovementEngine` durante el refactor de `solicitudes/despachar.py` y `recibir.py`. Test específico: `test_concurrent_movement_engine.py`.
- **R2**: cambiar firmas internas puede romper el `public_router` de OC. Test: `test_ordenes_compra.py` cubre HMAC.

---

## FASE 2 — Refactor de frontend (Semana 2, ~16 h)

### Objetivo
Partir las vistas gigantes en componentes cohesivos, limpiar mocks obsoletos, conectar o eliminar páginas stub.

### Pre-requisitos
- Fase 1 cerrada.
- Branch `refactor/fase-2-frontend` desde `main`.

### Pasos

#### 2.1 Partir `OrdenesCompraPage.jsx` (36 KB)

1. Identificar secciones en el archivo (CRUD tabla, drawer de creación, modal de envío, modal de aprobación).
2. Crear:
   ```
   apps/web/src/components/ordenes-compra/
   ├── OrdenCompraTable.jsx
   ├── OrdenCompraCreateDrawer.jsx
   ├── OrdenCompraEnviarModal.jsx
   └── OrdenCompraAprobacionModal.jsx
   ```
3. La vista queda como composición de componentes.

#### 2.2 Partir `SettingsPage.jsx` (34 KB)

1. Misma estrategia: una sub-página por sección (categorías, ubicaciones, usuarios, sistema).
2. Considerar rutas anidadas si la lógica lo amerita (`/settings/categorias`, `/settings/usuarios`).

#### 2.3 Partir `ReportsPage.jsx` (30 KB) y `SolicitudesAuxPage.jsx` (23 KB)

1. Extraer `KpiCard`, `ReporteTabla`, `SolicitudForm`, `SolicitudHistorial` a `components/`.

#### 2.4 Conectar o eliminar stubs

1. **Auditar `SlottingPage.jsx`**: si no consume `/api/v1/slotting` (no existe), mover a una `404` o eliminar.
2. **Auditar `ChatPage.jsx`**: idem. Si no hay endpoint, eliminar.
3. **Limpiar `mock.js`**: si la página ya está integrada a API real, eliminar el import. Si es para modo offline, documentar.

#### 2.5 Agregar tests unitarios de componentes

1. Ya hay 4 tests en `__tests__/`. Cubrir al menos `BarcodeInput`, `MultibodegaGrid` (los más críticos).
2. Cobertura objetivo: ≥ 50% en `components/` y ≥ 40% en `views/`.

### Criterios de salida
- [ ] Ningún archivo `.jsx` en `views/` supera 15 KB.
- [ ] Cada vista es composición de 2-5 componentes de `components/`.
- [ ] No hay referencias a `mock.js` en código de producción.
- [ ] `SlottingPage` y `ChatPage` justificadas o eliminadas.
- [ ] `npm run build` sin warnings nuevos.
- [ ] `npm run lint` limpio.
- [ ] Tests de frontend pasan.

### Riesgos
- **R1**: romper el enrutado de `react-router-dom` al mover vistas. Test: smoke test manual de cada ruta.
- **R2**: cambios de layout/CSS al extraer sub-componentes. Validar visualmente con `npm run dev` y comparar con la versión anterior (screenshots).

---

## FASE 3 — Calidad, testing y performance (Semana 3, ~16 h)

### Objetivo
Subir la calidad de los tests, hacerlos más rápidos y granulares, auditar queries pesadas en los endpoints críticos.

### Pre-requisitos
- Fases 1 y 2 cerradas.

### Pasos

#### 3.1 Segmentar `conftest.py`

1. Mover fixtures grandes a `tests/integration/conftest.py` y `tests/unit/conftest.py` específicos.
2. Sacar fixtures de `tests/conftest.py` solo si son cross-suite.

#### 3.2 Partir tests gigantes

1. `test_solicitudes.py` (40 KB) → separar en `test_solicitudes_aprobar.py`, `test_solicitudes_despachar.py`, etc.
2. `test_replenishment_evaluator.py` (28 KB) → separar escenarios en archivos.
3. `test_recepcion_escaneo.py` (22 KB) → OK si lo dejas, pero agregar `conftest_escaneo.py` con fixtures reutilizables.

#### 3.3 Audit de performance

1. Identificar endpoints con queries grandes:
   - `GET /api/v1/inventory/multibodega?sku=X`
   - `GET /api/v1/inventory/summary`
   - `GET /api/v1/consolidador/quiebres`
2. Activar logs SQL temporalmente:
   ```powershell
   $env:DATABASE_ECHO = "true"
   uvicorn app.main:app --reload
   ```
3. Verificar queries N+1 (cualquier `await db.execute(...)` dentro de un loop).
4. Confirmar índices en `app/db/models/` para las FK más consultadas (`warehouse_id`, `product_id`, `solicitud_id`).

#### 3.4 Agregar índice si falta

1. Crear migración Alembic `0010_indices_performance.py`.
2. Caso típico: índice compuesto `(warehouse_id, product_id)` en `stock_real` y `inventory`.
3. Medir con `EXPLAIN ANALYZE` antes y después.

#### 3.5 Subir el umbral de cobertura

1. CI actual exige `--cov-fail-under=80`. Subir a `85`.
2. Identificar módulos con cobertura < 80% y agregar tests específicos.

### Criterios de salida
- [ ] Ningún test individual supera 25 KB.
- [ ] Cobertura global ≥ 85%.
- [ ] `EXPLAIN ANALYZE` documentado para los 3 endpoints críticos.
- [ ] Migración 0010 mergeada.

### Riesgos
- **R1**: agregar índices puede romper migraciones si hay datos pre-existentes. Testear upgrade en una DB de staging primero.
- **R2**: subir el umbral de cobertura puede revelar módulos sin tests. Agregar tests antes de subir el umbral, no después.

---

## FASE 4 — Pre-producción (Semana 4, ~12 h)

### Objetivo
Validar el sistema completo en un entorno staging realista, con datos sintéticos, pruebas E2E y simulaciones de incidente.

### Pre-requisitos
- Fases 1, 2 y 3 cerradas.

### Pasos

#### 4.1 Desplegar en staging

1. Usar el script oficial:
   ```powershell
   .\infra\scripts\start-staging.ps1
   ```
2. Verificar:
   - `curl http://staging.bodega/api/v1/health` → 200.
   - `curl http://staging.bodega/metrics` → métricas Prometheus.
   - Mailpit recibe emails: `http://staging.bodega:8025`.

#### 4.2 Smoke E2E manual

1. Cargar seed de demo:
   ```powershell
   python apps/api/app/db/seed.py
   ```
2. Ejecutar el script `tests/manual/test_e2e_fase4.py` (workflow de solicitudes) y `test_e2e_fase7.py` (workflow SMTP).
3. Validar visualmente cada vista del frontend en `staging.bodega`.

#### 4.3 Load test

1. Instalar `locust`:
   ```powershell
   pip install locust
   ```
2. Crear `infra/tests/load/locustfile.py` con escenarios: login, listar productos, crear solicitud, dispatch.
3. Correr:
   ```powershell
   locust -f infra/tests/load/locustfile.py --host=http://staging.bodega -u 50 -r 10 --run-time 5m
   ```
4. Documentar RPS, p50, p95, p99. Establecer SLO: p95 < 500 ms para endpoints GET.

#### 4.4 Simular incidentes

1. **Postgres down**: parar el contenedor, verificar que el healthcheck marca `degraded`, que la API responde 503 (no 500).
2. **Mailpit down**: verificar que el outbox de notificaciones encola y no rompe el flujo.
3. **Worker arq down**: verificar que la API sigue respondiendo, que las solicitudes se encolan, que al levantar el worker se procesan.
4. **Nginx caído**: verificar que el healthcheck externo también cae.

#### 4.5 Verificar backups

1. Ejecutar `infra/scripts/backup-postgres.sh` y verificar que el archivo `.dump` se genera.
2. Ejecutar `infra/scripts/restore-postgres.sh` en una DB limpia y validar datos.
3. Documentar el tiempo de backup/restore en el runbook.

#### 4.6 Runbook walkthrough

1. Leer `docs/operations/runbook.md` y `infra/operations/DEPLOYMENT_RUNBOOK.md`.
2. En un board, recorrer cada escenario y validar que los pasos están claros.
3. Actualizar lo que falte.

### Criterios de salida
- [ ] Staging levantado y respondiendo 200 en health.
- [ ] Smoke E2E manual ejecutado y documentado.
- [ ] Load test ejecutado, SLO documentado.
- [ ] 4 simulaciones de incidente ejecutadas, respuestas del sistema documentadas.
- [ ] Backup + restore probados en DB limpia.
- [ ] Runbook actualizado.

### Riesgos
- **R1**: el load test puede tumbar la DB de staging. Tener un script de reset (`infra/scripts/reset-demo.ps1`).
- **R2**: las simulaciones de incidente deben coordinarse con el equipo para no confundir a usuarios reales si staging es compartido.

---

## FASE 5 — Go-live (cuando llegue, ~8 h)

### Objetivo
Desplegar a producción con todos los controles activados y un plan de rollback listo.

### Pre-requisitos
- Fase 4 cerrada.
- Decisión go/no-go firmada por el responsable.

### Pasos

1. **Pre-deploy check**:
   ```powershell
   bash infra/scripts/pre-deploy-check.sh
   ```
   Debe pasar 100%.

2. **Backup pre-deploy**:
   ```powershell
   bash infra/scripts/backup-postgres.sh
   ```
   Guardar el archivo en almacenamiento off-site.

3. **Desplegar**:
   ```powershell
   .\infra\scripts\start-production.ps1
   ```

4. **Smoke post-deploy**:
   ```powershell
   curl https://app.bodega/api/v1/health
   curl https://app.bodega/metrics
   ```
   Validar primera carga del frontend, login, una solicitud end-to-end.

5. **Monitoreo intensivo 24 h**:
   - Dashboard Prometheus abierto.
   - Sentry revisado cada 2-4 horas.
   - Logs con `LOG_LEVEL=INFO` para detectar errores.

6. **Si hay incidente, ejecutar rollback** documentado en `infra/operations/DEPLOYMENT_RUNBOOK.md`.

7. **Post-mortem a las 72 h**: documento de qué funcionó, qué no, qué mejorar.

### Criterios de salida
- [ ] Sistema en producción, health 200.
- [ ] 1 solicitud end-to-end completada con datos reales.
- [ ] 24 h sin errores críticos en logs/Sentry.
- [ ] Runbook de rollback verificado.

### Riesgos
- **R1**: si el primer usuario reporta un bug bloqueante, ejecutar rollback inmediato sin intentar parchar en caliente.
- **R2**: mantener `LOG_LEVEL=INFO` solo 72 h, después volver a `WARNING` (config ya en `.env.production.example`).

---

## Resumen visual

| Fase | Semana | Horas | Riesgo | Entregable verificable |
|------|--------|------:|--------|------------------------|
| 0 | Día 0 | 2 | 🔴 Alto | `.env.production` borrado, gitleaks en CI |
| 1 | Sem 1 | 16 | 🟠 Medio | `solicitudes/service.py` ≤ 8 KB, sin `notifications/` |
| 2 | Sem 2 | 16 | 🟢 Bajo | Ninguna vista > 15 KB |
| 3 | Sem 3 | 16 | 🟠 Medio | Cobertura ≥ 85%, índices validados |
| 4 | Sem 4 | 12 | 🟠 Medio | Staging validado, backups probados |
| 5 | Go-live | 8 | 🔴 Alto | Sistema en producción, 24 h monitoreado |

**Total**: ~70 horas distribuidas en 4-5 semanas, ejecutable por 1-2 personas a tiempo parcial.

---

## Cómo trackear el avance

1. Crear un **issue por fase** en GitHub con la checklist de criterios de salida.
2. Cada PR cierra al menos un criterio.
3. Reunión semanal de 30 min para revisar avance y blockers.
4. El CHANGELOG_PROYECTO.md se actualiza al cerrar cada fase.

---

## Después del go-live (no incluido en este roadmap)

Lo que el propio `RESUMEN_FINAL.md` sugiere como siguientes pasos:

1. Integración con ERP vía webhook.
2. Mobile app nativa para escaneo en piso.
3. Reportes ABC y forecasting.
4. Multi-tenancy.
5. Lotes y series (vencimientos, serial numbers).
6. ML para forecasting de quiebres.

Estos se planifican en un roadmap posterior, una vez que producción esté estable 30+ días.
