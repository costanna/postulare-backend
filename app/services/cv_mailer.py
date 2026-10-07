"""Envío directo de la candidatura por email vía SMTP configurado (p. ej. Gmail).

Solo para cuentas reales: las demo tienen prohibido este endpoint (403).
Gmail exige una "contraseña de aplicación" (no la normal), que se crea con
la verificación en dos pasos activada en myaccount.google.com/apppasswords.
Límite gratis de Gmail: ~500 envíos/día; además hay tope por usuario
(SEND_EMAIL_DAILY_LIMIT_PER_USER).
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("postulare.cv_mailer")


class MailerError(Exception):
    """El email no se pudo enviar (config ausente o fallo de SMTP)."""


def smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


def send_application_email(to_email: str, subject: str, body: str, pdf_bytes: bytes, pdf_filename: str) -> None:
    """Envía la candidatura con el CV en PDF: el original subido o uno
    generado desde el texto. Siempre PDF, nunca texto plano."""
    if not smtp_configured():
        raise MailerError("Envío no configurado: faltan SMTP_HOST/SMTP_USER/SMTP_PASSWORD")

    message = EmailMessage()
    message["Subject"] = subject
    # Con Gmail el From debe ser la propia cuenta (o un alias verificado).
    message["From"] = settings.SMTP_USER or settings.SMTP_FROM
    message["To"] = to_email
    message.set_content(body)
    message.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailerError(f"No se pudo enviar el email: {exc}") from exc
