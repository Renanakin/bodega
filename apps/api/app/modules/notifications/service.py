"""
NotificationsService: cola SMTP async (Fase 7, ADR-0004 / ADR-0005).

Implementa el patron outbox:
- Servicio encola emails en tabla `email_outbox` (status='pending').
- Tras el INSERT hace LPUSH via Arq (``app.worker.enqueue_send_email_task``)
  para que el worker Arq envie via SMTP async (aiosmtplib).
- En dev: Mailpit. En prod: AWS SES / SendGrid / Mailgun.

Reglas:
- R4: solo escribe en email_outbox; el envio es del worker.
- R6: idempotencia via outbox.id; retry exponencial con ``email_max_attempts``.
- R8: cada envio/reintento emite log estructurado.
- API publica:
    * ``enqueue`` — metodo canonico (Fase 7) con template_name + context.
    * ``enqueue_email`` — alias legacy (Fase 9 pre-refactor) que solo
      guarda body_html; se mantiene para no romper tests previos.
    * ``process_one(outbox_id)`` — worker Arq: procesa UN email.
    * ``process_pending(batch_size)`` — batch legacy (script standalone).
    * ``retry_dead()`` — admin: reintenta emails en estado 'dead'.
    * ``metrics()`` — conteo por status para Prometheus.
"""

from __future__ import annotations

