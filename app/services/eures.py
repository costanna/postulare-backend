"""Ofertas en España vía EURES (portal europeo de empleo), sin clave.

Usa el endpoint público del propio portal (`locationCodes=["es"]`), que
agrega ofertas de toda Europa y también las de Empléate/SEPE en España
(`source: "empleate"`). Sin cuota ni registro: solo caché interna.

No trae salario estructurado en la búsqueda (solo en el detalle, que no se
consulta para no multiplicar las llamadas) ni permite aplicar por API:
devuelve la URL del detalle en el portal para aplicar allí.
"""
import html
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.models.enums import Seniority
from app.services.job_search import JobSearchError, _cache_get, _cache_put, excluded_words
from app.services.scoring import _mentions

EURES_SEARCH_URL = "https://europa.eu/eures/api/jv-searchengine/public/jv-search/search"
EURES_PORTAL_URL = "https://europa.eu/eures/portal/jv-se/jv-details/{id}?lang=es"

MAX_RESULTS = 20
_TIMEOUT = 10.0

# NUTS-2 (4 primeros caracteres del código) -> comunidad autónoma. La búsqueda
# solo devuelve códigos NUTS, no nombres de ciudad: la región es lo más
# preciso que se puede mostrar sin pedir el detalle de cada oferta.
_NUTS2 = {
    "ES11": "Galicia",
    "ES12": "Asturias",
    "ES13": "Cantabria",
    "ES21": "País Vasco",
    "ES22": "Navarra",
    "ES23": "La Rioja",
    "ES24": "Aragón",
    "ES30": "Madrid",
    "ES41": "Castilla y León",
    "ES42": "Castilla-La Mancha",
    "ES43": "Extremadura",
    "ES51": "Cataluña",
    "ES52": "C. Valenciana",
    "ES53": "Baleares",
    "ES61": "Andalucía",
    "ES62": "Murcia",
    "ES63": "Ceuta",
    "ES64": "Melilla",
    "ES70": "Canarias",
}

# Sin tildes ni mayúsculas: la ubicación del perfil se normaliza igual.
_SPAIN_MARKERS = {
    "espana",
    "spain",
    "catalun",
    "madrid",
    "barcelona",
    "valencia",
    "sevilla",
    "zaragoza",
    "malaga",
    "murcia",
    "bilbao",
    "alicante",
    "cordoba",
    "valladolid",
    "vigo",
    "gijon",
    "hospitalet",
    "coruna",
    "vitoria",
    "granada",
    "oviedo",
    "pamplona",
    "almeria",
    "burgos",
    "santander",
    "castellon",
    "getafe",
    "cartagena",
    "terrassa",
    "sabadell",
    "tenerife",
    "palmas",
    "girona",
    "gerona",
    "lleida",
    "tarragona",
    "caceres",
    "badajoz",
    "jaen",
    "huelva",
    "cadiz",
    "leon",
    "salamanca",
    "logrono",
    "andaluc",
    "galicia",
    "euskadi",
    "vasco",
    "aragon",
    "asturias",
    "cantabria",
    "castilla",
    "extremadura",
    "valenciana",
    "baleares",
    "canarias",
    "navarra",
    "rioja",
    "remoto",
    "remote",
    "teletrabajo",
}


def eures_enabled() -> bool:
    return bool(settings.EURES_ENABLED)


def _fold(text: str) -> str:
    folded = text.lower()
    for accented, plain in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"), ("ñ", "n")):
        folded = folded.replace(accented, plain)
    return folded


def is_spain_location(location: str | None) -> bool:
    """Sin ubicación se busca en toda España; con ubicación, solo si parece España."""
    if not location or not location.strip():
        return True
    folded = _fold(location)
    return any(marker in folded for marker in _SPAIN_MARKERS)


def _region_label(location_map: dict | None) -> str | None:
    if not isinstance(location_map, dict):
        return None
    codes: list[str] = []
    for value in location_map.values():
        if isinstance(value, list):
            codes.extend(str(code) for code in value)
    for code in codes:
        region = _NUTS2.get(code[:4].upper())
        if region:
            return f"{region}, España"
    if codes:
        return "España"
    return None


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


def _normalize_offer(item: dict) -> dict:
    employer = item.get("employer")
    company = employer.get("name") if isinstance(employer, dict) else None
    offer_id = str(item.get("id"))
    return {
        "source": "eures",
        "external_id": offer_id,
        "title": (item.get("title") or "").strip()[:500],
        "company_name": _clip(company, 255),
        "location": _clip(_region_label(item.get("locationMap")), 255),
        "description": _strip_html(item.get("description")),
        "salary_range": None,  # la búsqueda no lo trae estructurado
        "url": EURES_PORTAL_URL.format(id=offer_id)[:1000],
        "creation_ms": item.get("creationDate"),
    }


def _is_recent(creation_ms: int | float | None, max_days_old: int | None) -> bool:
    if not max_days_old or not creation_ms:
        return True
    try:
        when = datetime.fromtimestamp(float(creation_ms) / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return True
    return datetime.now(timezone.utc) - when <= timedelta(days=max_days_old)


def search_eures(
    query: str,
    seniority: Seniority | None = None,
    *,
    exclude: str | None = None,
    exclude_other_levels: bool = True,
    max_days_old: int | None = None,
    max_results: int = MAX_RESULTS,
) -> list[dict]:
    """Ofertas en España normalizadas al formato interno. EURES no excluye por
    palabras en el servidor: se filtra en local como con InfoJobs."""
    if not eures_enabled():
        raise JobSearchError("EURES no está activado: define EURES_ENABLED=true")

    excluded = excluded_words(seniority, exclude, exclude_other_levels)
    cache_key = ("eures", query, max_results, tuple(excluded), max_days_old)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        response = httpx.post(
            EURES_SEARCH_URL,
            json={
                "resultsPerPage": max_results,
                "page": 1,
                "sortSearch": "BEST_MATCH",
                "keywords": [{"keyword": query, "specificSearchCode": "EVERYWHERE"}],
                "publicationPeriod": None,
                "occupationUris": [],
                "skillUris": [],
                "requiredExperienceCodes": [],
                "positionScheduleCodes": [],
                "sectorCodes": [],
                "educationAndQualificationLevelCodes": [],
                "positionOfferingCodes": [],
                "locationCodes": ["es"],
                "euresFlagCodes": [],
                "otherBenefitsCodes": [],
                "requiredLanguages": [],
                "minNumberPost": None,
                "sessionId": "postulare",
                "requestLanguage": "es",
            },
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise JobSearchError(f"Error consultando EURES: {exc}") from exc

    offers = []
    for item in payload.get("jvs", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("title"):
            continue
        offer = _normalize_offer(item)
        text = f"{offer['title']} {offer['description'] or ''}".lower()
        if any(_mentions(word, text) for word in excluded):
            continue
        if not _is_recent(offer.pop("creation_ms"), max_days_old):
            continue
        offers.append(offer)

    _cache_put(cache_key, offers)
    return offers
