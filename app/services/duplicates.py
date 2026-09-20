"""Detección de ofertas repetidas.

Adzuna republica la misma oferta con ids distintos (reanuncios, varias
ciudades...). Se considera repetida por su "clave": empresa + título
normalizados (sin mayúsculas, tildes ni signos). Además una oferta ya está
"seguida" si el usuario tiene una candidatura con la misma URL o la misma
empresa + puesto.
"""
import re
import unicodedata

from sqlalchemy.orm import Session

from app.models.application import Application


def normalize(text: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def offer_key(company: str | None, title: str | None, location: str | None = None) -> str:
    """Clave de una oferta. Con ubicación: el mismo puesto en dos ciudades no es un duplicado."""
    return "|".join((normalize(company), normalize(title), normalize(location)))


def tracked_key(company: str | None, position: str | None) -> str:
    return f"{normalize(company)}|{normalize(position)}"


def normalize_url(url: str | None) -> str:
    """URL sin esquema, parámetros ni barra final: dos enlaces a la misma oferta
    suelen diferir solo en el tracking (?utm=...)."""
    if not url:
        return ""
    return re.sub(r"^https?://(www\.)?", "", url.strip().lower()).split("?")[0].split("#")[0].rstrip("/")


class TrackedIndex:
    """Candidaturas del usuario indexadas para saber si una oferta ya está en ellas."""

    def __init__(self, rows: list[tuple[str | None, str | None, str | None]]) -> None:
        self._keys = {tracked_key(company, position) for company, position, _ in rows}
        self._urls = {normalize_url(url) for _, _, url in rows if url}

    @classmethod
    def for_user(cls, db: Session, user_id: object) -> "TrackedIndex":
        rows = (
            db.query(Application.company_name, Application.position, Application.job_url)
            .filter(Application.user_id == user_id)
            .all()
        )
        return cls([tuple(row) for row in rows])

    def contains(self, company: str | None, title: str | None, url: str | None) -> bool:
        if url and normalize_url(url) in self._urls:
            return True
        return tracked_key(company, title) in self._keys
