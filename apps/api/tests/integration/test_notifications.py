"""Tests del NotificationsService (Fase 7, ADR-0004).

Actualizado desde Fase 9: el service refactorizado llama a ``smtp.send_email``
(funcion del modulo) en vez del metodo legacy ``_send_email``. Los mocks
apuntan al path nuevo.

Fase 7 anade ``process_one`` (worker Arq). Los tests existentes validan
``process_pending`` (batch legacy) y la API de enqueue.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ordenes_compra import EmailOutbox
from app.modules.notifications import service as svc_module
from app.modules.notifications.service import NotificationsService


pytestmark = pytest.mark.integration


class TestNotificationsService:
    @pytest.mark.asyncio
    async def test_enqueue_email(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        outbox = await service.enqueue_email(
            to_email="test@bodega.example",
            subject="Test",
            body_html="<h1>Test</h1>",
        )
        assert outbox.status == "pending"
        assert outbox.attempts == 0

    @pytest.mark.asyncio
    async def test_process_pending_marks_sent(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        await service.enqueue_email(
            to_email="x@bodega.example", subject="X", body_html="<p>X</p>"
        )

        # Mock del cliente SMTP (Fase 7): ``process_one`` -> ``smtp_send_email``.
        # Mockeamos la referencia ``service.smtp_send_email`` (alias que el
        # modulo usa) para que el envio retorne OK.
        with patch.object(
            svc_module, "smtp_send_email", new=AsyncMock(return_value=None)
        ):
            stats = await service.process_pending(batch_size=10)
        assert stats["sent"] == 1
        assert stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_process_retries_on_error(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        await service.enqueue_email(
            to_email="y@bodega.example", subject="Y", body_html="<p>Y</p>"
        )

        # Mock SMTP que falla como transitorio. process_one debe incrementar
        # attempts y dejar status=pending.
        with patch.object(
            svc_module,
            "smtp_send_email",
            new=AsyncMock(side_effect=svc_module.SmtpError("SMTP error")),
        ):
            stats = await service.process_pending(batch_size=10)
        assert stats["retried"] == 1
        assert stats["sent"] == 0

    @pytest.mark.asyncio
    async def test_process_fails_after_max_attempts(
        self, async_engine, async_session: AsyncSession  # type: ignore[no-untyped-def]
    ) -> None:
        service = NotificationsService(async_session)
        outbox = await service.enqueue_email(
            to_email="z@bodega.example", subject="Z", body_html="<p>Z</p>"
        )
        # Forzar attempts = email_max_attempts (default 3).
        # process_one detecta ``attempts >= max_attempts`` -> dead, sin enviar.
        outbox.attempts = 3
        await async_session.commit()

        send_mock = AsyncMock(side_effect=svc_module.SmtpError("X"))
        with patch.object(svc_module, "smtp_send_email", new=send_mock):
            stats = await service.process_pending(batch_size=10)
        # process_pending solo selecciona attempts < MAX, asi que el row no entra.
        # stats debe mostrar 0 sent (correcto, no se proceso).
        assert stats["sent"] == 0
        # Y nunca se llamo a smtp_send_email.
        send_mock.assert_not_called()
