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
        """Verifica si la IP puede hacer otra request en el scope dado.

        C5.2: para ``/auth/login`` y ``/auth/refresh`` usamos el ``username``
        como key (no la IP). Esto mitiga el caso de un atacante con muchas
        IPs (botnet) atacando un usuario especifico. Ver
        ``auth_login_rate_limit_dependency`` en ``app/modules/auth/router.py``.
        """
        return self._check_bucket(
            bucket_key=(ip, scope),
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

    def check_by_key(
        self,
        key: str,
        scope: str,
        max_requests: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """C5.2: variante donde la key NO es la IP (ej: username, token).

        Usado por /auth/login y /auth/refresh para limitar por usuario
        y no por IP. Ver auth_login_rate_limit_dependency.
        """
        return self._check_bucket(
            bucket_key=(key, scope),
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

    def _check_bucket(
        self,
        bucket_key: tuple[str, str],
        max_requests: int,
        window_seconds: int,
    ) -> RateLimitResult:
        now = time.monotonic()
        cutoff = now - window_seconds
        bucket = self._buckets[bucket_key]

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


def rate_limit_by_key_dependency(
    scope: str,
    max_requests: int,
    window_seconds: int,
    key_extractor: Callable[[Request], str | None],
) -> Callable:
    """C5.2: factory de dependencies con key arbitraria (no IP).

    A diferencia de ``rate_limit_dependency`` (que usa la IP del cliente),
    esta variante deja que el caller extraiga la key del request. Usado
    para limitar por ``username`` en ``/auth/login`` y por ``refresh_token``
    en ``/auth/refresh``.

    Args:
        scope: nombre del bucket (ej: "auth_login", "auth_refresh").
        max_requests: requests permitidas en la ventana.
        window_seconds: tamano de la ventana.
        key_extractor: callable sync o async que toma el Request y
            devuelve la key (o None si no se puede extraer; en ese caso
            la request se permite sin rate-limit).

    Uso:
        async def _key_by_username(request: Request) -> str | None:
            body = await request.json()
            return body.get("username", "").lower().strip()

        @router.post("/auth/login")
        async def login(
            request: Request,
            _=Depends(rate_limit_by_key_dependency(
                scope="auth_login",
                max_requests=5,
                window_seconds=60,
                key_extractor=_key_by_username,
            )),
        ):
            ...
    """
    limiter = _rate_limiter

    async def _dependency(request: Request) -> None:
        # La key_extractor es siempre async (definido en el router con
        # ``async def``). El check via co_flags es fragil en Python 3.14+
        # donde las flags cambiaron, asi que simplemente intentamos await.
        try:
            key = await key_extractor(request)
        except TypeError:
            # Si por error el caller definio un extractor sync
            key = key_extractor(request)
        if not key:
            return
        result = limiter.check_by_key(
            key=key,
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
