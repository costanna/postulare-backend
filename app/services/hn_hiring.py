"""Empresas que contratan, descubiertas solas desde APIs públicas y gratuitas.

Dos orígenes, sin inventar nada:

1. Tus propias ofertas: empresas agregadas de tus matches con email de
   contacto extraído de la descripción.
2. HN "Who is hiring" (hilo mensual): comentarios con formato
   "Empresa | ubicación | ..." donde las empresas publican su email.
   Se filtra por España/remoto y por encaje con tus skills.

Solo se proponen empresas CON email real. El piloto las importa solo y envía.
"""
import html
import re

import httpx

from app.core.config import settings
from app.services.duplicates import normalize
from app.services.emails import extract_contact_email
from app.services.eures import is_spain_location
from app.services.job_search import JobSearchError, _cache_get, _cache_put
from app.services.lang_detect import detect_language
from app.services.scoring import _mentions

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
HN_ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"

_TIMEOUT = 15.0
MAX_COMMENTS = 400
MAX_SUGGESTIONS = 20


def hn_hiring_enabled() -> bool:
    return bool(settings.HN_HIRING_ENABLED)


def _clean(text: str | None) -> str:
    if not text:
        return ""
    no_html = re.sub(r"<[^>]+>", " ", text)
    no_html = html.unescape(no_html)
    return re.sub(r"\s+", " ", no_html).strip()


def _company_name(text: str) -> str | None:
    first = re.split(r"[|\n]", text, maxsplit=1)[0]
    name = re.sub(r"[*_`~]", "", first).strip()[:255]
    if not name or "@" in name or len(name) < 2:
        return None
    return name


def find_hiring_thread() -> str | None:
    """ID del hilo "Ask HN: Who is hiring?" más reciente, o None."""
    cached = _cache_get(("hn_hiring_thread",))
    if cached is not None:
        return cached[0] if cached else None
    try:
        response = httpx.get(
            HN_SEARCH_URL,
            params={"query": "Who is hiring", "tags": "story", "hitsPerPage": 10},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        hits = response.json().get("hits", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise JobSearchError(f"Error buscando el hilo de HN: {exc}") from exc
    thread_id = None
    for hit in hits:
        title = hit.get("title") or ""
        if title.startswith("Ask HN: Who is hiring?"):
            thread_id = str(hit.get("objectID"))
            break
    _cache_put(("hn_hiring_thread",), [thread_id] if thread_id else [])
    return thread_id


def fetch_hn_suggestions(skills: list[str], max_n: int = MAX_SUGGESTIONS) -> list[dict]:
    """[{name, email, language, match_score, source}] del hilo mensual."""
    if not hn_hiring_enabled():
        return []
    cache_key = ("hn_hiring", tuple(sorted(s.lower() for s in skills)))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    thread_id = find_hiring_thread()
    if thread_id is None:
        return []
    try:
        response = httpx.get(HN_ITEM_URL.format(id=thread_id), timeout=_TIMEOUT)
        response.raise_for_status()
        children = response.json().get("children", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise JobSearchError(f"Error leyendo el hilo de HN: {exc}") from exc

    clean_skills = [s.strip().lower() for s in skills if s and s.strip()]
    original = {s.strip().lower(): s.strip() for s in skills if s and s.strip()}
    suggestions = []
    seen_emails: set[str] = set()
    for comment in children[:MAX_COMMENTS]:
        if not isinstance(comment, dict):
            continue
        text = _clean(comment.get("text"))
        if not text:
            continue
        email = extract_contact_email(text)
        if not email or email.lower() in seen_emails:
            continue
        if not is_spain_location(text):
            continue
        lowered = text.lower()
        hits = [original[skill] for skill in clean_skills if _mentions(skill, lowered)]
        if not hits:
            continue
        name = _company_name(text)
        if not name:
            continue
        seen_emails.add(email.lower())
        suggestions.append(
            {
                "name": name,
                "email": email,
                "language": detect_language(text),
                "match_score": len(hits),
                "tags": hits[:8],
                "offers_count": 0,
                "source": "hn_hiring",
            }
        )
        if len(suggestions) >= max_n:
            break

    suggestions.sort(key=lambda s: -s["match_score"])
    _cache_put(cache_key, suggestions)
    return suggestions
