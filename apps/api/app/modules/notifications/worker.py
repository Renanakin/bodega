"""
Worker standalone para envio de emails (DEPRECATED, Fase 7).

.. deprecated::
    Este script esta deprecado desde Fase 7 (ADR-0004). Usar Arq:
    ``arq apps.api.app.worker.WorkerSettings``

    La forma canonica es el worker Arq declarado en ``app/worker.py``
    (registra ``send_email_task`` ademas de ``replenishment_task``). El
    cron de Arq reemplaza el loop ``while _running: ...`` de este script.

    Motivo del deprecation:
    - Pierde tareas si el proceso muere entre ``BLPOP`` y el commit.
    - No tiene reintentos con backoff (lo maneja ``process_one`` recien,
      pero este script le pasa el lote y nunca se re-llama solo).
    - Dificulta el escalado horizontal (varios procesos compiten por el
      mismo pool de emails sin lock atomico).

    Se mantiene por 1 release para facilitar migracion; sera removido
    en Fase 8.
"""
from __future__ import annotations

import asyncio
import signal
import sys
import warnings
from pathlib import Path

# Emitir warning al importar.
warnings.warn(
    "app.modules.notifications.worker esta deprecado desde Fase 7. "
    "Usar Arq: `arq apps.api.app.worker.WorkerSettings`",
    DeprecationWarning,
    stacklevel=2,
)

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.modules.notifications.service import NotificationsService  # noqa: E402


configure_logging()
log = get_logger(__name__)


_running = True


def _signal_handler(_sig, _frame):
    global _running
    _running = False
    log.info("worker.shutdown_requested")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


async def main_loop() -> None:
    settings = get_settings()
    interval = 30  # seconds
    log.info(
        "worker.deprecated_start",
        interval_seconds=interval,
        environment=settings.environment,
        note="DEPRECATED: usar Arq via `arq apps.api.app.worker.WorkerSettings`",
    )

    factory = get_session_factory()
    while _running:
        async with factory() as session:
            service = NotificationsService(session)
            try:
                stats = await service.process_pending(batch_size=20)
                if stats["sent"] or stats["failed"] or stats["retried"]:
                    log.info("worker.batch_complete", **stats)
            except Exception as e:  # noqa: BLE001
                log.error("worker.batch_error", error=str(e))
        await asyncio.sleep(interval)

    log.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(main_loop())
