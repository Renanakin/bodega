# Fases del proyecto

Este directorio contiene la documentación técnica de cada fase del roadmap.

## Fases completadas

| Fase | Título | Estado | Doc |
|---|---|---|---|
| 0 | Decisiones arquitecturales (6 ADRs) | ✅ Completada | `docs/adr/` |
| 1 | PostgreSQL real (SQLAlchemy 2.0 async + Alembic) | ✅ Completada | [`fase-1-postgres-real.md`](./fase-1-postgres-real.md) |
| 2 | Multibodega física (categorías + ubicaciones + stock_real + BarcodeInput) | ✅ Completada | [`fase-2-multibodega-fisica.md`](./fase-2-multibodega-fisica.md) |

## Roadmap restante

Ver [`roadmap-fase-3-a-10.md`](./roadmap-fase-3-a-10.md) para los prompts optimizados de las fases 3 a 10.

## Fases pendientes

| Fase | Título | Subagente | Skills | Estado |
|---|---|---|---|---|
| 3 | Solicitudes N-productos (reemplazo de transfers) | `coder` | software-architecture, saga-orchestration, production-code-audit, e2e-testing-patterns | 📋 Listo para ejecutar |
| 4 | Replenishment automático (cron Arq) | `coder` | workflow-orchestration-patterns, production-code-audit, testing-patterns | 📋 Listo para ejecutar |
| 5 | Recepción con escaneo de código de barras | `coder` | testing-patterns, e2e-testing-patterns | 📋 Listo para ejecutar |
| 6 | Frontend Supervisores + Órdenes de Compra | `coder` | production-code-audit, tailwind-patterns | 📋 Listo para ejecutar |
| 7 | Notificaciones SMTP async + Mailpit | `coder` | workflow-orchestration-patterns, production-code-audit, testing-patterns | 📋 Listo para ejecutar |
| 8 | Resto de vistas nuevas con Tailwind | `coder` | tailwind-design-system, product-design, ui-pattern | 📋 Listo para ejecutar |
| 9 | Observabilidad mínima (structlog + Prometheus) | `coder` | production-code-audit, error-handling-patterns | 📋 Listo para ejecutar |
| 10 | Hardening para producción | `coder` | cloudformation-best-practices, production-code-audit | 📋 Listo para ejecutar |
