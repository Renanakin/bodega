"""Arq worker para tareas async (Fase 4 + Fase 7).

Este modulo es el entry point del proceso ``worker`` que se ejecuta
como contenedor separado en docker-compose (ver ADR-0004).

Tareas registradas:
- ``replenishment_task`` — corre como cron cada
  ``settings.replenishment_interval_minutes`` minutos. Detecta stock
  bajo minimo en bodegas auxiliares y crea solicitudes automaticas via
  ``SolicitudService``.
- ``send_email_task`` — consume la cola ``arq:queue`` y envia UN email
  del outbox via SMTP (aiosmtplib). Encolado por
  ``app.modules.notifications.service.NotificationsService.enqueue`` y
  por ``retry_dead`` (uso admin).

Uso local (con Redis corriendo en localhost:6379):
    cd apps/api
    arq app.worker

Produccion (docker-compose):
    command: arq app.worker

Arquitectura:
- R3: este archivo solo ensambla la configuracion de Arq. La logica
  vive en ``ReplenishmentEvaluator`` (modulo de dominio) y
  ``NotificationsService`` (modulo de notificaciones).
- R4: el worker es un proceso aparte del API; no bloquea el startup
  de FastAPI ni comparte event loop.
- ADR-0004: Arq sobre Redis, mismo stack que Fase 7 (SMTP outbox).

Convencion de Arq 0.26+:
    La CLI ``arq app.worker`` importa este modulo y busca el simbolo
    ``WorkerSettings`` (clase con atributos de clase). Luego pasa esa
    clase a ``Worker(**settings.__dict__)`` para instanciar el worker.
    Por eso declaramos ``WorkerSettings`` como clase, no como instancia.
"""
from __future__ import annotations

from arq.connections import RedisSettings, create_pool
from arq.cron import cron

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_session_factory
from app.modules.observability.metrics import (
    update_email_outbox_gauge_from_db,
    update_solicitudes_gauge_from_db,
)
from app.modules.solicitudes.replenishment import ReplenishmentEvaluator


# Configurar logging estructurado (R8). En el entry point de Arq el
# logging debe inicializarse antes de instanciar el worker para que los
# hooks ``on_startup`` / ``on_shutdown`` emitan con structlog.
configure_logging()
log = get_logger(__name__)


# Nombre canonico de la tarea SMTP; usado tanto por el worker como por
# el helper ``enqueue_send_email_task`` que el NotificationsService
# llama al encolar. Constante para evitar typos.
SEND_EMAIL_TASK = "send_email_task"


def _build_cron_minutes(total_minutes: int) -> set[int]:
    """Genera el set de minutos (0-59) para el cron de Arq.

    Acepta intervalos de 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60
    minutos. Si el valor no divide 60 limpiamente, se cae al multiplo
    inferior valido (ej: 7 -> 6 min) y se registra una advertencia.

    Arq no soporta expresiones cron tipo ``*/5``; hay que pasar el set
    completo. Esto se genera una sola vez al instanciar el worker.
    """
    valid_intervals = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60)
    # Encontrar el intervalo valido mas cercano que no supere al pedido
    chosen = max((v for v in valid_intervals if total_minutes >= v), default=5)
    if chosen != total_minutes:
        log.warning(
            "worker.cron_interval_rounded",
            requested_minutes=total_minutes,
            applied_minutes=chosen,
            reason="Arq no soporta intervalos arbitrarios; se redondeo al multiplo inferior valido",
        )
    return {m for m in range(0, 60, chosen)}


# ============================================================== TAREAS (functions)


async def replenishment_task(ctx) -> dict:
    """Tarea cron: detecta stock bajo minimo y crea solicitudes automaticas.

    Args:
        ctx: contexto de Arq (no usado directamente; provee acceso a Redis).

    Returns:
        Dict con metricas de la corrida (lo que Arq guarda en el resultado
        y esta disponible en el dashboard / healthcheck).
    """
    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        evaluator = ReplenishmentEvaluator(session)
        report = await evaluator.evaluate_all()
        # Commit explicito: la transaccion de ``session_factory()`` no
        # hace commit al salir del contexto async (es un async_sessionmaker,
        # no un context manager transaccional).
        await session.commit()

    log.info(
        "worker.replenishment.completed",
        bodegas=report.bodegas_evaluadas,
        skus_bajo_minimo=report.skus_bajo_minimo,
        solicitudes_creadas=report.solicitudes_creadas,
        solicitudes_omitidas=report.solicitudes_omitidas_pendientes,
        errores=len(report.errores),
        dry_run=report.dry_run,
    )
    return {
        "bodegas_evaluadas": report.bodegas_evaluadas,
        "skus_bajo_minimo": report.skus_bajo_minimo,
        "solicitudes_creadas": report.solicitudes_creadas,
        "solicitudes_omitidas_pendientes": report.solicitudes_omitidas_pendientes,
        "errores": report.errores,
        "dry_run": report.dry_run,
        "interval_minutes": settings.replenishment_interval_minutes,
    }


