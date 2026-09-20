"""InfoJobs como segunda fuente de ofertas. Nunca llaman a la API real: httpx.get se simula."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import app.services.infojobs as infojobs
from app.core.config import settings
from app.models.enums import Seniority
from app.services.job_search import JobSearchError, clear_search_cache
from app.services.infojobs import search_infojobs
from tests.conftest import register_and_login
from tests.test_search_filters import PROFILE


def _item(id_="ij1", title="Desarrollador Angular Junior", **extra):
    return {
        "id": id_,
        "title": title,
        "city": "Sabadell",
        "province": {"id": 9, "value": "Barcelona"},
        "author": {"id": "a", "name": "Acme SL"},
        "link": f"https://www.infojobs.net/oferta/{id_}",
        "requirementMin": "Angular y TypeScript",
        "category": {"id": 1, "value": "Informática y telecomunicaciones"},
        "salaryDescription": "30.000€ - 35.000€ Bruto/año",
        "published": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


class FakeInfoJobs:
    def __init__(self, offers=None, status=200, reject_province=False):
        self.offers, self.status, self.reject_province = offers or [], status, reject_province
        self.calls: list[dict] = []

    def __call__(self, url, params=None, auth=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "params": dict(params or {}), "auth": auth})
        request = httpx.Request("GET", url)
        if self.reject_province and "province" in (params or {}):
            return httpx.Response(400, json={"error": "province"}, request=request)
        return httpx.Response(self.status, json={"offers": self.offers}, request=request)


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "INFOJOBS_CLIENT_ID", "cid")
    monkeypatch.setattr(settings, "INFOJOBS_CLIENT_SECRET", "secret")
    clear_search_cache()


def _install(monkeypatch, fake):
    monkeypatch.setattr(httpx, "get", fake)
    return fake


def test_it_is_disabled_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "INFOJOBS_CLIENT_ID", "")
    assert infojobs.infojobs_enabled() is False
    with pytest.raises(JobSearchError):
        search_infojobs("python")


def test_request_uses_basic_credentials_query_province_and_limits(configured, monkeypatch):
    fake = _install(monkeypatch, FakeInfoJobs([_item()]))

    search_infojobs("Desarrollador Full Stack Junior Python Angular Java", "Barcelona, Catalunya", max_days_old=7)

    call = fake.calls[0]
    assert call["url"] == "https://api.infojobs.net/api/9/offer"
    assert call["auth"] == ("cid", "secret")
    assert call["params"]["q"] == "Desarrollador Full Stack Junior"
    assert call["params"]["province"] == "barcelona"
    assert call["params"]["sinceDate"] == "_7_DAYS"
    assert call["params"]["maxResults"] == 30


@pytest.mark.parametrize("location,expected", [("A Coruña", "a-coruna"), ("Madrid", "madrid"), ("Las Palmas, Canarias", "las-palmas")])
def test_province_keys_are_normalized(location, expected):
    assert infojobs._province_key(location) == expected


@pytest.mark.parametrize("days,expected", [(1, "_24_HOURS"), (7, "_7_DAYS"), (14, "_15_DAYS"), (30, None), (None, None)])
def test_recency_maps_to_the_api_windows(days, expected):
    assert infojobs._since_date(days) == expected


def test_offers_are_normalized_to_the_internal_format(configured, monkeypatch):
    _install(monkeypatch, FakeInfoJobs([_item()]))

    [offer] = search_infojobs("angular", "Barcelona")

    assert offer["source"] == "infojobs" and offer["external_id"] == "ij1"
    assert offer["title"] == "Desarrollador Angular Junior"
    assert offer["company_name"] == "Acme SL"
    assert offer["location"] == "Sabadell, Barcelona"
    assert offer["salary_range"] == "30.000€ - 35.000€ Bruto/año"
    assert offer["url"] == "https://www.infojobs.net/oferta/ij1"
    assert "Angular y TypeScript" in offer["description"] and "Informática" in offer["description"]
    assert "published" not in offer


def test_missing_optional_fields_do_not_break_normalization(configured, monkeypatch):
    _install(monkeypatch, FakeInfoJobs([{"id": 5, "title": "Programador"}]))
    [offer] = search_infojobs("programador")
    assert offer["company_name"] is None and offer["location"] is None and offer["description"] is None
    assert offer["external_id"] == "5"


def test_excluded_levels_and_words_are_filtered_locally(configured, monkeypatch):
    offers = [_item("a", "Desarrollador Angular Junior"), _item("b", "Senior Angular Developer"), _item("c", "Angular con PHP")]
    _install(monkeypatch, FakeInfoJobs(offers))

    result = search_infojobs("angular", seniority=Seniority.junior, exclude="php")

    assert [o["external_id"] for o in result] == ["a"]


def test_old_offers_are_dropped_when_a_max_age_is_set(configured, monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    _install(monkeypatch, FakeInfoJobs([_item("new"), _item("old", published=old)]))

    assert [o["external_id"] for o in search_infojobs("angular", max_days_old=30)] == ["new"]


def test_a_location_that_is_not_a_province_falls_back_to_a_national_search(configured, monkeypatch):
    fake = _install(monkeypatch, FakeInfoJobs([_item()], reject_province=True))
    calls = []

    result = search_infojobs("angular", "Sant Cugat", before_request=lambda: calls.append(1))

    assert len(fake.calls) == 2 and "province" not in fake.calls[1]["params"]
    assert len(calls) == 2
    assert len(result) == 1


def test_other_http_errors_are_not_retried_and_become_search_errors(configured, monkeypatch):
    fake = _install(monkeypatch, FakeInfoJobs(status=401))
    with pytest.raises(JobSearchError):
        search_infojobs("angular", "Barcelona")
    assert len(fake.calls) == 1


def test_malformed_json_is_a_search_error(configured, monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: httpx.Response(200, content=b"<html>", request=httpx.Request("GET", "https://x"))
    )
    with pytest.raises(JobSearchError):
        search_infojobs("angular")


def test_identical_searches_are_served_from_cache_without_calling_again(configured, monkeypatch):
    fake = _install(monkeypatch, FakeInfoJobs([_item()]))
    calls = []
    search_infojobs("angular", "Barcelona", before_request=lambda: calls.append(1))
    search_infojobs("angular", "Barcelona", before_request=lambda: calls.append(1))
    assert len(fake.calls) == 1 and len(calls) == 1


# --- Integración en la búsqueda ---------------------------------------------------------


def _adzuna_result(id_, title, company):
    return {
        "id": id_, "title": title, "company": {"display_name": company}, "location": {"display_name": "Barcelona"},
        "description": "Angular", "redirect_url": f"https://adzuna/{id_}",
    }


def _router(monkeypatch, adzuna, infojobs_fake):
    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(settings, "ADZUNA_APP_KEY", "key")

    def dispatch(url, params=None, **kwargs):
        request = httpx.Request("GET", url)
        if "infojobs" in url:
            return infojobs_fake(url, params=params, **kwargs)
        if adzuna is None:
            return httpx.Response(500, request=request)
        return httpx.Response(200, json={"results": adzuna}, request=request)

    monkeypatch.setattr(httpx, "get", dispatch)


def _search(client, headers):
    client.patch("/profile", headers=headers, json=PROFILE)
    return client.post("/matches/search", headers=headers)


def test_search_merges_both_sources(client, auth_headers, configured, monkeypatch):
    _router(monkeypatch, [_adzuna_result(1, "Angular Dev", "Alfa")], FakeInfoJobs([_item("x", "Angular Junior", author={"name": "Beta"})]))

    response = _search(client, auth_headers)

    assert response.status_code == 200 and response.json()["new_matches"] == 2
    sources = {m["job_offer"]["source"] for m in client.get("/matches", headers=auth_headers).json()}
    assert sources == {"adzuna", "infojobs"}


def test_the_same_offer_on_both_sites_is_kept_once(client, auth_headers, configured, monkeypatch):
    same_title, same_company = "Angular Dev", "Acme SL"
    _router(
        monkeypatch,
        [_adzuna_result(1, same_title, same_company)],
        FakeInfoJobs([_item("x", same_title, city="Barcelona")]),
    )
    result = _search(client, auth_headers).json()
    assert result["new_matches"] == 1 and result["skipped_duplicates"] == 1


def test_if_one_source_fails_the_other_still_answers(client, auth_headers, configured, monkeypatch):
    _router(monkeypatch, None, FakeInfoJobs([_item()]))
    response = _search(client, auth_headers)
    assert response.status_code == 200 and response.json()["new_matches"] == 1


def test_if_every_source_fails_the_search_is_a_502(client, auth_headers, configured, monkeypatch):
    _router(monkeypatch, None, FakeInfoJobs(status=500))
    assert _search(client, auth_headers).status_code == 502


def test_infojobs_alone_works_when_adzuna_is_not_configured(client, auth_headers, configured, monkeypatch):
    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "")
    monkeypatch.setattr(httpx, "get", FakeInfoJobs([_item()]))
    response = _search(client, auth_headers)
    assert response.status_code == 200 and response.json()["new_matches"] == 1


def test_without_infojobs_credentials_it_is_never_called(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "INFOJOBS_CLIENT_ID", "")
    clear_search_cache()
    fake = FakeInfoJobs([_item()])
    _router(monkeypatch, [_adzuna_result(1, "Angular Dev", "Alfa")], fake)
    assert _search(client, auth_headers).status_code == 200
    assert fake.calls == []


def test_infojobs_has_its_own_daily_cap_and_adzuna_keeps_working(client, auth_headers, configured, monkeypatch):
    monkeypatch.setattr(settings, "INFOJOBS_DAILY_LIMIT", 1)
    fake = FakeInfoJobs([_item()])
    _router(monkeypatch, [_adzuna_result(1, "Angular Dev", "Alfa")], fake)

    first = _search(client, auth_headers)
    other = register_and_login(client, email="otra@example.com")
    clear_search_cache()
    second = _search(client, other)

    assert first.status_code == second.status_code == 200
    assert len(fake.calls) == 1
    assert second.json()["new_matches"] == 1
