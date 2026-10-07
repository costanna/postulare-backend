"""Fuentes gratuitas de ofertas, sin clave: Remotive, RemoteOK y Arbeitnow.

Son feeds públicos pensados para consumo casual (solo remoto / Europa).
Se normalizan al mismo formato interno que Adzuna/InfoJobs para que el
scoring, los duplicados y los filtros existentes funcionen sin cambios.

Ninguna permite "aplicar" por API: devuelven la URL de la oferta para que
la persona aplique en el portal. La automatización de Postulare es interna:
convertir a candidatura + carta plantilla + kit de envío (ver apply_pack).
"""
import html
import re

import httpx

from app.core.config import settings
from app.services.job_search import JobSearchError, _cache_get, _cache_put

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTEOK_URL = "https://remoteok.com/api"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"

MAX_RESULTS = 20
_TIMEOUT = 10.0


def free_boards_enabled() -> bool:
    return bool(settings.FREE_BOARDS_ENABLED)


def _strip_html(text: str | None, limit: int = 4000) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:limit] or None


def _clip(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    return text[:limit] if text else None


def _normalize_remotive(item: dict) -> dict:
    return {
        "source": "remotive",
        "external_id": str(item.get("id")),
        "title": (item.get("title") or "").strip()[:500],
        "company_name": _clip(item.get("company_name"), 255),
        "location": _clip(item.get("candidate_required_location") or "Remoto", 255),
        "description": _strip_html(item.get("description")),
        "salary_range": _clip(item.get("salary"), 100),
        "url": _clip(item.get("url"), 1000),
    }


def _normalize_remoteok(item: dict) -> dict:
    company = item.get("company")
    location = item.get("location") or item.get("candidate_required_location") or "Remoto"
    link = item.get("url") or item.get("apply_url")
    if not link and item.get("slug"):
        link = f"https://remoteok.com/remote-jobs/{item.get('slug')}"
    return {
        "source": "remoteok",
        "external_id": str(item.get("id")),
        "title": (item.get("position") or item.get("title") or "").strip()[:500],
        "company_name": _clip(company, 255),
        "location": _clip(location, 255),
        "description": _strip_html(item.get("description")),
        "salary_range": _clip(item.get("salary"), 100),
        "url": _clip(link, 1000),
    }


def _normalize_arbeitnow(item: dict) -> dict:
    slug = item.get("slug")
    link = item.get("url") or (f"https://www.arbeitnow.com/jobs/{slug}" if slug else None)
    # location puede venir como "Berlin" o como lista; toleramos ambos.
    location = item.get("location")
    if isinstance(location, list):
        location = ", ".join(str(p) for p in location if p) or None
    return {
        "source": "arbeitnow",
        "external_id": str(slug or item.get("id")),
        "title": (item.get("title") or "").strip()[:500],
        "company_name": _clip(item.get("company_name"), 255),
        "location": _clip(location, 255),
        "description": _strip_html(item.get("description")),
        "salary_range": _clip(item.get("salary"), 100),
        "url": _clip(link, 1000),
    }


def _matches_query(text: str, query_words: list[str]) -> bool:
    if not query_words:
        return True
    lowered = text.lower()
    return any(word in lowered for word in query_words)


def search_remotive(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """Remoto tech, sin clave. Filtra en local por palabras de la consulta."""
    cache_key = ("remotive", query, max_results)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        response = httpx.get(REMOTIVE_URL, params={"search": query}, timeout=_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise JobSearchError(f"Error consultando Remotive: {exc}") from exc
    words = [w.lower() for w in re.findall(r"[\w+#.]+", query or "")]
    offers = []
    for item in payload.get("jobs", [])[: max_results * 3]:
        offer = _normalize_remotive(item)
        if not offer["title"]:
            continue
        haystack = f"{offer['title']} {offer['description'] or ''}"
        if _matches_query(haystack, words):
            offers.append(offer)
        if len(offers) >= max_results:
            break
    _cache_put(cache_key, offers)
    return offers


def search_remoteok(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """Remoto general, sin clave. Exige User-Agent propio según sus términos."""
    cache_key = ("remoteok", query, max_results)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        response = httpx.get(
            REMOTEOK_URL,
            headers={"User-Agent": "Postulare/1.0 (job search; contact: postulare.app)"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise JobSearchError(f"Error consultando RemoteOK: {exc}") from exc
    items = payload if isinstance(payload, list) else payload.get("jobs", [])
    # El primer elemento a veces es un aviso legal, no una oferta.
    items = [i for i in items if isinstance(i, dict) and i.get("id") and (i.get("position") or i.get("title"))]
    words = [w.lower() for w in re.findall(r"[\w+#.]+", query or "")]
    offers = []
    for item in items:
        offer = _normalize_remoteok(item)
        if not offer["title"]:
            continue
        haystack = f"{offer['title']} {offer['description'] or ''}"
        if _matches_query(haystack, words):
            offers.append(offer)
        if len(offers) >= max_results:
            break
    _cache_put(cache_key, offers)
    return offers


def search_arbeitnow(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """Europa / visa-sponsorship, sin clave. El feed es global: filtra en local."""
    cache_key = ("arbeitnow", query, max_results)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        response = httpx.get(ARBEITNOW_URL, timeout=_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise JobSearchError(f"Error consultando Arbeitnow: {exc}") from exc
    items = payload.get("data", []) if isinstance(payload, dict) else []
    words = [w.lower() for w in re.findall(r"[\w+#.]+", query or "")]
    offers = []
    for item in items:
        if not isinstance(item, dict):
            continue
        offer = _normalize_arbeitnow(item)
        if not offer["title"]:
            continue
        haystack = f"{offer['title']} {offer['description'] or ''}"
        if _matches_query(haystack, words):
            offers.append(offer)
        if len(offers) >= max_results:
            break
    _cache_put(cache_key, offers)
    return offers


def search_free_boards(query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    """Las tres fuentes gratuitas juntas. Si una falla se sigue con las demás."""
    offers: list[dict] = []
    failures: list[Exception] = []
    for search in (search_remotive, search_remoteok, search_arbeitnow):
        try:
            offers.extend(search(query, max_results=max_results))
        except JobSearchError as exc:
            failures.append(exc)
    if failures and not offers:
        raise failures[0]
    return offers
