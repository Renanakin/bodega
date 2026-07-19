"""
Metricas Prometheus custom de Bodegaje (Fase 9 + 11).

Stack: prometheus-client + prometheus-fastapi-instrumentator.

Convenciones:
- Todas las metricas custom usan el prefijo ``bodegaje_`` para evitar
  colisiones con metricas estandar de Python/FastAPI.
- Cardinalidad baja: solo labels discretos (estado, prioridad, tipo).
  NUNCA labels con alta cardinalidad (UUIDs, paths, user_ids).
- Gauges se actualizan desde la BD por un cron job del worker
  (``update_metrics_task``), NO en cada request (evita saturar la BD).
- Counters se incrementan in-line en el codigo de negocio
  (``solicitud.creada``, ``email.sent``).

Metricas HTTP automaticas (prometheus-fastapi-instrumentator):
- ``http_requests_total{method, status, handler}`` — contador.
- ``http_request_duration_seconds{method, status, handler}`` — histograma.
- ``http_requests_in_progress`` — gauge.

Custom metrics:
- Solicitudes: creadas, despachadas, recibidas, rechazadas, por estado.
- Ordenes de compra: enviadas a supervisor, aprobadas.
- Email outbox: pending (gauge), sent, failed (con error_type), dead.
- Replenishment: ultimo run (gauge), solicitudes creadas.
- Stock: movimientos, oversells rechazados.
- Worker: pool BD.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator


# =============================================================================
# Solicitudes
# =============================================================================

# Contador: solicitudes creadas, con label de tipo de bodega origen
# y prioridad. Cardinalidad: 3 tipos (aux/box/principal) x 3 prioridades
# (normal/alta/urgente) = 9 max. OK para Prometheus.
SOLICITUDES_CREADAS = Counter(
    "bodegaje_solicitudes_creadas_total",
    "Total de solicitudes de recarga creadas",
    labelnames=["bodega_origen_tipo", "prioridad"],
)

# Alias retro-compat (Fase 11 plan original usaba este nombre).
solicitudes_creadas_total = SOLICITUDES_CREADAS

SOLICITUDES_DESPACHADAS_TOTAL = Counter(
    "bodegaje_solicitudes_despachadas_total",
    "Total de solicitudes despachadas (estado -> in_transit)",
)
solicitudes_despachadas_total = SOLICITUDES_DESPACHADAS_TOTAL

SOLICITUDES_RECIBIDAS_TOTAL = Counter(
    "bodegaje_solicitudes_recibidas_total",
    "Total de solicitudes recibidas (completa o parcial)",
    labelnames=["completa"],  # "true" o "false"
)
solicitudes_recibidas_total = SOLICITUDES_RECIBIDAS_TOTAL

SOLICITUDES_RECHAZADAS_TOTAL = Counter(
    "bodegaje_solicitudes_rechazadas_total",
    "Total de solicitudes rechazadas",
)
solicitudes_rechazadas_total = SOLICITUDES_RECHAZADAS_TOTAL

# Gauge: solicitudes por estado. Cardinalidad: 6 estados (pending,
# approved, in_transit, partially_received, received, cancelled, rejected).
# Se actualiza desde la BD cada 60s por el cron del worker.
SOLICITUDES_POR_ESTADO = Gauge(
    "bodegaje_solicitudes_por_estado",
    "Cantidad actual de solicitudes por estado (snapshot desde BD)",
    labelnames=["estado"],
)


# =============================================================================
# Ordenes de compra
# =============================================================================

ORDENES_COMPRA_ENVIADAS_TOTAL = Counter(
    "bodegaje_ordenes_compra_enviadas_total",
    "Total de OC enviadas a supervisor (encolado de email)",
)
ordenes_compra_enviadas_total = ORDENES_COMPRA_ENVIADAS_TOTAL

ORDENES_COMPRA_APROBADAS_TOTAL = Counter(
    "bodegaje_ordenes_compra_aprobadas_total",
    "Total de OC aprobadas (via token o admin)",
    labelnames=["via"],  # "token" o "admin"
)
ordenes_compra_aprobadas_total = ORDENES_COMPRA_APROBADAS_TOTAL


# =============================================================================
# Email outbox
# =============================================================================

# Gauge: emails pendientes en outbox. Se actualiza desde la BD cada 60s.
EMAIL_OUTBOX_PENDING = Gauge(
    "bodegaje_email_outbox_pending",
    "Cantidad de emails pendientes en el outbox (snapshot desde BD)",
)
email_outbox_pending = EMAIL_OUTBOX_PENDING

EMAIL_SENT_TOTAL = Counter(
    "bodegaje_email_sent_total",
    "Total de emails enviados exitosamente",
)
email_outbox_sent_total = EMAIL_SENT_TOTAL  # alias retro-compat

# Counter: emails que fallaron al enviar. Label: tipo de error
# (transient o permanent) — baja cardinalidad.
EMAIL_FAILED_TOTAL = Counter(
    "bodegaje_email_failed_total",
    "Total de emails que fallaron al enviar (por tipo de error)",
    labelnames=["error_type"],
)
email_outbox_failed_total = EMAIL_FAILED_TOTAL  # alias retro-compat

EMAIL_DEAD_TOTAL = Counter(
    "bodegaje_email_dead_total",
    "Total de emails que pasaron a dead letter (max_attempts alcanzado)",
)

# Histograma: duracion del envio SMTP. Buckets optimizados para SMTP
# (esperado: 0.05s a 2s; cola a 5-30s si el server SMTP esta lento).
EMAIL_SMTP_SEND_DURATION = Histogram(
    "bodegaje_email_smtp_send_duration_seconds",
    "Duracion del envio SMTP en segundos",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
smtp_send_duration = EMAIL_SMTP_SEND_DURATION  # alias retro-compat


# =============================================================================
# Replenishment
# =============================================================================

REPLENISHMENT_EVALUATOR_LAST_RUN = Gauge(
    "bodegaje_replenishment_evaluator_last_run_timestamp",
    "Timestamp de la ultima ejecucion del ReplenishmentEvaluator",
)
replenishment_evaluator_last_run = REPLENISHMENT_EVALUATOR_LAST_RUN  # alias

REPLENISHMENT_SOLICITUDES_CREADAS_TOTAL = Counter(
    "bodegaje_replenishment_solicitudes_creadas_total",
    "Total de solicitudes creadas por el ReplenishmentEvaluator automatico",
)
replenishment_solicitudes_creadas_total = (
    REPLENISHMENT_SOLICITUDES_CREADAS_TOTAL
)


# =============================================================================
# Stock
# =============================================================================

STOCK_MOVEMENTS_TOTAL = Counter(
    "bodegaje_stock_movements_total",
    "Total de movimientos de stock procesados por MovementEngine",
    labelnames=["movement_type", "result"],  # IN/OUT/ADJUST, ok/oversell
)
stock_movements_total = STOCK_MOVEMENTS_TOTAL  # alias retro-compat

OVERSELL_REJECTED_TOTAL = Counter(
    "bodegaje_oversell_rejected_total",
    "Total de movimientos rechazados por oversell (stock insuficiente)",
)
oversell_rejected_total = OVERSELL_REJECTED_TOTAL  # alias retro-compat


# =============================================================================
# Healthcheck
# =============================================================================

DB_POOL_SIZE_ACTIVE = Gauge(
    "bodegaje_db_pool_size_active",
    "Conexiones activas en el pool de la BD (Postgres)",
)
db_pool_size_active = DB_POOL_SIZE_ACTIVE  # alias retro-compat

DB_POOL_SIZE_IDLE = Gauge(
    "bodegaje_db_pool_size_idle",
    "Conexiones idle en el pool de la BD (Postgres)",
)
db_pool_size_idle = DB_POOL_SIZE_IDLE  # alias retro-compat


# =============================================================================
# Instrumentator (metricas HTTP automaticas)
# =============================================================================


def instrument_app(app) -> None:  # type: ignore[no-untyped-def]
    """Monta el Instrumentator de FastAPI en la app.

    Configuracion:
    - ``should_group_status_codes=True``: agrupa 2xx/3xx/4xx/5xx en el
      label ``status`` (reduce cardinalidad de 20+ status codes a 4).
    - ``should_ignore_untemplated=True``: ignora paths dinamicos no
      declarados (e.g. ``/api/v1/products/{uuid}`` -> no se trackea
      el uuid, solo el handler). Reduce cardinalidad a 1.
    - ``excluded_handlers``: ``/health`` y ``/metrics`` se excluyen
      del tracking para no contaminar las metricas con checks de
      Kubernetes (que disparan cada N segundos).

    Usage:
        from app.modules.observability.metrics import instrument_app
        instrument_app(app)  # en main.py, despues de crear la app
    """
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    )
    instrumentator.instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )


# =============================================================================
# Helpers para actualizar gauges desde la BD
# =============================================================================
# Estas funciones se llaman desde el cron job del worker
# (``update_metrics_task``) cada 60s. NO se llaman en cada request
# para evitar saturar la BD.


async def update_solicitudes_gauge_from_db(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Actualiza ``SOLICITUDES_POR_ESTADO`` desde la BD.

    Args:
        session_factory: callable que retorna una ``AsyncSession`` (típicamente
            ``app.db.session.get_session_factory()``).
    """
    # Import local para evitar circular imports al cargar el modulo.
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.db.models.solicitudes import SolicitudRecarga  # noqa: PLC0415

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(
                    SolicitudRecarga.estado, func.count(SolicitudRecarga.id)
                ).group_by(SolicitudRecarga.estado)
            )
        ).all()
        for estado, count in rows:
            # ``estado`` es un enum; convertir a su ``.value`` (string).
            estado_str = estado.value if hasattr(estado, "value") else str(estado)
            SOLICITUDES_POR_ESTADO.labels(estado=estado_str).set(count)


async def update_email_outbox_gauge_from_db(session_factory) -> None:  # type: ignore[no-untyped-def]
    """Actualiza ``EMAIL_OUTBOX_PENDING`` desde la BD.

    Cuenta los emails en ``email_outbox`` con ``status='pending'``.
    """
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.db.models.ordenes_compra import EmailOutbox  # noqa: PLC0415

    async with session_factory() as session:
        count = (
            await session.execute(
                select(func.count(EmailOutbox.id)).where(
                    EmailOutbox.status == "pending"
                )
            )
        ).scalar_one()
        EMAIL_OUTBOX_PENDING.set(count)
