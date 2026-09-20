"""Filtros del usuario y caché del cliente de Adzuna (sin llamar a la API real)."""
import httpx
import pytest

from app.core.config import settings
from app.models.enums import Seniority
from app.services import job_search
from app.services.job_search import search_job_offers


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def adzuna_configured(monkeypatch):
    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "id-test")
    monkeypatch.setattr(settings, "ADZUNA_APP_KEY", "key-test")
    monkeypatch.setattr(settings, "ADZUNA_COUNTRY", "es")
    monkeypatch.setattr(settings, "ADZUNA_CACHE_MINUTES", 360)


def _capture_params(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        job_search.httpx,
        "get",
        lambda url, params, timeout: captured.update(params=params) or _FakeResponse({"results": []}),
    )
    return captured


def _count_calls(monkeypatch, payload=None):
    calls = []
    monkeypatch.setattr(
        job_search.httpx,
        "get",
        lambda url, params, timeout: calls.append(1) or _FakeResponse(payload or {"results": []}),
    )
    return calls


def test_search_merges_user_exclusions_with_the_seniority_ones(adzuna_configured, monkeypatch):
    captured = _capture_params(monkeypatch)

    search_job_offers("python", seniority=Seniority.junior, exclude="PHP, sap")

    words = captured["params"]["what_exclude"].split()
    assert {"senior", "php", "sap"} <= set(words)  # en minúsculas y sin comas
    assert len(words) == len(set(words))


def test_search_can_skip_the_automatic_level_exclusion(adzuna_configured, monkeypatch):
    captured = _capture_params(monkeypatch)

    search_job_offers("python", seniority=Seniority.junior, exclude_other_levels=False)

    assert "what_exclude" not in captured["params"]


def test_search_sends_max_days_old_and_custom_radius(adzuna_configured, monkeypatch):
    captured = _capture_params(monkeypatch)

    search_job_offers("python", location="Girona", radius_km=12, max_days_old=7)

    assert captured["params"]["max_days_old"] == 7
    assert captured["params"]["distance"] == 12


def test_identical_search_is_served_from_cache_without_calling_adzuna(adzuna_configured, monkeypatch):
    calls = _count_calls(monkeypatch, {"results": [{"id": 1, "title": "A"}]})
    before = []

    first = search_job_offers("python", before_request=lambda: before.append(1))
    second = search_job_offers("python", before_request=lambda: before.append(1))

    assert len(calls) == 1 and len(before) == 1  # la caché ni llama ni cuenta cuota
    assert first == second
    second[0]["title"] = "mutado"  # la caché devuelve copias: no se contamina
    assert search_job_offers("python")[0]["title"] == "A"


def test_different_filters_are_different_cache_entries(adzuna_configured, monkeypatch):
    calls = _count_calls(monkeypatch)

    search_job_offers("python")
    search_job_offers("python", location="Barcelona")
    search_job_offers("python", exclude="php")

    assert len(calls) == 3


def test_cache_entries_expire(adzuna_configured, monkeypatch):
    calls = _count_calls(monkeypatch)
    clock = {"now": 1000.0}
    monkeypatch.setattr(job_search.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(settings, "ADZUNA_CACHE_MINUTES", 10)

    search_job_offers("python")
    clock["now"] += 9 * 60
    search_job_offers("python")
    assert len(calls) == 1
    clock["now"] += 2 * 60  # 11 min desde la primera
    search_job_offers("python")
    assert len(calls) == 2


def test_cache_can_be_disabled(adzuna_configured, monkeypatch):
    calls = _count_calls(monkeypatch)
    monkeypatch.setattr(settings, "ADZUNA_CACHE_MINUTES", 0)

    search_job_offers("python")
    search_job_offers("python")

    assert len(calls) == 2


def test_before_request_can_abort_the_search(adzuna_configured, monkeypatch):
    monkeypatch.setattr(job_search.httpx, "get", lambda *a, **k: pytest.fail("no debería llamar a Adzuna"))

    def refuse():
        raise RuntimeError("tope alcanzado")

    with pytest.raises(RuntimeError):
        search_job_offers("python", before_request=refuse)


def test_http_errors_are_not_cached(adzuna_configured, monkeypatch):
    attempts = []

    def flaky(url, params, timeout):
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("sin red")
        return _FakeResponse({"results": []})

    monkeypatch.setattr(job_search.httpx, "get", flaky)

    with pytest.raises(job_search.JobSearchError):
        search_job_offers("python")
    assert search_job_offers("python") == []  # el fallo no quedó "cacheado"
    assert len(attempts) == 2