async def send_email_task(ctx, outbox_id: str) -> dict:
    """Tarea Arq: consume UN email del outbox y lo envia via SMTP (Fase 7).

    Llamada por:
    - LPUSH directo desde ``NotificationsService.enqueue()`` (path normal).
    - LPUSH desde ``NotificationsService.retry_dead()`` (uso admin).
    - Re-encolado interno por Arq si el job falla (Arq 0.28 retry builtin;
      aqui lo manejamos manual via ``email_max_attempts`` porque queremos
      distinguir errores permanentes vs transitorios).

    Args:
        ctx: contexto de Arq.
        outbox_id: UUID del row en ``email_outbox`` a procesar.

    Returns:
        Dict con ``status`` (``sent``/``pending``/``dead``) y ``attempts``.
        Arq persiste este dict como resultado del job.
    """
    session_factory = get_session_factory()

    # Import lazy: ``NotificationsService`` vive en
    # ``app.modules.notifications.service``, que NO depende de Arq en
    # modulo level. Importarlo aqui evita cualquier ciclo de imports.
    from app.modules.notifications.service import NotificationsService  # noqa: PLC0415

    async with session_factory() as session:
        service = NotificationsService(session)
        result = await service.process_one(outbox_id)
        await session.commit()

    log.info(
        "worker.send_email.completed",
        outbox_id=outbox_id,
        **result,
    )
    return result


async def update_metrics_task(ctx) -> dict:
    """Tarea Arq: actualiza los Gauges de Prometheus desde la BD (Fase 9).

    Se ejecuta cada minuto (cron). Hace SELECT COUNT(*) en
    ``solicitudes_recarga`` (agrupado por estado) y ``email_outbox``
    (filtrado por status='pending') y actualiza los Gauges.

    Por que un cron y no en cada request:
    - Cardinalidad acotada: 6 estados + 1 count de pending.
    - Evita saturar la BD con COUNT(*) en cada peticion a /metrics
      (Prometheus scrapea cada 15-30s).
    - Los Gauges son "snapshot from BD" — no necesitan real-time.

    Args:
        ctx: contexto de Arq (no usado).

    Returns:
        Dict con las cantidades actualizadas (util para debug via
        ``arq`` CLI o healthcheck de Fase 10+).
    """
    session_factory = get_session_factory()

    # Import lazy: evita ciclo si ``app.modules.observability`` se importa
    # en el path de inicializacion del worker.
    from app.modules.observability.metrics import (  # noqa: PLC0415
        update_email_outbox_gauge_from_db,
        update_solicitudes_gauge_from_db,
    )

    await update_solicitudes_gauge_from_db(session_factory)
    await update_email_outbox_gauge_from_db(session_factory)

    log.info("worker.metrics.updated")
    return {
        "status": "ok",
        "gauges_updated": [
            "solicitudes_por_estado",
            "email_outbox_pending",
        ],
    }


# ============================================================== ENQUEUE HELPER


async def enqueue_send_email_task(outbox_id: str) -> None:
    """Helper: encola ``send_email_task`` en Arq desde codigo de la API.

    Usado por ``NotificationsService.enqueue()`` y ``retry_dead()``.
    Crea un ArqRedis pool efimero (no singleton) para evitar acoplar el
    ciclo de vida del API al del worker: cada enqueue es independiente.

    Si Redis no responde, NO se lanza excepcion: el caller decide si
    hacer rollback o aceptar que el email queda en outbox y sera
    procesado por un mecanismo de recuperacion (cron de retry, no
    implementado en Fase 7).

    Args:
        outbox_id: UUID (str) del row ``email_outbox`` a procesar.
    """
    settings = get_settings()
    redis_settings = RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.redis_db,
    )
    try:
        pool = await create_pool(redis_settings)
        try:
            await pool.enqueue_job(SEND_EMAIL_TASK, outbox_id)
        finally:
            await pool.aclose()  # redis 5.0+; ``close()`` esta deprecado
        log.debug("worker.enqueue_send_email.ok", outbox_id=outbox_id)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "worker.enqueue_send_email.failed",
            outbox_id=outbox_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


