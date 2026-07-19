"""Tests unitarios del NotificationsService (Fase 7, ADR-0004).

Cubre:
- ``enqueue`` valida email y renderiza plantilla.
- ``enqueue`` encola en Arq (LPUSH a arq:queue) — mockeamos el helper.
- ``process_one`` transiciones de estado: pending -> sent / dead.
- ``process_one`` retry con backoff (attempts++, status=pending).
- ``process_one`` SmtpPermanentError -> dead inmediato.
- ``metrics`` conteo por status.

Mockeamos:
- ``app.worker.enqueue_send_email_task`` (helper de Arq) — para
  verificar LPUSH sin tocar Redis.
- ``app.modules.notifications.smtp.send_email`` (cliente aiosmtplib)
  — para verificar envio sin tocar SMTP.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import worker as worker_module
from app.db.models.ordenes_compra import EmailOutbox
from app.modules.notifications import smtp as smtp_module
from app.modules.notifications import service as svc_module
from app.modules.notifications.service import (
    InvalidEmailError,
    NotificationsService,
)


pytestmark = pytest.mark.unit


# Context minimo valido para la plantilla ``orden_compra.html.j2``.
OC_CONTEXT = {
    "subject": "OC-0001 requiere aprobacion",
    "supervisor": {"nombre": "Juan"},
    "oc": {
        "codigo": "OC-0001",
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
            }
        ],
    },
    "approve_url": "http://localhost:5173/ordenes-compra/aprobar/abc",
    "reject_url": "http://localhost:5173/ordenes-compra/rechazar/abc",
    "token_expires_at": "2026-07-22",
}


@pytest.fixture
def enqueue_mock() -> AsyncMock:
    """Mock del helper que LPUSHea a Redis via Arq."""
    return AsyncMock(return_value=None)


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_inserta_outbox_y_lpush_redis(
        self, async_engine, async_session: AsyncSession, enqueue_mock: AsyncMock  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        # Patch del helper en su modulo de origen (app.worker) para que
        # el import lazy dentro de service.py lo encuentre mockeado.
        with patch.object(worker_module, "enqueue_send_email_task", new=enqueue_mock):
            ob = await service.enqueue(
                to_email="juan@bodega.example",
                subject="OC-0001 requiere aprobacion",
                template_name="orden_compra.html.j2",
                context=OC_CONTEXT,
            )
        # El outbox se inserto en BD con status=pending.
        assert ob.id is not None
        assert ob.status == "pending"
        assert ob.attempts == 0
        assert ob.to_email == "juan@bodega.example"
        assert ob.subject == "OC-0001 requiere aprobacion"
        # body_html renderizado (contiene el codigo OC y el nombre del supervisor).
        assert "OC-0001" in ob.body_html
        assert "Juan" in ob.body_html
        # LPUSH a Arq fue invocado con el outbox.id.
        enqueue_mock.assert_called_once_with(str(ob.id))

    @pytest.mark.asyncio
    async def test_enqueue_con_email_invalido_falla(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        with pytest.raises(InvalidEmailError):
            await service.enqueue(
                to_email="not-an-email",
                subject="X",
                template_name="orden_compra.html.j2",
                context=OC_CONTEXT,
            )
        # No se inserto nada en BD.
        stmt = select(EmailOutbox)
        result = await async_session.execute(stmt)
        assert list(result.scalars().all()) == []

    @pytest.mark.asyncio
    async def test_enqueue_si_redis_cae_no_falla_encolar(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        """Si el LPUSH a Redis falla, el outbox queda en BD y el cron lo recoge."""
        service = NotificationsService(async_session)
        with patch.object(
            worker_module,
            "enqueue_send_email_task",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ):
            ob = await service.enqueue(
                to_email="a@bodega.example",
                subject="X",
                template_name="orden_compra.html.j2",
                context=OC_CONTEXT,
            )
        # El outbox se inserto aunque Redis haya fallado.
        assert ob.status == "pending"


class TestProcessOne:
    @pytest.mark.asyncio
    async def test_envia_email_y_marca_sent(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        ob = await service.enqueue_email(
            to_email="k@bodega.example",
            subject="K",
            body_html="<p>K</p>",
        )
        # Patch sobre el alias ``smtp_send_email`` que el service importa
        # a nivel de modulo (``from ... import send_email as smtp_send_email``).
        with patch.object(
            svc_module, "smtp_send_email", new=AsyncMock(return_value=None)
        ):
            result = await service.process_one(ob.id)
        assert result["status"] == "sent"
        assert result["attempts"] == 0
        # Re-leer de BD: status=sent, sent_at set.
        reloaded = await async_session.get(EmailOutbox, ob.id)
        assert reloaded is not None
        assert reloaded.status == "sent"
        assert reloaded.sent_at is not None
        assert reloaded.last_error is None

    @pytest.mark.asyncio
    async def test_smtp_error_transitorio_aumenta_attempts(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        ob = await service.enqueue_email(
            to_email="t@bodega.example",
            subject="T",
            body_html="<p>T</p>",
        )
        with patch.object(
            svc_module,
            "smtp_send_email",
            new=AsyncMock(side_effect=smtp_module.SmtpError("timeout")),
        ):
            result = await service.process_one(ob.id)
        assert result["status"] == "pending"
        assert result["attempts"] == 1
        reloaded = await async_session.get(EmailOutbox, ob.id)
        assert reloaded is not None
        assert reloaded.attempts == 1
        assert reloaded.status == "pending"
        assert "transient" in (reloaded.last_error or "")

    @pytest.mark.asyncio
    async def test_smtp_permanent_error_marca_dead(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        ob = await service.enqueue_email(
            to_email="p@bodega.example",
            subject="P",
            body_html="<p>P</p>",
        )
        with patch.object(
            svc_module,
            "smtp_send_email",
            new=AsyncMock(side_effect=smtp_module.SmtpPermanentError("550 user unknown")),
        ):
            result = await service.process_one(ob.id)
        assert result["status"] == "dead"
        assert result["attempts"] == 1
        reloaded = await async_session.get(EmailOutbox, ob.id)
        assert reloaded is not None
        assert reloaded.status == "dead"
        assert "permanent" in (reloaded.last_error or "")

    @pytest.mark.asyncio
    async def test_despues_3_fallos_marca_dead(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        ob = await service.enqueue_email(
            to_email="d@bodega.example",
            subject="D",
            body_html="<p>D</p>",
        )
        # Forzar attempts=2 (el 3er intento debe fallar -> dead).
        ob.attempts = 2
        await async_session.commit()

        with patch.object(
            svc_module,
            "smtp_send_email",
            new=AsyncMock(side_effect=smtp_module.SmtpError("timeout")),
        ):
            result = await service.process_one(ob.id)
        # attempts=3 (incremento) >= max_attempts=3 -> dead.
        assert result["status"] == "dead"
        assert result["attempts"] == 3
        reloaded = await async_session.get(EmailOutbox, ob.id)
        assert reloaded is not None
        assert reloaded.status == "dead"

    @pytest.mark.asyncio
    async def test_outbox_no_existente_retorna_missing(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        result = await service.process_one(uuid.uuid4())
        assert result["status"] == "missing"

    @pytest.mark.asyncio
    async def test_outbox_ya_sent_skip(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        ob = await service.enqueue_email(
            to_email="s@bodega.example",
            subject="S",
            body_html="<p>S</p>",
        )
        ob.status = "sent"
        ob.sent_at = None
        await async_session.commit()

        send_mock = AsyncMock(return_value=None)
        with patch.object(svc_module, "smtp_send_email", new=send_mock):
            result = await service.process_one(ob.id)
        assert result["status"] == "sent"
        send_mock.assert_not_called()


class TestRetryDeadAndMetrics:
    @pytest.mark.asyncio
    async def test_retry_dead_re_encola(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        # Crear 2 dead, 1 sent.
        for i, st in enumerate(["dead", "dead", "sent"]):
            ob = await service.enqueue_email(
                to_email=f"u{i}@bodega.example",
                subject=f"U{i}",
                body_html="<p>X</p>",
            )
            ob.status = st
            ob.attempts = 3
        await async_session.commit()

        enqueue_mock = AsyncMock(return_value=None)
        with patch.object(worker_module, "enqueue_send_email_task", new=enqueue_mock):
            count = await service.retry_dead()
        assert count == 2
        # LPUSH para los 2 dead.
        assert enqueue_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_metrics_retorna_conteo_por_status(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        # 3 pending, 2 sent, 1 dead.
        for i, st in enumerate(["pending", "pending", "pending", "sent", "sent", "dead"]):
            ob = await service.enqueue_email(
                to_email=f"m{i}@bodega.example",
                subject=f"M{i}",
                body_html="<p>M</p>",
            )
            ob.status = st
        await async_session.commit()

        metrics = await service.metrics()
        assert metrics["pending"] == 3
        assert metrics["sent"] == 2
        assert metrics["dead"] == 1
        assert metrics["total"] == 6
