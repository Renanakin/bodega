"""Rate limiter in-memory por IP (Fase 6).

Decisiones:
- Sin dependencia externa (slowapi NO esta en requirements).
- Dict { (ip, scope) -> [timestamps] } en memoria, suficiente para MVP.
- Scope es una clave arbitraria (e.g. "public_oc", "internal") para tener
  distintos limites por grupo de endpoints.
- IP detection: prefiere X-Forwarded-For (primera IP), fallback a
  `request.client.host`.

Regla de oro aplicada:
- R4: solo infrastructura, sin logica de negocio.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass(slots=True)
class RateLimitResult:
    """Resultado de check_rate_limit()."""

    allowed: bool
    retry_after_seconds: int  # >0 si no esta permitido
    remaining: int  # requests restantes en la ventana actual


class RateLimiter:
    """Sliding-window in-memory rate limiter por (ip, scope).

    Mantiene un deque de timestamps por (ip, scope). Una request se
    permite si hay menos de `max_requests` timestamps en los ultimos
    `window_seconds` segundos.
    """

    def __init__(self) -> None:
        # (ip, scope) -> deque[timestamp_float]
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(
        self,
        ip: str,
        scope: str,
        max_requests: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Verifica si la IP puede hacer otra request en el scope dado."""
        now = time.monotonic()
        cutoff = now - window_seconds
        bucket = self._buckets[(ip, scope)]

        # Descartar timestamps fuera de la ventana
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_requests:
            retry_after = max(1, int(bucket[0] + window_seconds - now) + 1)
            return RateLimitResult(
                allowed=False,
                retry_after_seconds=retry_after,
                remaining=0,
            )

        bucket.append(now)
        return RateLimitResult(
            allowed=True,
            retry_after_seconds=0,
            remaining=max_requests - len(bucket),
        )

    def clear(self) -> None:
        """Limpia todos los buckets. Util en tests."""
        self._buckets.clear()


# Singleton compartido
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Retorna el singleton del rate limiter."""
    return _rate_limiter


def reset_rate_limiter_for_tests() -> None:
    """Limpia el estado del rate limiter. Solo para tests."""
    _rate_limiter.clear()


def _extract_client_ip(request: Request) -> str:
    """Extrae la IP del cliente respetando X-Forwarded-For (primera IP)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def rate_limit_dependency(
    scope: str,
    max_requests: int,
    window_seconds: int,
) -> Callable:
    """Factory de dependencies de FastAPI para rate limiting.

    Uso:
        @router.get("/foo")
        async def foo(request: Request, _=Depends(rate_limit_dependency(
            scope="public_oc", max_requests=5, window_seconds=60,
        ))):
            ...
    """
    limiter = _rate_limiter

    def _dependency(request: Request) -> None:
        ip = _extract_client_ip(request)
        result = limiter.check(
            ip=ip,
            scope=scope,
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": (
                        f"Demasiadas solicitudes. Intente de nuevo en "
                        f"{result.retry_after_seconds}s."
                    ),
                    "extra": {"retry_after": result.retry_after_seconds},
                },
                headers={"Retry-After": str(result.retry_after_seconds)},
            )
        request.state.rate_limit_remaining = result.remaining

    return _dependency
