"""Cliente de la API oficial de InfoJobs (segunda fuente de ofertas, opcional).

Se activa solo si hay INFOJOBS_CLIENT_ID e INFOJOBS_CLIENT_SECRET (se obtienen registrando una
aplicación en https://developer.infojobs.net). La autenticación es HTTP Basic con esas credenciales.

El listado de ofertas no trae la descripción completa: se construye un texto corto con el requisito
mínimo, la categoría y las condiciones, suficiente para puntuar por palabras clave. InfoJobs no tiene
un filtro para excluir palabras, así que las exclusiones (otros niveles, palabras del usuario) se
aplican aquí, sobre los resultados.
"""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.models.enums import Seniority
from app.services.duplicates import normalize
from app.services.job_search import JobSearchError, _cache_get, _cache_put, excluded_words
from app.services.scoring import _mentions

INFOJOBS_URL = "https://api.infojobs.net/api/9/offer"
MAX_QUERY_WORDS = 4
MAX_RESULTS = 30


def infojobs_enabled() -> bool:
    return bool(settings.INFOJOBS_CLIENT_ID and settings.INFOJOBS_CLIENT_SECRET)


def _since_date(max_days_old: int | None) -> str | None:
    if not max_days_old:
        return None
    if max_days_old <= 1:
        return "_24_HOURS"
    if max_days_old <= 7:
        return "_7_DAYS"
    if max_days_old <= 15:
        return "_15_DAYS"
    return None


def _province_key(location: str | None) -> str | None:
    """"Barcelona, Catalunya" -> "barcelona"; "A Coruña" -> "a-coruna" (así se escriben las provincias en la API)."""
    first = (location or "").split(",")[0]
    key = normalize(first).replace(" ", "-")
    return key or None


def _value(item: dict, field: str) -> str | None:
    node = item.get(field)
    return node.get("value") if isinstance(node, dict) else None


def _clip(value: str | None, limit: int) -> str | None:
    return value[:limit] if value else None


def _normalize_offer(item: dict) -> dict:
    city, province = item.get("city"), _value(item, "province")
    location = ", ".join(part for part in (city, province) if part) or None
    extras = [
        item.get("requirementMin"),
        _value(item, "category"),
        _value(item, "subcategory"),
        _value(item, "experienceMin"),
        _value(item, "contractType"),
        _value(item, "workDay"),
        _value(item, "teleworking"),
    ]
    author = item.get("author") or {}
    return {
        "source": "infojobs",
        "external_id": str(item.get("id")),
        "title": (item.get("title") or "").strip()[:500],
        "company_name": _clip(author.get("name"), 255),
        "location": _clip(location, 255),
        "description": ". ".join(part for part in extras if part) or None,
        "salary_range": _clip(item.get("salaryDescription"), 100),
        "url": _clip(item.get("link"), 1000),
        "published": item.get("published"),
    }


def _is_recent(published: str | None, max_days_old: int | None) -> bool:
    if not max_days_old or not published:
        return True
    try:
        when = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - when <= timedelta(days=max_days_old)


class _RejectedParams(JobSearchError):
    """La API rechazó la consulta (400/404/422): típicamente porque la provincia no existe."""


def _fetch(params: dict, before_request: Callable[[], None] | None) -> list[dict]:
    if before_request is not None:
        before_request()
    try:
        response = httpx.get(
            INFOJOBS_URL,
            params=params,
            auth=(settings.INFOJOBS_CLIENT_ID, settings.INFOJOBS_CLIENT_SECRET),
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json().get("offers") or []
    except httpx.HTTPStatusError as exc:
        error = _RejectedParams if exc.response.status_code in (400, 404, 422) else JobSearchError
        raise error(f"Error consultando InfoJobs: {exc}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise JobSearchError(f"Error consultando InfoJobs: {exc}") from exc


def search_infojobs(
    query: str,
    location: str | None = None,
    seniority: Seniority | None = None,
    *,
    exclude: str | None = None,
    exclude_other_levels: bool = True,
    max_days_old: int | None = None,
    before_request: Callable[[], None] | None = None,
) -> list[dict]:
    """Ofertas de InfoJobs normalizadas al formato interno. `before_request` se llama antes de cada llamada real."""
    if not infojobs_enabled():
        raise JobSearchError("InfoJobs no está configurado: define INFOJOBS_CLIENT_ID e INFOJOBS_CLIENT_SECRET")

    params: dict = {
        "q": " ".join(query.split()[:MAX_QUERY_WORDS]),
        "maxResults": MAX_RESULTS,
        "order": "relevancia-desc",
    }
    since = _since_date(max_days_old)
    if since:
        params["sinceDate"] = since
    province = _province_key(location)

    excluded = excluded_words(seniority, exclude, exclude_other_levels)
    cache_key = ("infojobs", *sorted(params.items()), province, tuple(excluded), max_days_old)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        raw = _fetch({**params, "province": province} if province else params, before_request)
    except _RejectedParams:
        if not province:
            raise
        # Una "ubicación" que no es una provincia (un barrio, un pueblo) la rechaza la API: se busca en toda España
        raw = _fetch(params, before_request)

    offers = []
    for item in raw:
        offer = _normalize_offer(item)
        text = f"{offer['title']} {offer['description'] or ''}".lower()
        if any(_mentions(word, text) for word in excluded):
            continue
        if not _is_recent(offer.pop("published"), max_days_old):
            continue
        offers.append(offer)

    _cache_put(cache_key, offers)
    return offers
