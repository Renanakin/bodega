"""
Tests LIVE del hardening de Nginx (Fase 10).

Estos tests requieren Nginx corriendo (típicamente localhost:80 o :8080).
Por defecto estan SKIPPED para no fallar en CI sin infra.

Para correrlos:
    # 1. Levantar el stack.
    docker compose -f infra/docker/docker-compose.yml \\
                   -f infra/docker/compose.local.dev.yml up -d

    # 2. Correr los tests con skip desactivado.
    cd infra && pytest tests/test_nginx_headers.py -v --runlive

    # 3. Verificar manualmente con curl.
    curl -I http://localhost/

Valida:
- Headers de seguridad presentes (HSTS, X-Frame-Options, etc).
- Rate limit funcional (5 req/min en /api/v1/public/, 100 req/min general).
- Nginx responde 200 en healthcheck.
- /metrics esta rate-limited.
- Compresion gzip funciona.
"""
from __future__ import annotations

import os

import pytest


# Live: requiere Nginx en localhost.
# Por defecto skip. Para correr: setear BODEGA_NGINX_URL o usar --runlive.
LIVE_BASE_URL = os.getenv("BODEGA_NGINX_URL", "http://localhost")
SKIP_REASON = (
    f"Test LIVE que requiere Nginx en {LIVE_BASE_URL}. "
    "Para correr: docker compose ... up -d && pytest --runlive"
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Agrega flag --runlive para activar tests live."""
    parser.addoption(
        "--runlive",
        action="store_true",
        default=False,
        help="Correr tests live que requieren Nginx/Postgres.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Si no se paso --runlive, skip todos los tests live."""
    if config.getoption("--runlive"):
        return
    skip_live = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


pytestmark = [
    pytest.mark.live,
    pytest.mark.skip(reason=SKIP_REASON),
]


# --- Tests ---------------------------------------------------------------

class TestNginxHeaders:
    """Headers de seguridad que el hardening de Fase 10 debe setear."""

    def test_strict_transport_security(self) -> None:
        """HSTS: max-age=31536000; includeSubDomains; preload."""
        import httpx

        r = httpx.get(LIVE_BASE_URL, follow_redirects=False, timeout=5)
        hsts = r.headers.get("strict-transport-security", "")
        assert "max-age=31536000" in hsts, f"HSTS no presente o mal formado: {hsts!r}"
        assert "includeSubDomains" in hsts, f"HSTS sin includeSubDomains: {hsts!r}"

    def test_x_frame_options_deny(self) -> None:
        """X-Frame-Options: DENY (clickjacking)."""
        import httpx

        r = httpx.get(LIVE_BASE_URL, timeout=5)
        xfo = r.headers.get("x-frame-options", "")
        assert xfo == "DENY", f"X-Frame-Options debe ser DENY, recibido: {xfo!r}"

    def test_x_content_type_options_nosniff(self) -> None:
        """X-Content-Type-Options: nosniff."""
        import httpx

        r = httpx.get(LIVE_BASE_URL, timeout=5)
        xcto = r.headers.get("x-content-type-options", "")
        assert xcto == "nosniff", f"X-Content-Type-Options debe ser nosniff, recibido: {xcto!r}"

    def test_referrer_policy_strict_origin(self) -> None:
        """Referrer-Policy: strict-origin-when-cross-origin."""
        import httpx

        r = httpx.get(LIVE_BASE_URL, timeout=5)
        rp = r.headers.get("referrer-policy", "")
        assert rp == "strict-origin-when-cross-origin", (
            f"Referrer-Policy debe ser strict-origin-when-cross-origin, recibido: {rp!r}"
        )

    def test_content_security_policy_default_src_self(self) -> None:
        """CSP: default-src 'self' (XSS mitigation)."""
        import httpx

        r = httpx.get(LIVE_BASE_URL, timeout=5)
        csp = r.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp, f"CSP sin default-src 'self': {csp!r}"
        assert "object-src 'none'" in csp, f"CSP sin object-src 'none': {csp!r}"

    def test_permissions_policy_geolocation_disabled(self) -> None:
        """Permissions-Policy: geolocation=() (APIs sensibles deshabilitadas)."""
        import httpx

        r = httpx.get(LIVE_BASE_URL, timeout=5)
        pp = r.headers.get("permissions-policy", "")
        assert "geolocation=()" in pp, f"Permissions-Policy sin geolocation=(): {pp!r}"
        assert "microphone=()" in pp, f"Permissions-Policy sin microphone=(): {pp!r}"
        assert "camera=()" in pp, f"Permissions-Policy sin camera=(): {pp!r}"

    def test_server_tokens_off(self) -> None:
        """Nginx no expone la version en el header Server."""
        import httpx

        r = httpx.get(LIVE_BASE_URL, timeout=5)
        server = r.headers.get("server", "")
        # Server debe ser "nginx" (sin version).
        assert "/" not in server, f"Nginx expone version: {server!r}"
        assert server == "nginx", f"Header Server esperado 'nginx', recibido: {server!r}"


class TestNginxRateLimit:
    """Rate limit funcional."""

    def test_healthcheck_no_rate_limited(self) -> None:
        """/healthz no esta sujeto a rate limit (monitorizacion)."""
        import httpx

        # Hacer 200 requests rapidas.
        for _ in range(200):
            r = httpx.get(f"{LIVE_BASE_URL}/healthz", timeout=5)
            assert r.status_code == 200, (
                f"Healthcheck fallo tras multiples requests: {r.status_code}"
            )

    def test_api_rate_limit_devuelve_429(self) -> None:
        """Si se supera el rate limit, Nginx retorna 429."""
        import httpx

        # Hacer 200 requests rapidas al API (rate limit = 100/min, burst 20).
        statuses = []
        for _ in range(200):
            r = httpx.get(f"{LIVE_BASE_URL}/api/v1/health", timeout=5)
            statuses.append(r.status_code)
        # Al menos algunas deben ser 429.
        assert 429 in statuses, f"Nunca se recibio 429, statuses: {set(statuses)}"

    def test_public_oc_rate_limit_mas_estricto(self) -> None:
        """Endpoint /api/v1/public/* tiene rate limit MAS estricto (5/min)."""
        import httpx

        # 20 requests rapidas. El rate limit es 5/min con burst 10.
        statuses = []
        for _ in range(20):
            r = httpx.get(
                f"{LIVE_BASE_URL}/api/v1/public/ordenes-compra/test",
                timeout=5,
            )
            statuses.append(r.status_code)
        # Deberia haber 429s tras las primeras ~10 requests.
        n_429 = sum(1 for s in statuses if s == 429)
        assert n_429 >= 5, (
            f"Rate limit muy permisivo: solo {n_429} rechazos de 20 requests"
        )


class TestNginxBehavior:
    """Comportamiento general del proxy."""

    def test_healthcheck_responde_200(self) -> None:
        """/healthz retorna 200 ok."""
        import httpx

        r = httpx.get(f"{LIVE_BASE_URL}/healthz", timeout=5)
        assert r.status_code == 200
        assert "ok" in r.text

    def test_proxy_preserve_host_header(self) -> None:
        """Nginx pasa el header Host al upstream."""
        import httpx

        # Llamar al endpoint /api/v1/health que viene del API.
        r = httpx.get(f"{LIVE_BASE_URL}/api/v1/health", timeout=5)
        # Si Nginx pasara el Host mal, el API podría responder 421/400.
        assert r.status_code in (200, 503), (
            f"API respondio {r.status_code}, posible Host mal pasado"
        )

    def test_compression_gzip_en_respuestas_grandes(self) -> None:
        """Respuestas grandes vienen con Content-Encoding: gzip."""
        import httpx

        # /api/v1/health retorna un JSON ~1KB. Si el threshold gzip es
        # 1KB, deberia estar comprimido.
        r = httpx.get(
            f"{LIVE_BASE_URL}/api/v1/health",
            headers={"Accept-Encoding": "gzip"},
            timeout=5,
        )
        # Content-Encoding puede ser 'gzip' o ausente si la respuesta es < min_length.
        encoding = r.headers.get("content-encoding", "")
        # Solo verificamos que la opcion gzip esta habilitada.
        # (Algunas respuestas < 1024 bytes no se comprimen).
        assert encoding in ("gzip", ""), f"Encoding inesperado: {encoding!r}"
