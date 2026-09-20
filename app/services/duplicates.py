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
    """Clave de una oferta. Con ubicación (solo la ciudad, antes de la coma, porque cada fuente
    la escribe distinto): el mismo puesto en dos ciudades no es un duplicado."""
    city = (location or "").split(",")[0]
    return "|".join((normalize(company), normalize(title), normalize(city)))


def tracked_key(company: str | None, position: str | None) -> str:
    return f"{normalize(company)}|{normalize(position)}"


_TRACKING_PARAMS = {"se", "v", "ref", "referrer", "source", "fbclid", "gclid", "trk", "campaign", "medium"}


def normalize_url(url: str | None) -> str:
    """URL sin esquema, fragmento ni barra final y sin parámetros de seguimiento (utm_*, se, v...).
    Los demás parámetros se conservan: en muchas webs el id de la oferta va ahí (?id=123), y sin él
    todas las ofertas de esa web parecerían la misma."""
    if not url:
        return ""
    bare = re.sub(r"^https?://(www\.)?", "", url.strip().lower()).split("#")[0]
    path, _, query = bare.partition("?")
    kept = sorted(
        part
        for part in query.split("&")
        if part and not part.startswith("utm_") and part.split("=")[0] not in _TRACKING_PARAMS
    )
    return path.rstrip("/") + ("?" + "&".join(kept) if kept else "")


class TrackedIndex:
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
