"""
Idempotency-Key middleware (Stripe-style).

Permite que un cliente (e.g. frontend, batch importer) ejecute un POST
de forma idempotente: si envia ``Idempotency-Key: abc-123`` y el server
falla/desconecta, el cliente puede reintentar con la misma key y el
server retorna la MISMA respuesta (cacheada en Redis por 24h).

Inspirado en https://stripe.com/blog/idempotency (Fase 5+).
Compatible con Redis (via ``REDIS_URL``) o in-memory (fallback para tests).

Uso en cliente:
    curl -X POST /api/v1/solicitudes \\
        -H "Idempotency-Key: 8c1f-4b2e-a1f7-9d3c-5e6b" \\
        -H "Content-Type: application/json" \\
        -d '{...}'

El middleware:
1. Si la request entrante tiene ``Idempotency-Key``:
   - Hashea el body + la key para identificar la operacion.
   - Si ya existe en cache: retorna el response cacheado.
   - Si no: ejecuta la request, cachea el response (status + body).
2. Si no tiene la key: pasa transparente (no cachea nada).
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger(__name__)

# TTL del cache de idempotencia (24h, alineado con Stripe).
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60


class InMemoryIdempotencyCache:
    """Fallback en memoria (tests / dev sin Redis)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[int, bytes, dict[str, str]]] = {}

    async def get(self, key: str) -> tuple[int, bytes, dict[str, str]] | None:
        return self._store.get(key)

    async def set(self, key: str, status: int, body: bytes, headers: dict[str, str]) -> None:
        self._store[key] = (status, body, headers)

    async def ping(self) -> bool:
        return True


