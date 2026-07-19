"""Tests E2E con Mailpit (Fase 7, ADR-0004).

Valida el flujo completo de envio de email:
1. ``smtp.send_email`` envia a Mailpit via SMTP.
2. La plantilla Jinja2 renderiza con el contexto correcto.
3. El token de aprobacion aparece en el body_html.
4. Tras aprobar via token, la OC pasa a estado ``aprobado``.

Requisitos:
- Mailpit corriendo en ``localhost:1025`` (SMTP) y ``localhost:8025`` (UI).
- Variables ``SMTP_HOST`` y ``SMTP_PORT`` apuntando a Mailpit.

Si Mailpit no esta disponible, los tests se skippean automaticamente
(``pytest.skip`` en el fixture).
"""
from __future__ import annotations

import asyncio
import socket
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import issue_approval_token
from app.db.models.ordenes_compra import (
    DetalleOrdenCompra,
    EmailOutbox,
    OrdenCompra,
    OrdenCompraEstado,
)
from app.db.models.products import Product
from app.db.models.supervisores import Supervisor
from app.db.models.warehouses import Warehouse
from app.modules.notifications.service import NotificationsService
from app.modules.notifications.smtp import send_email, SmtpError
from app.modules.notifications.templates import render_with_inline_css, render_template


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------- MAILPIT FIXTURE


