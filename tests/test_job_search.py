"""Tests del cliente de Adzuna: forma de la petición y normalización de la respuesta.

test_matches.py sustituye search_job_offers entera, así que sin estos tests
la petición real a Adzuna no estaba cubierta por nada.
"""
import httpx
import pytest

from app.core.config import settings
from app.services import job_search
from app.services.job_search import JobSearchError, search_job_offers


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def adzuna_configured(monkeypatch):
    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "id-test")
    monkeypatch.setattr(settings, "ADZUNA_APP_KEY", "key-test")
    monkeypatch.setattr(settings, "ADZUNA_COUNTRY", "es")


def test_search_uses_what_or_so_any_word_matches(adzuna_configured, monkeypatch):
    # Regresión: con `what` Adzuna exige TODAS las palabras; un perfil normal
    # (puesto + 4-5 skills) devolvía 0 ofertas contra la API real.
    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse({"results": []})

    monkeypatch.setattr(job_search.httpx, "get", fake_get)

    search_job_offers("Junior Full Stack Developer Angular Python", location="Barcelona")

    assert captured["url"].endswith("/es/search/1")
    assert captured["params"]["what_or"] == "Junior Full Stack Developer Angular Python"
    assert "what" not in captured["params"]
    assert captured["params"]["where"] == "Barcelona"


def test_search_omits_where_without_location(adzuna_configured, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        job_search.httpx, "get", lambda url, params, timeout: captured.update(params=params) or _FakeResponse({"results": []})
    )

    search_job_offers("python")

    assert "where" not in captured["params"]


def test_search_normalizes_results(adzuna_configured, monkeypatch):
    payload = {
        "results": [
            {
                "id": 123,
                "title": "  Angular Developer ",
                "company": {"display_name": "Acme"},
                "location": {"display_name": "Barcelona"},
                "description": "Buscamos...",
                "salary_min": 30000,
                "salary_max": 34000,
                "redirect_url": "https://example.com/job/123",
            },
            {"id": 456, "title": "Sin datos"},
        ]
    }
    monkeypatch.setattr(job_search.httpx, "get", lambda url, params, timeout: _FakeResponse(payload))

    offers = search_job_offers("angular")

    assert offers[0] == {
        "source": "adzuna",
        "external_id": "123",
        "title": "Angular Developer",
        "company_name": "Acme",
        "location": "Barcelona",
        "description": "Buscamos...",
        "salary_range": "30.000 - 34.000",
        "url": "https://example.com/job/123",
    }
    assert offers[1]["company_name"] is None
    assert offers[1]["salary_range"] is None


def test_search_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "")
    monkeypatch.setattr(settings, "ADZUNA_APP_KEY", "")

    with pytest.raises(JobSearchError):
        search_job_offers("python")


def test_search_wraps_http_errors(adzuna_configured, monkeypatch):
    def boom(url, params, timeout):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(job_search.httpx, "get", boom)

    with pytest.raises(JobSearchError):
        search_job_offers("python")


# --- Consulta construida a partir del perfil ---------------------------------

from app.models.enums import Seniority  # noqa: E402
from app.services.job_search import build_search_query  # noqa: E402


def test_query_normalizes_feminine_role_to_the_form_offers_use():
    assert build_search_query("Desarrolladora Full Stack Junior", []) == "Desarrollador Full Stack Junior"
    assert build_search_query("Programadora Python", []) == "Programador Python"


def test_query_skips_generic_skills_and_keeps_user_order():
    skills = ["Git", "Python", "Jira", "Angular", "Scrum", "Java", "Spring Boot", "React", "TypeScript"]

    query = build_search_query("Full Stack Junior", skills)

    # Git/Jira/Scrum fuera; máximo 5 skills útiles (Python, Angular, Java, Spring Boot, React)
    assert query == "Full Stack Junior Python Angular Java Spring Boot React"


def test_query_dedupes_case_insensitively():
    assert build_search_query("Python Developer", ["python", "Angular"]) == "Python Developer Angular"


def test_query_is_empty_without_position_or_useful_skills():
    assert build_search_query(None, None) == ""
    assert build_search_query("", ["Git", "Scrum"]) == ""


def _capture_params(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        job_search.httpx, "get", lambda url, params, timeout: captured.update(params=params) or _FakeResponse({"results": []})
    )
    return captured


def test_search_excludes_senior_words_for_a_junior_profile(adzuna_configured, monkeypatch):
    captured = _capture_params(monkeypatch)

    search_job_offers("python", seniority=Seniority.junior)

    exclude = captured["params"]["what_exclude"].split()
    assert "senior" in exclude and "lead" in exclude
    assert "junior" not in exclude


def test_search_excludes_junior_words_for_a_senior_profile(adzuna_configured, monkeypatch):
    captured = _capture_params(monkeypatch)

    search_job_offers("python", seniority=Seniority.senior)

    assert "junior" in captured["params"]["what_exclude"].split()


def test_search_does_not_exclude_anything_without_seniority(adzuna_configured, monkeypatch):
    captured = _capture_params(monkeypatch)

    search_job_offers("python")

    assert "what_exclude" not in captured["params"]


def test_search_widens_radius_when_there_is_a_location(adzuna_configured, monkeypatch):
    captured = _capture_params(monkeypatch)

    search_job_offers("python", location="Barcelona")
    assert captured["params"]["distance"] == job_search.SEARCH_RADIUS_KM

    search_job_offers("python")
    assert "distance" not in captured["params"]
