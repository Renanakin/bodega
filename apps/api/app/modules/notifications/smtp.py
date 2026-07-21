"""Cliente SMTP async (aiosmtplib) para envio de emails (Fase 7, ADR-0004).

Decisiones:
- aiosmtplib 3.x: cliente SMTP async nativo (no bloquea el event loop).
- Soporta SMTP plano (Mailpit dev), STARTTLS (smtp_use_tls=True, prod) y
  SMTP+TLS (no usado en el proyecto, se deja extensible via configuracion).
- Timeout defensivo: 30s default. La mayoria de envios <2s; 30s cubre
  cuellos de botella en servers lentos.
- No se reintenta aqui: el retry lo hace ``NotificationsService.process_one``
  en base a ``attempts`` y ``email_max_attempts``.

Reglas:
- R1: la configuracion se lee de ``Settings`` (env vars), nunca hardcoded.
- R4: solo infrastructura SMTP, sin logica de negocio.
- R8: log estructurado por cada envio (smtp.sent, smtp.error).
"""

from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib
from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class SmtpError(Exception):
    """Error al enviar email via SMTP (envoltorio async-friendly).

    Captura excepciones de red/timeout/SMTP y las normaliza a una sola
    jerarquia para que ``NotificationsService.process_one`` pueda
    distinguir errores recuperables (transient) de errores permanentes
    (e.g. direccion invalida).

    Por defecto todos los errores SMTP son recuperables: el operador
    puede editar la direccion y re-enviar. Para errores permanentes se
    puede usar ``SmtpPermanentError``.
    """


class SmtpPermanentError(SmtpError):
    """Error SMTP que NO se debe reintentar (e.g. RCPT 550)."""


async def send_email(
    *,
    to_email: str,
    subject: str,
    body_html: str,
    from_email: str | None = None,
) -> None:
    """Envia un email HTML via SMTP async (aiosmtplib).

    Args:
        to_email: direccion destino (ya validada en ``enqueue``).
        subject: asunto del email.
        body_html: cuerpo HTML (CSS inline obligatorio).
        from_email: opcional; default ``settings.smtp_from``.

    Raises:
        SmtpPermanentError: si el server rechazo el destinatario (5xx
            recuperable) — el caller NO debe reintentar.
        SmtpError: cualquier otro error (timeout, conexion, 4xx transitorio).
            El caller debe reintentar hasta ``email_max_attempts``.
    """
    settings = get_settings()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email or settings.smtp_from
    msg["To"] = to_email
    # Fallback plain-text para clientes que no soportan HTML.
    msg.set_content("Por favor visualiza este email en un cliente que soporte HTML.")
    msg.add_alternative(body_html, subtype="html")

    username = settings.smtp_username or None
    password = settings.smtp_password.get_secret_value() if settings.smtp_password else None

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=username,
            password=password,
            # smtp_use_tls=True: STARTTLS. En Mailpit (dev) va sin TLS.
            start_tls=settings.smtp_use_tls,
            timeout=settings.smtp_timeout_seconds,
        )
        log.info(
            "smtp.sent",
            to=to_email,
            subject=subject,
            host=settings.smtp_host,
            port=settings.smtp_port,
        )
    except aiosmtplib.SMTPRecipientRefused as e:
        # 5xx en RCPT: direccion invalida, no se reintenta.
        log.error(
            "smtp.recipient_refused",
            to=to_email,
            code=e.code,
            message=str(e),
        )
        raise SmtpPermanentError(f"Destinatario rechazado por SMTP: {to_email} ({e})") from e
    except aiosmtplib.SMTPSenderRefused as e:
        log.error("smtp.sender_refused", code=e.code, message=str(e))
        raise SmtpError(f"Remitente rechazado por SMTP: {e}") from e
    except (TimeoutError, aiosmtplib.SMTPException, OSError) as e:
        log.error(
            "smtp.error",
            to=to_email,
            host=settings.smtp_host,
            port=settings.smtp_port,
            error_type=type(e).__name__,
            error=str(e),
        )
        raise SmtpError(f"Fallo al enviar email a {to_email}: {e}") from e


__all__ = ["SmtpError", "SmtpPermanentError", "send_email"]
