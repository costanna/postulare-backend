"""Cliente de la API de Adzuna para buscar ofertas de empleo.

Usa siempre una API oficial (nunca scraping de LinkedIn/InfoJobs). Adzuna
requiere registrarse gratis para obtener ADZUNA_APP_ID y ADZUNA_APP_KEY:
https://developer.adzuna.com/
"""
import httpx

from app.core.config import settings

ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"


class JobSearchError(Exception):
    """Fallo al consultar el proveedor de ofertas (config ausente o error de red/API)."""


def search_job_offers(query: str, location: str | None = None, results_per_page: int = 20) -> list[dict]:
    """Busca ofertas en Adzuna y las devuelve normalizadas al formato interno de job_offers."""
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY:
        raise JobSearchError(
            "Adzuna no está configurado: define ADZUNA_APP_ID y ADZUNA_APP_KEY en las variables de entorno"
        )

    url = f"{ADZUNA_BASE_URL}/{settings.ADZUNA_COUNTRY}/search/1"
    params = {
        "app_id": settings.ADZUNA_APP_ID,
        "app_key": settings.ADZUNA_APP_KEY,
        "results_per_page": results_per_page,
        "what": query,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location

    try:
        response = httpx.get(url, params=params, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise JobSearchError(f"Error consultando la API de ofertas: {exc}") from exc

    payload = response.json()
    return [_normalize_adzuna_result(item) for item in payload.get("results", [])]


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
