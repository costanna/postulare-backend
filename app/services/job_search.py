"""Cliente de la API de Adzuna para buscar ofertas de empleo.

Usa siempre una API oficial (nunca scraping de LinkedIn/InfoJobs). Adzuna
requiere registrarse gratis para obtener ADZUNA_APP_ID y ADZUNA_APP_KEY:
https://developer.adzuna.com/
"""
import copy
import re
import time
from collections.abc import Callable

import httpx

from app.core.config import settings
from app.models.enums import Seniority

ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"

# Radio (km) alrededor de la ubicación del perfil. El de Adzuna por defecto
# es 5 km, que en Barcelona deja fuera todo el área metropolitana
# (L'Hospitalet, Sant Cugat, Badalona...): con 30 km hay el doble de ofertas.
SEARCH_RADIUS_KM = 30

# Cuántas skills entran en la consulta. Con más, la consulta se diluye.
MAX_QUERY_SKILLS = 5

# Skills que no distinguen un puesto de otro (herramientas transversales,
# metodologías, maquetación): aparecen en casi cualquier oferta de
# desarrollo y solo meten ruido en la consulta. Se siguen usando en el
# scoring, que sí las cuenta cuando aparecen en la oferta.
_GENERIC_SKILLS = {
    "git", "github", "gitlab", "jira", "scrum", "agile", "kanban", "ci/cd", "cicd",
    "testing", "rest", "rest api", "api", "apis", "html", "html5", "css", "css3", "mvc", "jwt",
}

# Palabras que, si aparecen en una oferta, indican otro nivel de experiencia.
# Se envían como `what_exclude`: para un perfil junior, quita del listado los
# "Senior ...", "Lead ...", "Manager ..." que de otro modo encabezan los
# resultados (relevancia por palabras, no por nivel).
_SENIORITY_EXCLUDE: dict[Seniority, str] = {
    Seniority.junior: "senior sr lead principal manager director head arquitecto architect",
    Seniority.mid: "trainee becario intern prácticas",
    Seniority.senior: "junior jr trainee becario intern prácticas",
}


class JobSearchError(Exception):
    """Fallo al consultar el proveedor de ofertas (config ausente o error de red/API)."""


def build_search_query(desired_position: str | None, skills: list[str] | None) -> str:
    """Construye la consulta de búsqueda a partir del perfil.

    Puesto deseado + las primeras skills que distinguen (en el orden en que
    el usuario las puso: las primeras son las que cuentan). Devuelve una
    cadena vacía si el perfil no da nada con lo que buscar.
    """
    terms: list[str] = []

    if desired_position:
        terms.extend(_role_words(desired_position))

    useful_skills = [s.strip() for s in (skills or []) if s and s.strip() and s.strip().lower() not in _GENERIC_SKILLS]
    for skill in useful_skills[:MAX_QUERY_SKILLS]:
        terms.extend(re.findall(r"[\w+#.]+", skill))

    seen: set[str] = set()
    unique = []
    for term in terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            unique.append(term)
    return " ".join(unique)


def _role_words(position: str) -> list[str]:
    # Las ofertas se publican en masculino o como "Desarrollador/a": un
    # "Desarrolladora" del perfil no encontraría casi ninguna.
    position = re.sub(r"\b(\w+dor)a\b", r"\1", position, flags=re.IGNORECASE)
    position = re.sub(r"\bingeniera\b", "ingeniero", position, flags=re.IGNORECASE)
    return re.findall(r"[\w+#.]+", position)


# Caché en memoria de búsquedas idénticas (mismos parámetros, misma ventana de
# tiempo): varias personas con perfil parecido, o la misma pulsando de nuevo,
# no gastan una llamada real a Adzuna cada vez. Se pierde al reiniciar el
# servicio (Render duerme el plan gratuito), lo cual es aceptable: es una
# optimización, la garantía de cuota es el tope diario global.
_CACHE_MAX_ENTRIES = 100
_cache: dict[tuple, tuple[float, list[dict]]] = {}


def clear_search_cache() -> None:
    _cache.clear()