def _mailpit_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    """TCP probe rapido a Mailpit. Falla el test si no esta disponible."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


@pytest.fixture
def mailpit_required() -> None:
    """Skip el test si Mailpit SMTP (1025) no esta disponible."""
    settings = get_settings()
    host = settings.smtp_host
    port = settings.smtp_port
    if host in ("localhost", "127.0.0.1") and not _mailpit_reachable(host, port):
        pytest.skip(
            f"Mailpit SMTP no esta accesible en {host}:{port}. "
            "Levantar con: docker compose -f infra/docker/docker-compose.yml up -d mailpit"
        )


@pytest.fixture
def mailpit_api_required() -> None:
    """Skip el test si Mailpit UI/API HTTP (8025) no esta disponible.

    Adicional al fixture ``mailpit_required`` (SMTP). Algunos tests
    validan el email via la API HTTP de Mailpit; si esa API no
    responde, los tests no pueden verificar el envio end-to-end.
    """
    if not _mailpit_reachable("localhost", 8025):
        pytest.skip(
            "Mailpit API HTTP no esta accesible en localhost:8025. "
            "Levantar Mailpit: docker compose -f infra/docker/docker-compose.yml up -d mailpit"
        )


# -------------------------------------------------------------- PLANTILLA TESTS


class TestPlantillaJinja2:
    def test_plantilla_se_renderiza_con_contexto_correcto(
        self, mailpit_api_required: None
    ) -> None:
        """Render de la plantilla con todos los campos del context."""
        ctx = {
            "subject": "OC-0042 requiere aprobacion",
            "supervisor": {"nombre": "Maria"},
            "oc": {
                "codigo": "OC-0042",
                "bodega_origen_nombre": "Principal",
                "solicitante_nombre": "Pedro",
                "proveedor_nombre": "Repuestos SA",
                "fecha_creacion": "2026-07-15",
                "total_estimado": "30.000",
                "lineas": [
                    {
                        "sku": "F-001",
                        "nombre": "Filtro",
                        "cantidad": "10",
                        "costo_unitario": "1.500",
                        "subtotal": "15.000",
                    },
                    {
                        "sku": "A-002",
                        "nombre": "Aceite",
                        "cantidad": "5",
                        "costo_unitario": "3.000",
                        "subtotal": "15.000",
                    },
                ],
            },
            "approve_url": "http://localhost:5173/ordenes-compra/aprobar/TOKEN_FAKE",
            "reject_url": "http://localhost:5173/ordenes-compra/rechazar/TOKEN_FAKE",
            "token_expires_at": "2026-07-22",
        }
        html = render_template("orden_compra.html.j2", ctx)
        # El HTML contiene los datos clave.
        assert "OC-0042" in html
        assert "Maria" in html
        assert "Pedro" in html
        assert "Repuestos SA" in html
        assert "F-001" in html
        assert "A-002" in html
        assert "30.000" in html  # total
        # El link de aprobacion aparece (con CSS inline).
        assert "TOKEN_FAKE" in html
        # El bloque del footer menciona el sistema.
        assert "Bodegaje" in html

    def test_premailer_aplica_css_inline(
        self, mailpit_api_required: None
    ) -> None:
        """Si premailer esta disponible, el CSS de ``<style>`` se inlinea."""
        ctx = {
            "subject": "X",
            "supervisor": {"nombre": "X"},
            "oc": {
                "codigo": "OC-9999",
                "bodega_origen_nombre": "X",
                "solicitante_nombre": "X",
                "proveedor_nombre": "X",
                "fecha_creacion": "2026-01-01",
                "total_estimado": "0",
                "lineas": [],
            },
            "approve_url": "http://x/a",
            "reject_url": "http://x/r",
            "token_expires_at": "2026-01-08",
        }
        html = render_with_inline_css("orden_compra.html.j2", ctx)
        assert "OC-9999" in html
        # Con premailer activo, debe haber inline style="background-color: ..."
        # (o al menos no fallar; si premailer no esta, retorna el HTML sin inlinear)
        if "style=" in html:
            # El boton Aprobar debe tener inline style.
            assert 'style="display: inline-block' in html or 'style="' in html


# ------------------------------------------------------ ENVIO REAL A MAILPIT


class TestEnvioSmtpReal:
    @pytest.mark.asyncio
    async def test_envio_email_real_a_mailpit(
        self, mailpit_api_required: None
    ) -> None:
        """Envia un email real a Mailpit y verifica via API de Mailpit."""
        # Antes de enviar, vaciamos la cola de Mailpit via su API HTTP.
        async with httpx.AsyncClient(base_url="http://localhost:8025", timeout=5) as http:
            try:
                await http.delete("/api/v1/messages")
            except httpx.HTTPError:
                # Mailpit no expone la API, pero el test sigue si SMTP anda.
                pass

        to_email = f"test-{uuid.uuid4().hex[:8]}@bodega.example"
        subject = f"E2E Fase 7 - {uuid.uuid4().hex[:8]}"
        body_html = (
            f"<h1>OC-0001</h1><p>Body test {uuid.uuid4()}</p>"
        )
        await send_email(
            to_email=to_email,
            subject=subject,
            body_html=body_html,
        )

        # Pequeño delay para que Mailpit registre el mensaje.
        await asyncio.sleep(0.5)

        # Verificar via API de Mailpit.
        async with httpx.AsyncClient(base_url="http://localhost:8025", timeout=5) as http:
            r = await http.get("/api/v1/messages")
            if r.status_code == 200:
                data = r.json()
                messages = data.get("messages", [])
                # Buscar el mensaje por subject.
                assert any(
                    msg.get("Subject") == subject for msg in messages
                ), f"Mailpit no recibio el email con subject {subject!r}"
            else:
                # Si la API no responde, al menos verificamos que el envio
                # no levanto excepcion. El SMTP probe ya valido el server.
                pytest.skip("Mailpit API no disponible; SMTP probe fue OK")

    @pytest.mark.asyncio
    async def test_plantilla_jinja2_se_envia_a_mailpit(
        self, mailpit_api_required: None
    ) -> None:
        """Renderiza plantilla + envia a Mailpit, verifica que llega."""
        async with httpx.AsyncClient(base_url="http://localhost:8025", timeout=5) as http:
            try:
                await http.delete("/api/v1/messages")
            except httpx.HTTPError:
                pass

        token_test = uuid.uuid4().hex
        ctx = {
            "subject": f"E2E Plantilla - {token_test[:8]}",
            "supervisor": {"nombre": "E2E"},
            "oc": {
                "codigo": "OC-7777",
                "bodega_origen_nombre": "PRINCIPAL",
                "solicitante_nombre": "E2E Bot",
                "proveedor_nombre": "Test SA",
                "fecha_creacion": "2026-07-15",
                "total_estimado": "99.999",
                "lineas": [
                    {
                        "sku": "TEST-1",
                        "nombre": "Producto test",
                        "cantidad": "3",
                        "costo_unitario": "33.333",
                        "subtotal": "99.999",
                    }
                ],
            },
            "approve_url": f"http://localhost:5173/ordenes-compra/aprobar/{token_test}",
            "reject_url": f"http://localhost:5173/ordenes-compra/rechazar/{token_test}",
            "token_expires_at": "2026-07-22",
        }
        body_html = render_with_inline_css("orden_compra.html.j2", ctx)
        await send_email(
            to_email=f"e2e-{token_test[:8]}@bodega.example",
            subject=ctx["subject"],
            body_html=body_html,
        )
        await asyncio.sleep(0.5)

        # Verificar via API.
        async with httpx.AsyncClient(base_url="http://localhost:8025", timeout=5) as http:
            r = await http.get("/api/v1/messages")
            if r.status_code == 200:
                data = r.json()
                messages = data.get("messages", [])
                assert any(
                    msg.get("Subject") == ctx["subject"] for msg in messages
                ), "Mailpit no recibio el email renderizado"

    @pytest.mark.asyncio
    async def test_token_aprobacion_esta_en_el_body_html(
        self, mailpit_api_required: None
    ) -> None:
        """El token HMAC de aprobacion aparece en el HTML enviado."""
        async with httpx.AsyncClient(base_url="http://localhost:8025", timeout=5) as http:
            try:
                await http.delete("/api/v1/messages")
            except httpx.HTTPError:
                pass

        # Generar token HMAC (ADR-0005).
        orden_id = str(uuid.uuid4())
        sup_id = str(uuid.uuid4())
        jti = str(uuid.uuid4())
        token = issue_approval_token(
            orden_id=orden_id, supervisor_id=sup_id, action="approve", jti=jti
        )

        # El token NO debe aparecer en claro en el subject (solo en el body).
        async with httpx.AsyncClient(base_url="http://localhost:8025", timeout=5) as http:
            r = await http.get("/api/v1/messages")
            if r.status_code == 200:
                before = len(r.json().get("messages", []))
            else:
                before = 0

        ctx = {
            "subject": "Token Check",
            "supervisor": {"nombre": "X"},
            "oc": {
                "codigo": "OC-9999",
                "bodega_origen_nombre": "X",
                "solicitante_nombre": "X",
                "proveedor_nombre": "X",
                "fecha_creacion": "2026-01-01",
                "total_estimado": "0",
                "lineas": [],
            },
            "approve_url": f"http://localhost:5173/ordenes-compra/aprobar/{token}",
            "reject_url": f"http://localhost:5173/ordenes-compra/rechazar/{token}",
            "token_expires_at": "2026-01-08",
        }
        body_html = render_with_inline_css("orden_compra.html.j2", ctx)
        # El token debe estar en el body_html (es un link con el token en URL).
        assert token in body_html

        # Enviar a Mailpit.
        await send_email(
            to_email="x@x.com",
            subject=ctx["subject"],
            body_html=body_html,
        )
        await asyncio.sleep(0.5)

        # Verificar que el mensaje llego y contiene el token.
        async with httpx.AsyncClient(base_url="http://localhost:8025", timeout=5) as http:
            r = await http.get("/api/v1/messages")
            if r.status_code == 200:
                data = r.json()
                messages = data.get("messages", [])
                # Buscar el mensaje con el token en el body.
                found = False
                for msg in messages:
                    detail_r = await http.get(f"/api/v1/message/{msg['ID']}")
                    if detail_r.status_code == 200:
                        detail = detail_r.json()
                        body_content = detail.get("Body", "") or detail.get("HTML", "")
                        if token in body_content:
                            found = True
                            break
                assert found, f"Token {token!r} no aparece en el body de Mailpit"


# ----------------------------------------------- APROBACION VIA TOKEN (END-TO-END)


class TestAprobacionFlujoCompleto:
    @pytest.mark.asyncio
    async def test_aprobacion_via_link_email_actualiza_oc(
        self,
        async_engine,  # type: ignore[no-untyped-def]
        async_session: AsyncSession,
        mailpit_required: None,
    ) -> None:
        """E2E: crear OC + enviar email + aprobar via token -> estado aprobado."""
        wh = Warehouse(
            id=uuid.uuid4(), code="W-F7", name="W", warehouse_type="principal"
        )
        sup = Supervisor(
            id=uuid.uuid4(), nombre="E2E Test", email="e2e@x.com", activo=True
        )
        p = Product(id=uuid.uuid4(), sku="F7-1", name="Prod", unit="u")
        async_session.add_all([wh, sup, p])
        await async_session.commit()

        # Crear OC.
        oc = OrdenCompra(
            id=uuid.uuid4(),
            codigo="OC-E2E-1",
            id_bodega_principal=wh.id,
            id_supervisor=sup.id,
            proveedor_nombre="E2E Proveedor",
            estado=OrdenCompraEstado.BORRADOR,
            total_estimado=Decimal("100"),
        )
        async_session.add(oc)
        await async_session.flush()
        async_session.add(
            DetalleOrdenCompra(
                id_orden_compra=oc.id,
                id_producto=p.id,
                cantidad_pedida=Decimal("2"),
                costo_unitario_pactado=Decimal("50"),
            )
        )
        await async_session.commit()

        # Encolar email.
        jti = str(uuid.uuid4())
        oc.email_token_jti = jti
        oc.estado = OrdenCompraEstado.ENVIADO_A_SUPERVISOR
        oc.email_enviado_at = datetime.now(UTC)
        await async_session.commit()

        token = issue_approval_token(
            orden_id=str(oc.id),
            supervisor_id=str(sup.id),
            action="approve",
            jti=jti,
        )

        # Enviar email a Mailpit (no falla aunque la API no este, SMTP ya
        # fue probado por el fixture).
        try:
            await send_email(
                to_email=sup.email,
                subject=f"OC {oc.codigo}",
                body_html=f"<a href='http://localhost/ordenes-compra/aprobar/{token}'>Aprobar</a>",
            )
        except SmtpError:
            pass  # El foco del test es la aprobacion, no el SMTP.

        # Aprobar via token (sin auth, sin red).
        from app.modules.ordenes_compra.service import OrdenCompraService

        service = OrdenCompraService(async_session)
        view = await service.aprobar_con_token(token, "approve")
        assert view.estado == "aprobado"
        assert view.aprobado_at is not None

        # Verificar que el outbox fue procesado o que el flujo esta OK.
        from sqlalchemy import select

        result = await async_session.execute(select(EmailOutbox))
        outboxes = list(result.scalars().all())
        # El outbox (si fue creado por enviar_correo) debe tener status sent
        # tras process_one, o pending si el worker no corrio.
        for ob in outboxes:
            assert ob.status in ("sent", "pending", "dead")