# ============================================================== HOOKS DEL WORKER


async def startup(ctx) -> None:
    """Hook invocado por Arq al arrancar el worker."""
    log.info("worker.startup", tasks=["replenishment_task", SEND_EMAIL_TASK])


async def shutdown(ctx) -> None:
    """Hook invocado por Arq al detener el worker (SIGTERM/SIGINT)."""
    log.info("worker.shutdown")


# ============================================================== SETTINGS (Arq)


def _build_settings_dict() -> dict:
    """Construye el dict de settings que Arq consume via ``WorkerSettings``.

    Separado en una funcion para que tests puedan llamar a
    ``get_worker_settings()`` y forzar reconfiguracion (con mocks del
    Settings) sin tener que reimportar el modulo.
    """
    settings = get_settings()
    cron_minutes = _build_cron_minutes(settings.replenishment_interval_minutes)
    log.info(
        "worker.configured",
        redis_host=settings.redis_host,
        redis_port=settings.redis_port,
        redis_db=settings.redis_db,
        cron_minutes=sorted(cron_minutes),
        tasks=["replenishment_task", SEND_EMAIL_TASK],
    )
    return {
        "redis_settings": RedisSettings(
            host=settings.redis_host,
            port=settings.redis_port,
            database=settings.redis_db,
        ),
        "functions": [replenishment_task, send_email_task, update_metrics_task],
        "cron_jobs": [
            cron(
                replenishment_task,
                minute=cron_minutes,
                run_at_startup=False,
            ),
            # Fase 9: actualizacion de Gauges Prometheus cada 1 minuto.
            # Usamos un set explicito (no ``*/1``) para mantener consistencia
            # con el patron de Arq (set completo, no expressions).
            cron(
                update_metrics_task,
                minute=set(range(0, 60)),
                run_at_startup=True,  # una vez al arrancar, asi /metrics tiene data
            ),
        ],
        "on_startup": startup,
        "on_shutdown": shutdown,
        # Mantenemos el resultado de la ultima corrida por 1h para
        # que el endpoint de healthcheck pueda reportar el ultimo
        # estado (Fase 9 lo conectara a /health).
        "keep_result": 60 * 60,
        "max_jobs": settings.worker_max_jobs,
    }


# Arq 0.26 espera una CLASE con los settings como atributos de clase.
# La CLI hace ``Worker(**WorkerSettings.__dict__)`` para instanciar.
# Por lo tanto, no instanciamos: dejamos los valores en el __dict__
# de la clase via la metaclase-style de Python (dict spread).
class WorkerSettings:
    """Configuracion del worker Arq (Fase 4 + Fase 7).

    Los atributos de clase se copian al instanciar ``Worker`` (Arq
    hace ``Worker(**WorkerSettings.__dict__)``). Se computan en el
    cuerpo de la clase para que esten disponibles en cuanto Arq importa
    el modulo.
    """

    _settings: dict = _build_settings_dict()

    def __init_subclass__(cls, **kwargs) -> None:  # pragma: no cover
        super().__init_subclass__(**kwargs)

    # Atributos que Arq consume (ver ``arq/worker.py:Worker.__init__``).
    redis_settings = _settings["redis_settings"]
    functions = _settings["functions"]
    cron_jobs = _settings["cron_jobs"]
    on_startup = _settings["on_startup"]
    on_shutdown = _settings["on_shutdown"]
    keep_result = _settings["keep_result"]
    max_jobs = _settings["max_jobs"]


def get_worker_settings() -> dict:
    """Retorna el dict de settings. Util para tests y healthchecks.

    No retorna una instancia: Arq 0.26 internamente acepta un dict O
    una clase con atributos. Tests pueden invocar esta funcion y
    manipular el dict resultante.
    """
    return _build_settings_dict()