import json
import re
import smtplib
import uuid
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.ordenes_compra import EmailOutbox
from app.modules.notifications.smtp import (
    SmtpError,
    SmtpPermanentError,
)
from app.modules.notifications.smtp import (
    send_email as smtp_send_email,
)
from app.modules.notifications.templates import render_with_inline_css
from app.modules.observability.metrics import (
    EMAIL_DEAD_TOTAL,
    EMAIL_FAILED_TOTAL,
    EMAIL_SENT_TOTAL,
    EMAIL_SMTP_SEND_DURATION,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


# Regex simple para validar formato de email. No es RFC 5322 completo
# (eso requiere una lib), pero cubre el 99% de los casos reales.
_EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidEmailError(ValueError):
    """Email destino con formato invalido (no se encola)."""


class NotificationsService:
    """Encola y procesa emails via outbox pattern."""

    # Estado terminales / no procesables. Alias para que el codigo del worker
    # y los tests compartan la fuente de verdad.
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_DEAD = "dead"

    # Legacy: el script standalone original (Fase 9) lo usa. Para Arq
    # usamos ``settings.email_max_attempts`` (3 por default).
    MAX_ATTEMPTS_LEGACY = 3

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----------------------------------------------------------------- ENQUEUE

    async def enqueue(
        self,
        *,
        to_email: str,
        subject: str,
        template_name: str,
        context: dict[str, Any],
        _priority: int = 5,
    ) -> EmailOutbox:
        """Encola un email renderizando la plantilla Jinja2 (Fase 7 API).

        Pasos:
        1. Validar ``to_email`` (formato).
        2. Renderizar plantilla con ``context`` y aplicar CSS inline
           (premailer); el resultado se guarda como snapshot en
           ``body_html`` para que el envio no dependa del FS en runtime.
        3. INSERT en ``email_outbox`` (status='pending', attempts=0).
        4. Encolar ``send_email_task`` en Arq (LPUSH a ``arq:queue``).
        5. Log estructurado ``notifications.enqueued``.

        Args:
            to_email: direccion destino.
            subject: asunto del email.
            template_name: nombre de la plantilla (ej. ``orden_compra.html.j2``).
            context: dict de variables para Jinja2.
            priority: prioridad Arq (no usado en 0.28, mantenido para
                forward-compat con posibles schedulers).

        Returns:
            ``EmailOutbox`` recien creada (con ``id``).

        Raises:
            InvalidEmailError: si ``to_email`` no tiene formato valido.
        """
        if not _EMAIL_REGEX.match(to_email or ""):
            raise InvalidEmailError(f"Email destino invalido: {to_email!r}")

        body_html = render_with_inline_css(template_name, context)

        outbox = EmailOutbox(
            id=uuid.uuid4(),
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            template_name=template_name,
            template_context=json.dumps(context, default=str),
            status=self.STATUS_PENDING,
            attempts=0,
        )
        self._session.add(outbox)
        # Flush para que ``outbox.id`` exista antes de encolar.
        await self._session.flush()

        # Encolar en Arq. La funcion helper se importa lazy para evitar
        # circular import: ``app.worker`` importa ``app.modules.notifications``,
        # no al reves. La importacion lazy (dentro de la coroutine) rompe el ciclo.
        try:
            from app.worker import enqueue_send_email_task  # noqa: PLC0415

            await enqueue_send_email_task(str(outbox.id))
        except Exception as e:  # noqa: BLE001
            # Si Redis cae, NO fallamos el INSERT: el outbox queda pendiente
            # y el cron de retry (Fase 7+) o el retry manual lo recoge.
            log.warning(
                "notifications.enqueue_redis_failed",
                outbox_id=str(outbox.id),
                error=str(e),
                note="El email queda en outbox; sera procesado por el cron de retry",
            )

        log.info(
            "notifications.enqueued",
            outbox_id=str(outbox.id),
            to_email=to_email,
            subject=subject,
            template_name=template_name,
        )
        return outbox

    async def enqueue_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_html: str,
        template_name: str | None = None,
        template_context: str | None = None,
    ) -> EmailOutbox:
        """Encola un email sin renderizar plantilla (LEGACY, Fase 9).

        Mantenido para no romper ``tests/integration/test_notifications.py``
        y el caller de ``OrdenCompraService.enviar_correo`` (que ya pasa
        ``body_html`` pre-armado con el link al token).

        NO encola en Arq: el caller (Fase 6) esperaba que el cron del
        script standalone ``notifications/worker.py`` recogiera la cola.
        En Fase 7 el path canonico es ``enqueue()``.
        """
        outbox = EmailOutbox(
            id=uuid.uuid4(),
            to_email=to_email,
            subject=subject,
            body_html=body_html,
            template_name=template_name,
            template_context=template_context,
            status=self.STATUS_PENDING,
        )
        self._session.add(outbox)
        await self._session.commit()
        await self._session.refresh(outbox)
        log.info(
            "notifications.enqueued_legacy",
            outbox_id=str(outbox.id),
            to_email=to_email,
            subject=subject,
        )
        return outbox

    # ------------------------------------------------------------- PROCESS ONE

    async def process_one(self, outbox_id: str | uuid.UUID) -> dict[str, Any]:
        """Procesa UN email (worker Arq).

        Comportamiento:
        - SELECT FOR UPDATE-like via ``get()``; si status != 'pending' skip.
        - Si ``attempts >= email_max_attempts``: marcar ``dead`` y skip.
        - Renderizar plantilla solo si ``body_html`` esta vacio (no es el caso
          habitual, pero permite re-render si se subio una plantilla nueva).
        - Enviar via ``smtp.send_email``:
            * OK: status='sent', sent_at=now().
            * ``SmtpPermanentError`` (destinatario invalido): status='dead'.
            * Otro ``SmtpError``: attempts++, status='pending' con
              ``next_retry_at`` calculado via backoff.
        - Commit al final (idempotente si se llama dos veces: el SELECT
          inicial re-leera ``status`` despues del primer commit).

        Returns:
            Dict con ``status`` final y ``attempts`` (util para Arq result).
        """
        settings = get_settings()
        oid = uuid.UUID(str(outbox_id))
        ob = await self._session.get(EmailOutbox, oid)
        if ob is None:
            log.warning("notifications.outbox_not_found", outbox_id=str(oid))
            return {"status": "missing", "attempts": 0}
        if ob.status != self.STATUS_PENDING:
            # Ya procesado por otro worker o cron.
            log.debug(
                "notifications.skip_non_pending",
                outbox_id=str(oid),
                current_status=ob.status,
            )
            return {"status": ob.status, "attempts": ob.attempts}
        if ob.attempts >= settings.email_max_attempts:
            ob.status = self.STATUS_DEAD
            ob.last_error = "max_attempts_reached"
            await self._session.commit()
            # Métricas Fase 9: dead por agotar retries (sin SMTP attempt nuevo).
            EMAIL_DEAD_TOTAL.inc()
            log.error(
                "notifications.dead_max_attempts",
                outbox_id=str(oid),
                to_email=ob.to_email,
                attempts=ob.attempts,
            )
            return {"status": self.STATUS_DEAD, "attempts": ob.attempts}

        # Intentar envio. El re-render solo aplica si el snapshot esta vacio
        # (caso raro: reintento manual tras cambio de plantilla).
        body_html = ob.body_html
        if not body_html and ob.template_name and ob.template_context:
            try:
                ctx = json.loads(ob.template_context)
                body_html = render_with_inline_css(ob.template_name, ctx)
                ob.body_html = body_html
            except Exception as e:  # noqa: BLE001
                # Si falla el re-render, no es recuperable: marca dead.
                ob.attempts += 1
                ob.status = self.STATUS_DEAD
                ob.last_error = f"render_failed: {e}"[:500]
                await self._session.commit()
                # Métricas Fase 9: dead por render fail (no recuperable).
                EMAIL_DEAD_TOTAL.inc()
                log.error(
                    "notifications.render_failed",
                    outbox_id=str(oid),
                    error=str(e),
                )
                return {"status": self.STATUS_DEAD, "attempts": ob.attempts}

        # Medir duracion del envio SMTP con histograma Prometheus.
        # El context manager registra en TODOS los paths (exito o
        # excepcion); el histograma siempre ve el tiempo real gastado
        # en el SMTP, lo cual es util para detectar servers lentos.
        with EMAIL_SMTP_SEND_DURATION.time():
            try:
                await smtp_send_email(
                    to_email=ob.to_email,
                    subject=ob.subject,
                    body_html=body_html,
                )
            except SmtpPermanentError as e:
                ob.attempts += 1
                ob.status = self.STATUS_DEAD
                ob.last_error = f"permanent: {e}"[:500]
                await self._session.commit()
                # Métricas Fase 9: error permanente y dead.
                EMAIL_FAILED_TOTAL.labels(error_type="permanent").inc()
                EMAIL_DEAD_TOTAL.inc()
                log.error(
                    "notifications.dead_permanent",
                    outbox_id=str(oid),
                    to_email=ob.to_email,
                    error=str(e),
                )
                return {"status": self.STATUS_DEAD, "attempts": ob.attempts}
            except SmtpError as e:
                ob.attempts += 1
                ob.last_error = f"transient: {e}"[:500]
                if ob.attempts >= settings.email_max_attempts:
                    ob.status = self.STATUS_DEAD
                    await self._session.commit()
                    # Métricas Fase 9: error transient que agota retries → dead.
                    EMAIL_FAILED_TOTAL.labels(error_type="transient").inc()
                    EMAIL_DEAD_TOTAL.inc()
                    log.error(
                        "notifications.dead_after_retry",
                        outbox_id=str(oid),
                        to_email=ob.to_email,
                        attempts=ob.attempts,
                        error=str(e),
                    )
                    return {
                        "status": self.STATUS_DEAD,
                        "attempts": ob.attempts,
                    }
                # Mantiene status='pending' pero calcula next_retry_at.
                backoff_list = settings.email_retry_backoff_list
                backoff = backoff_list[ob.attempts - 1]
                # Métricas Fase 9: error transient (reintentable, NO dead).
                EMAIL_FAILED_TOTAL.labels(error_type="transient").inc()
                log.warning(
                    "notifications.retry_scheduled",
                    outbox_id=str(oid),
                    to_email=ob.to_email,
                    attempts=ob.attempts,
                    next_retry_in_seconds=backoff,
                    error=str(e),
                )
                await self._session.commit()
                return {"status": self.STATUS_PENDING, "attempts": ob.attempts}
        # Path exitoso: el `with EMAIL_SMTP_SEND_DURATION.time()` salio
        # sin excepcion, asi que llegamos aqui. La estructura
        # `with` + `try/except` no permite un ``else`` que sea alcanzable
        # cuando hay returns dentro del with, asi que lo manejamos
        # como un bloque lineal al final.
        ob.status = self.STATUS_SENT
        ob.sent_at = datetime.now(UTC)
        ob.last_error = None
        await self._session.commit()
        # Métricas Fase 9: envio exitoso.
        EMAIL_SENT_TOTAL.inc()
        log.info(
            "notifications.sent",
            outbox_id=str(oid),
            to_email=ob.to_email,
            subject=ob.subject,
            attempts=ob.attempts,
        )
        return {"status": self.STATUS_SENT, "attempts": ob.attempts}

    # -------------------------------------------------------- PROCESS PENDING

    async def process_pending(self, batch_size: int = 10) -> dict[str, int]:
        """Procesa batch de emails pendientes (LEGACY, script standalone).

        Llamado por ``notifications/worker.py:main_loop``. En Arq el path
        canonico es ``process_one``.

        Returns:
            Dict con conteo {sent, failed, retried, skipped}.
        """
        stmt = (
            select(EmailOutbox)
            .where(EmailOutbox.status == self.STATUS_PENDING)
            .where(EmailOutbox.attempts < self.MAX_ATTEMPTS_LEGACY)
            .limit(batch_size)
        )
        result = await self._session.execute(stmt)
        outboxes = list(result.scalars().all())

        stats: dict[str, int] = {"sent": 0, "failed": 0, "retried": 0, "skipped": 0}
        for ob in outboxes:
            r = await self.process_one(ob.id)
            s = r["status"]
            if s == self.STATUS_SENT:
                stats["sent"] += 1
            elif s == self.STATUS_DEAD:
                stats["failed"] += 1
            elif s == self.STATUS_PENDING:
                stats["retried"] += 1
            else:
                stats["skipped"] += 1

        await self._session.commit()
        log.info("notifications.batch_processed", **stats)
        return stats

    # --------------------------------------------------------------- RETRY DEAD

    async def retry_dead(self) -> int:
        """Re-pone en cola los emails en estado 'dead' (uso admin).

        Devuelve la cantidad de outboxes re-encoladas. NO incrementa
        ``attempts``: el operador decidio reintentar, asumimos que el
        problema subyacente (e.g. SMTP caido) ya esta resuelto.
        """
        stmt = select(EmailOutbox).where(EmailOutbox.status == self.STATUS_DEAD)
        result = await self._session.execute(stmt)
        outboxes = list(result.scalars().all())
        if not outboxes:
            return 0
        for ob in outboxes:
            ob.status = self.STATUS_PENDING
            ob.attempts = 0
            ob.last_error = None
        await self._session.commit()
        # Encolar en Arq. Usamos la misma logica que enqueue() pero sin
        # re-validar email ni re-renderizar (body_html ya esta en BD).
        try:
            from app.worker import enqueue_send_email_task  # noqa: PLC0415

            for ob in outboxes:
                await enqueue_send_email_task(str(ob.id))
        except Exception as e:  # noqa: BLE001
            log.warning(
                "notifications.retry_dead_redis_failed",
                count=len(outboxes),
                error=str(e),
            )
        log.info("notifications.retry_dead", count=len(outboxes))
        return len(outboxes)

    # ----------------------------------------------------------------- METRICS

    async def metrics(self) -> dict[str, int]:
        """Conteos por status. Util para Prometheus (`/metrics` custom)."""
        stmt = select(EmailOutbox.status, func.count(EmailOutbox.id)).group_by(EmailOutbox.status)
        result = await self._session.execute(stmt)
        counts: dict[str, int] = {
            self.STATUS_PENDING: 0,
            self.STATUS_SENT: 0,
            self.STATUS_DEAD: 0,
        }
        for status, count in result.all():
            counts[status] = count
        counts["total"] = sum(counts.values())
        return counts

    # --------------------------------------------------- LEGACY _send_email

    async def _send_email(self, ob: EmailOutbox) -> None:
        """Envia un email via SMTP sincronico (LEGACY, Fase 9).

        Mantenido porque ``tests/integration/test_notifications.py`` lo
        monkey-patchea. NO usar en codigo nuevo: usar ``smtp.send_email``.
        En dev: usa Mailpit (sin TLS). En prod: STARTTLS.
        """
        settings = get_settings()

        # Construir mensaje MIME
        msg = MIMEMultipart("alternative")
        msg["Subject"] = ob.subject
        msg["From"] = settings.smtp_from
        msg["To"] = ob.to_email
        msg.attach(MIMEText(ob.body_html, "html"))

        # En dev: usar Mailpit (sin TLS)
        # En prod: AWS SES (con TLS)
        if settings.smtp_use_tls:
            smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
            smtp.starttls()
        else:
            smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)

        try:
            if settings.smtp_username:
                smtp.login(
                    settings.smtp_username,
                    settings.smtp_password.get_secret_value() if settings.smtp_password else "",
                )
            smtp.sendmail(settings.smtp_from, [ob.to_email], msg.as_string())
        finally:
            smtp.quit()

        log.info(
            "notifications.sent_legacy",
            outbox_id=str(ob.id),
            to_email=ob.to_email,
            subject=ob.subject,
        )
