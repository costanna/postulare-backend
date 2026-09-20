"""Envío de emails transaccionales (recuperación de contraseña).

Si no hay SMTP configurado (desarrollo local), el email no se envía: el enlace
se registra en el log para poder probar el flujo sin infraestructura de correo.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("postulare.email")


def send_password_reset_email(to_email: str, reset_token: str) -> None:
    reset_link = f"{settings.FRONTEND_URL}/auth/reset-password?token={reset_token}"

    if not settings.SMTP_HOST:
        logger.info("SMTP no configurado. Enlace de restablecimiento para %s: %s", to_email, reset_link)
        return

    message = EmailMessage()
    message["Subject"] = "Restablece tu contraseña de Postulare"
    message["From"] = settings.SMTP_FROM
    message["To"] = to_email
    message.set_content(
        "Has solicitado restablecer tu contraseña en Postulare.\n\n"
        f"Abre este enlace para elegir una nueva contraseña:\n{reset_link}\n\n"
        "Si no has sido tú, puedes ignorar este email."
    )

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(message)
