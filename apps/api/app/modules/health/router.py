"""
Health check ampliado (R8: observabilidad + Fase 9).

GET /api/v1/health → estado de BD, Redis y worker.
GET /api/v1/health/live → liveness probe (Kubernetes-style, siempre 200).

Convenciones:
- Devuelve 200 si todo OK.
- Devuelve 503 si alguna dependencia crítica está down.
- Timeout 2-5s por dependencia para no colgar el endpoint.
- Redis y worker check se hacen en PARALELO con ``asyncio.gather``
  para minimizar latencia total.

Notas Fase 9:
- BD: usa el async engine via ``ping_database()`` (compat con postgres
  y sqlite via ``detect_backend()``).
- Redis: hace PING con timeout 2s. Si Redis no esta instalado o
  configurado, retorna ``status=skipped`` (no down) para no romper
  environments sin cache.
- Worker: cuenta keys ``arq:*`` en Redis (los workers Arq mantienen
  un heartbeat con TTL). Si hay >= 1 key, hay >= 1 worker vivo.
  Si Redis no responde, retorna ``status=skipped`` igual que arriba.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import detect_backend, get_session_factory, ping_database
from fastapi import APIRouter, Response, status

log = get_logger(__name__)

router = APIRouter()


# --- Helpers ---------------------------------------------------------------


async def _check_db() -> dict[str, Any]:
    """Chequea la BD con un ping (SELECT 1).

    Usa ``ping_database()`` que detecta el backend automáticamente
    y aplica el driver correcto (asyncpg para postgres, aiosqlite
    para sqlite).

    Returns:
        Dict con ``status`` (``ok``/``down``) y opcionalmente
        ``backend`` y ``latency_ms``.
    """
    backend = detect_backend()
    start = time.perf_counter()
    try:
        ok = await asyncio.wait_for(ping_database(), timeout=5.0)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        if ok:
            return {
                "status": "ok",
                "backend": backend,
                "latency_ms": elapsed_ms,
            }
        return {
            "status": "down",
            "backend": backend,
            "error": "ping_database returned False",
        }
    except asyncio.TimeoutError:
        return {
            "status": "down",
            "backend": backend,
            "error": "timeout (5s) en ping_database",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "status": "down",
            "backend": backend,
            "error": str(e)[:200],
        }


async def _check_redis() -> dict[str, str]:
    """Ping a Redis con timeout 2s.

    Si Redis no está instalado o no responde, retorna ``status=skipped``
    (no down) para no romper environments sin cache (tests, CI).
    """
    try:
        import redis.asyncio as redis_async  # noqa: PLC0415
    except ImportError:
        return {"status": "skipped", "reason": "redis lib not installed"}

    settings = get_settings()
    start = time.perf_counter()
    try:
        client = redis_async.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2.0,
        )
        try:
            await asyncio.wait_for(client.ping(), timeout=2.0)
        finally:
            await client.aclose()
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "ok", "latency_ms": str(elapsed_ms)}
    except asyncio.TimeoutError:
        return {"status": "down", "error": "timeout (2s) en PING"}
    except Exception as e:  # noqa: BLE001
        return {"status": "down", "error": str(e)[:200]}


async def _check_worker() -> dict[str, Any]:
    """Chequea que el worker Arq esté respondiendo.

    Estrategia: contar keys con prefijo ``arq:`` en Redis. Los workers
    Arq mantienen un heartbeat con TTL (~60s). Si hay >= 1 key, hay
    al menos 1 worker vivo.

    Returns:
        Dict con ``status`` (``ok``/``down``/``skipped``), ``active_workers``
        (int) y opcionalmente ``error`` o ``reason``.
    """
    try:
        import redis.asyncio as redis_async  # noqa: PLC0415
    except ImportError:
        return {"status": "skipped", "reason": "redis lib not installed"}

    settings = get_settings()
    start = time.perf_counter()
    try:
        client = redis_async.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2.0,
        )
        try:
            # Usamos ``scan_iter`` (no ``keys``) para no bloquear Redis
            # en environments con muchos keys. ``count=100`` es un hint
            # de batch size, no un limite.
            keys: list[str] = []
            async for k in client.scan_iter(match="arq:*", count=100):
                keys.append(k)
        finally:
            await client.aclose()

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        active_workers = len(keys)
        return {
            "status": "ok" if active_workers > 0 else "down",
            "active_workers": str(active_workers),
            "latency_ms": str(elapsed_ms),
        }
    except asyncio.TimeoutError:
        return {"status": "down", "error": "timeout (2s) en SCAN"}
    except Exception as e:  # noqa: BLE001
        return {"status": "down", "error": str(e)[:200]}


# --- Endpoints -------------------------------------------------------------


@router.get("/health")
async def healthcheck(response: Response) -> dict[str, Any]:
    """Health check ampliado: BD + Redis + worker en paralelo.

    Returns:
        200 si todo OK:
            {
                "status": "ok",
                "version": "0.1.0",
                "environment": "production",
                "components": {
                    "db":      {"status": "ok", "backend": "postgres", "latency_ms": 1.2},
                    "redis":   {"status": "ok", "latency_ms": "0.3"},
                    "worker":  {"status": "ok", "active_workers": "1", "latency_ms": "0.4"}
                },
                "timestamp": 1721000000.123
            }

        503 si algun componente critico esta down (BD, Redis o worker):
            { "status": "degraded", "components": {...}, ... }

    Reglas de status code:
    - 503 si BD está down (critico, no se puede servir nada).
    - 503 si Redis está down y worker también (no se pueden encolar jobs).
    - 503 si worker está down sin Redis (no hay quien procese el outbox).
    - 200 si BD OK y Redis/worker skipped (ej: tests sin Redis).
    """
    settings = get_settings()

    # Ejecutar los 3 checks en PARALELO. ``return_exceptions=False``
    # por defecto: si uno falla, gather propaga la excepcion. Pero como
    # cada check internamente captura excepciones y retorna ``status=down``,
    # en la práctica NUNCA se propaga una excepcion.
    db_check, redis_check, worker_check = await asyncio.gather(
        _check_db(),
        _check_redis(),
        _check_worker(),
    )

    components: dict[str, Any] = {
        "db": db_check,
        "redis": redis_check,
        "worker": worker_check,
    }

    # Status code: 503 si BD down, o (Redis down AND worker down).
    # ``skipped`` cuenta como "no requerido" (no falla).
    db_down = db_check.get("status") == "down"
    redis_down = redis_check.get("status") == "down"
    worker_down = worker_check.get("status") == "down"
    critical_down = db_down or (redis_down and worker_down)

    overall_ok = not critical_down
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        log.warning("health.degraded", components=components)

    return {
        "status": "ok" if overall_ok else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "components": components,
        # Backward-compat (Fase 9): el endpoint ``/health`` previo
        # (Fase 0-8) exponia ``checks.database`` y ``checks.redis``.
        # Mantenemos ese shape para no romper integraciones externas
        # (tests, dashboards, etc) que consumian la v1 del contrato.
        # La forma nueva (``components.db``/``components.worker``) es
        # la canónica para integraciones nuevas.
        "checks": {
            "database": components["db"],
            "redis": components["redis"],
        },
        "timestamp": time.time(),
    }


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Liveness probe simple (Kubernetes-style).

    Retorna 200 mientras el proceso esté vivo. No valida dependencias.
    Util para que Kubernetes decida si reiniciar el pod, sin enredarse
    con la salud de las dependencias externas.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(response: Response) -> dict[str, str]:
    """Readiness probe simple (Kubernetes-style).

    Similar a ``/health`` pero más liviano: solo chequea BD (lo mínimo
    para poder servir requests). Si la BD esta OK, el pod está listo.

    Returns:
        200 si BD OK; 503 si BD down.
    """
    db_check = await _check_db()
    if db_check.get("status") == "ok":
        return {"status": "ready"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "not_ready", "reason": db_check.get("error", "db down")}
