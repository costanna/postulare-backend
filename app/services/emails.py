"""Extracción de emails de contacto desde textos (ofertas, webs de empresa)."""
import re

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_EMAIL_BLOCKLIST = ("example.com", "example.org", "example.net", "email.com", "noreply", "no-reply", "donotreply")


def extract_contact_email(*texts: str | None) -> str | None:
    """Primer email con pinta de contacto en los textos, o None si no hay."""
    for text in texts:
        if not text:
            continue
        for match in _EMAIL_RE.findall(text):
            lowered = match.lower()
            if any(blocked in lowered for blocked in _EMAIL_BLOCKLIST):
                continue
            return match.rstrip(".,;:!?()")
    return None