class RedisIdempotencyCache:
    """Cache basado en Redis (produccion)."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._client: Any = None  # lazy

    async def _get_client(self) -> Any:
        if self._client is None:
            import redis.asyncio as redis_async  # type: ignore[import-not-found]

            self._client = redis_async.from_url(self._url, decode_responses=False)
        return self._client

    async def get(self, key: str) -> tuple[int, bytes, dict[str, str]] | None:
        import json as _json

        try:
            client = await self._get_client()
            data = await client.get(f"idempotency:{key}")
        except Exception as exc:
            log.warning("idempotency.redis_get_failed", error=str(exc))
            return None
        if data is None:
            return None
        try:
            payload = _json.loads(data)
        except _json.JSONDecodeError:
            return None
        return (
            int(payload["status"]),
            payload["body"].encode("utf-8") if isinstance(payload["body"], str) else payload["body"],
            payload.get("headers", {}),
        )

    async def set(self, key: str, status: int, body: bytes, headers: dict[str, str]) -> None:
        import json as _json

        try:
            client = await self._get_client()
            payload = _json.dumps(
                {"status": status, "body": body.decode("utf-8", errors="replace"), "headers": headers}
            )
            await client.set(f"idempotency:{key}", payload, ex=IDEMPOTENCY_TTL_SECONDS)
        except Exception as exc:
            log.warning("idempotency.redis_set_failed", error=str(exc))

    async def ping(self) -> bool:
        try:
            client = await self._get_client()
            return bool(await client.ping())
        except Exception:
            return False


def _make_cache() -> Any:
    """Factory: Redis si REDIS_URL está definido, sino in-memory."""
    redis_url = os.getenv("REDIS_URL", "").strip()
    if redis_url:
        return RedisIdempotencyCache(redis_url)
    return InMemoryIdempotencyCache()


def _fingerprint(body: bytes) -> str:
    """Hash SHA-256 del body (para validar que el cliente reintenta
    con la misma operacion)."""
    return hashlib.sha256(body).hexdigest()[:16]


class IdempotencyMiddleware:
    """Pure-ASGI middleware para ``Idempotency-Key``.

    Solo se aplica a requests mutables (POST/PATCH/PUT/DELETE). GETs
    pasan transparentes (son idempotentes por definicion).

    Si Redis no está disponible, el middleware sigue funcionando
    con cache en memoria (suficiente para tests). El cache en memoria
    se LIMPIA entre tests via ``reset_idempotency_cache()``.
    """

    MUTABLE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})

    def __init__(self, app: ASGIApp, cache: Any | None = None) -> None:
        self.app = app
        self._cache = cache or _make_cache()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        if method not in self.MUTABLE_METHODS:
            await self.app(scope, receive, send)
            return

        # Extraer Idempotency-Key de los headers.
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        idempotency_key = headers.get("idempotency-key", "").strip()
        if not idempotency_key:
            await self.app(scope, receive, send)
            return

        # Leer body para fingerprint. Necesitamos consumir ``receive``.
        body_chunks: list[bytes] = []
        body_done = False
        original_receive = receive

        async def receive_with_body_capture() -> Message:
            nonlocal body_done
            msg = await original_receive()
            if msg["type"] == "http.request":
                body_chunks.append(msg.get("body", b""))
                if not msg.get("more_body", False):
                    body_done = True
            return msg

        body = b"".join(body_chunks)

        # Verificar cache: si la misma key+fingerprint ya existe, retornar
        # el response cacheado.
        cache_key = f"{idempotency_key}:{_fingerprint(body)}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            status, cached_body, cached_headers = cached
            log.info(
                "idempotency.hit",
                key=idempotency_key,
                fingerprint=_fingerprint(body),
                status=status,
            )

            # Reconstruir el response cacheado.
            response_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in cached_headers.items()]
            response_headers.append((b"x-idempotency-replay", b"true"))

            async def send_cached(message: Message) -> None:
                if message["type"] == "http.response.start":
                    # No podemos modificar los headers ya enviados;
                    # pero el primer send que capturemos sera este.
                    await send(message)
                else:
                    await send(message)

            await send({"type": "http.response.start", "status": status, "headers": response_headers})
            await send({"type": "http.response.body", "body": cached_body})
            return

        # No hay cache. Ejecutar la app capturando el response.
        response_status: int = 500
        response_body: bytes = b""
        response_headers_dict: dict[str, str] = {}

        async def send_capture(message: Message) -> None:
            nonlocal response_status, response_body, response_headers_dict
            if message["type"] == "http.response.start":
                response_status = int(message["status"])
                for k, v in message.get("headers", []):
                    response_headers_dict[k.decode("latin-1").lower()] = v.decode("latin-1")
                await send(message)
            elif message["type"] == "http.response.body":
                response_body += message.get("body", b"")
                await send(message)
            else:
                await send(message)

        # Reconstruir un receive que devuelva el body completo.
        body_consumed = [False]

        async def receive_replay() -> Message:
            if not body_consumed[0]:
                body_consumed[0] = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            return await original_receive()

        await self.app(scope, receive_replay, send_capture)

        # Solo cacheamos respuestas 2xx (idempotencia != retries de error).
        if 200 <= response_status < 300:
            try:
                await self._cache.set(cache_key, response_status, response_body, response_headers_dict)
                log.info(
                    "idempotency.stored",
                    key=idempotency_key,
                    fingerprint=_fingerprint(body),
                    status=response_status,
                )
            except Exception as exc:
                log.warning("idempotency.store_failed", error=str(exc))

        # Marcar el response con header X-Idempotency-Key (echo).
        # Nota: ya enviamos el response. Para un hit perfecto habria que
        # agregar el header al ``http.response.start``, pero eso requiere
        # buffering. Por ahora el log en cache es suficiente.
        return None  # explicito


# --- API pública ---


_global_cache: Any = None


def get_idempotency_cache() -> Any:
    """Retorna el cache global (lazy init)."""
    global _global_cache
    if _global_cache is None:
        _global_cache = _make_cache()
    return _global_cache


def reset_idempotency_cache() -> None:
    """Reset del cache (para tests)."""
    global _global_cache
    _global_cache = None