def _cache_get(key: tuple) -> list[dict] | None:
    ttl = settings.ADZUNA_CACHE_MINUTES * 60
    if ttl <= 0:
        return None
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, offers = entry
    if time.monotonic() - stored_at > ttl:
        _cache.pop(key, None)
        return None
    return copy.deepcopy(offers)


def _cache_put(key: tuple, offers: list[dict]) -> None:
    if settings.ADZUNA_CACHE_MINUTES <= 0:
        return
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)
    _cache[key] = (time.monotonic(), copy.deepcopy(offers))


def search_job_offers(
    query: str,
    location: str | None = None,
    results_per_page: int = 20,
    seniority: Seniority | None = None,
    *,
    radius_km: int = SEARCH_RADIUS_KM,
    exclude: str | None = None,
    exclude_other_levels: bool = True,
    max_days_old: int | None = None,
    before_request: Callable[[], None] | None = None,
) -> list[dict]:
    """Busca ofertas en Adzuna y las devuelve normalizadas al formato interno de job_offers.

    `before_request` se invoca justo antes de una llamada REAL (nunca si la
    respuesta sale de la caché): ahí se aplica el tope diario global, que
    puede abortar la búsqueda lanzando una excepción.
    """
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY:
        raise JobSearchError(
            "Adzuna no está configurado: define ADZUNA_APP_ID y ADZUNA_APP_KEY en las variables de entorno"
        )

    search_params = {
        "results_per_page": results_per_page,
        # `what_or` (basta con que aparezca ALGUNA palabra), no `what` (deben
        # aparecer TODAS): la consulta junta el puesto deseado y varias
        # skills ("Junior Full Stack Developer Angular Python FastAPI SQL"),
        # y con `what` no existe casi ninguna oferta con todas esas palabras
        # (0 resultados contra la API real; con `what_or`, cientos). Adzuna
        # ordena por relevancia, así que arriba quedan las que más coinciden,
        # y el scoring propio (services/scoring.py) afina después.
        "what_or": query,
    }
    if location:
        search_params["where"] = location
        search_params["distance"] = radius_km
    if max_days_old:
        search_params["max_days_old"] = max_days_old

    excluded: list[str] = []
    if exclude_other_levels and seniority:
        excluded.extend(_SENIORITY_EXCLUDE.get(seniority, "").split())
    if exclude:
        excluded.extend(re.findall(r"[\w+#.]+", exclude))
    excluded = list(dict.fromkeys(word.lower() for word in excluded))
    if excluded:
        search_params["what_exclude"] = " ".join(excluded)

    cache_key = (settings.ADZUNA_COUNTRY, *sorted(search_params.items()))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if before_request is not None:
        before_request()

    url = f"{ADZUNA_BASE_URL}/{settings.ADZUNA_COUNTRY}/search/1"
    params = {
        "app_id": settings.ADZUNA_APP_ID,
        "app_key": settings.ADZUNA_APP_KEY,
        "content-type": "application/json",
        **search_params,
    }

    try:
        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise JobSearchError(f"Error consultando la API de ofertas: {exc}") from exc

    offers = [_normalize_adzuna_result(item) for item in payload.get("results", [])]
    _cache_put(cache_key, offers)
    return offers


def _normalize_adzuna_result(item: dict) -> dict:
    return {
        "source": "adzuna",
        "external_id": str(item.get("id")),
        "title": (item.get("title") or "").strip(),
        "company_name": (item.get("company") or {}).get("display_name"),
        "location": (item.get("location") or {}).get("display_name"),
        "description": item.get("description"),
        "salary_range": _format_salary(item),
        "url": item.get("redirect_url"),
    }


def _format_salary(item: dict) -> str | None:
    salary_min = item.get("salary_min")
    salary_max = item.get("salary_max")
    if not salary_min and not salary_max:
        return None
    if salary_min and salary_max and salary_min != salary_max:
        return f"{int(salary_min):,} - {int(salary_max):,}".replace(",", ".")
    value = salary_min or salary_max
    return f"{int(value):,}".replace(",", ".") if value else None
