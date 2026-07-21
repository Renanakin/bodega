"""Renderizado de plantillas HTML para emails (Fase 7, ADR-0004).

Stack:
- Jinja2 (sync) — el renderizado es CPU-bound y rapido, no necesita async.
- FileSystemLoader apuntando a ``apps/api/app/modules/notifications/templates/``.
- ``premailer`` se aplica a la salida para forzar CSS inline (los clientes
  de email como Outlook ignoran `<style>` en `<head>`).

Reglas:
- R3: ruta obvia (``notifications/templates.py``) — unico punto de render.
- R4: zero logica de negocio, solo presentacion.
- R6: el cache de Jinja2 es por instancia (FileSystemLoader cachea
  internamente los templates; no hace falta memoizar).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from app.core.logging import get_logger
from jinja2 import Environment, FileSystemLoader, select_autoescape

log = get_logger(__name__)

# Path absoluto al directorio de plantillas, relativo a este archivo.
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=1)
def _get_environment() -> Environment:
    """Crea (y cachea) el entorno Jinja2 con FileSystemLoader."""
    if not TEMPLATES_DIR.exists():
        # Tolerancia: si el dir no existe (build minimo), usamos un dir vacio.
        # El primer render fallara con TemplateNotFound, que es descriptivo.
        log.warning("notifications.templates_dir_missing", path=str(TEMPLATES_DIR))
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# Regex para colapsar whitespace sobrante (linebreaks, tabs, multiples
# espacios) que Jinja2 a veces deja entre tags cuando los bloques tienen
# `trim_blocks=True` pero aun asi se filtra HTML/espacios en blanco.
_WHITESPACE_BETWEEN_TAGS = re.compile(r">\s+<")
_MULTI_NEWLINES = re.compile(r"\n\s*\n+")


def render_template(template_name: str, context: dict) -> str:
    """Renderiza una plantilla del directorio ``templates/``.

    Args:
        template_name: nombre del archivo (ej. ``orden_compra.html.j2``).
        context: dict de variables para el template.

    Returns:
        HTML renderizado como ``str``.

    Raises:
        jinja2.TemplateNotFound: si la plantilla no existe.
    """
    env = _get_environment()
    template = env.get_template(template_name)
    html = template.render(**context)
    # Colapsar espacios entre tags >...<  (cosmetic; mejora deliverability
    # en clientes como Outlook que renderizan previews).
    html = _WHITESPACE_BETWEEN_TAGS.sub("><", html)
    html = _MULTI_NEWLINES.sub("\n", html)
    return html.strip()


def render_with_inline_css(
    template_name: str,
    context: dict,
) -> str:
    """Renderiza plantilla y aplica CSS inline via premailer.

    premailer toma el HTML renderizado (con bloque ``<style>`` en head)
    y mueve las reglas a atributos ``style=""`` en cada elemento.
    Esto es lo que MAIL clients (Outlook, Gmail, Apple Mail) esperan
    para respetar el styling.

    Si premailer no esta instalado o falla, retorna el HTML original
    (con bloque ``<style>``) — degrada bien en clientes modernos.

    Args:
        template_name: nombre de la plantilla.
        context: variables de Jinja2.

    Returns:
        HTML con CSS inline aplicado.
    """
    html = render_template(template_name, context)
    try:
        from premailer import transform  # type: ignore[import-not-found]
    except ImportError:
        log.debug("notifications.premailer_unavailable", fallback="style_block")
        return html
    try:
        return transform(
            html,
            # Mantener los @media queries como style block (no inline).
            keep_style_tags=True,
            remove_classes=False,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("notifications.premailer_failed", error=str(e))
        return html


__all__ = ["TEMPLATES_DIR", "render_template", "render_with_inline_css"]
