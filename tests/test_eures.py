"""EURES-España: normalización, filtros locales y tolerancia a fallos. Sin llamadas reales."""
import time

import pytest

import app.services.eures as eures
from app.services.eures import (
    _normalize_offer,
    is_spain_location,
    search_eures,
)
from app.services.job_search import JobSearchError


def _item(**extra):
    base = {
        "id": "Tm9uZTEx",
        "title": "Desarrolladora Python",
        "description": "Python y FastAPI.<br>Jornada completa.",
        "employer": {"name": "Acme SL"},
        "locationMap": {"ES": ["ES511"]},
        "creationDate": int(time.time() * 1000),
    }
    base.update(extra)
    return base


def test_normalize_maps_nuts_to_region_and_builds_portal_url():
    offer = _normalize_offer(_item())
    assert offer["source"] == "eures"
    assert offer["external_id"] == "Tm9uZTEx"
    assert offer["company_name"] == "Acme SL"
    assert offer["location"] == "Cataluña, España"
    assert offer["url"] == "https://europa.eu/eures/portal/jv-se/jv-details/Tm9uZTEx?lang=es"
    assert offer["description"] == "Python y FastAPI. Jornada completa."
    assert offer["salary_range"] is None


def test_normalize_tolerates_missing_employer_and_location():
    offer = _normalize_offer(_item(employer=None, locationMap=None))
    assert offer["company_name"] is None
    assert offer["location"] is None


def test_normalize_unknown_nuts_falls_back_to_spain():
    offer = _normalize_offer(_item(locationMap={"ES": ["ES999"]}))
    assert offer["location"] == "España"


@pytest.mark.parametrize(
    "location,expected",
    [
        (None, True),
        ("", True),
        ("Barcelona", True),
        ("Madrid, España", True),
        ("A Coruña", True),
        ("Málaga", True),
        ("Remoto", True),
        ("Berlin", False),
        ("London, UK", False),
        ("Lisboa", False),
    ],
)
def test_is_spain_location(location, expected):
    assert is_spain_location(location) is expected


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _enable_eures(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "EURES_ENABLED", True)


def _mock_post(monkeypatch, payload):
    seen = {}

    def fake(url, json, timeout):
        seen["body"] = json
        return _Resp(payload)

    monkeypatch.setattr(eures.httpx, "post", fake)
    return seen


def test_search_sends_spain_filter_and_normalizes(monkeypatch):
    seen = _mock_post(monkeypatch, {"jvs": [_item()]})
    offers = search_eures("python")
    assert seen["body"]["locationCodes"] == ["es"]
    assert len(offers) == 1 and offers[0]["company_name"] == "Acme SL"


def test_search_drops_excluded_levels_locally(monkeypatch):
    from app.models.enums import Seniority

    _mock_post(
        monkeypatch,
        {"jvs": [_item(title="Senior Java Engineer", description="Java senior"), _item()]},
    )
    offers = search_eures("python", Seniority.junior)
    assert [o["title"] for o in offers] == ["Desarrolladora Python"]


def test_search_respects_max_days_old(monkeypatch):
    old_ms = int(time.time() * 1000) - 30 * 24 * 3600 * 1000
    _mock_post(monkeypatch, {"jvs": [_item(creationDate=old_ms), _item()]})
    assert len(search_eures("python", max_days_old=7)) == 1


def test_search_error_becomes_job_search_error(monkeypatch):
    import httpx

    def boom(url, json, timeout):
        raise httpx.ConnectError("caído")

    monkeypatch.setattr(eures.httpx, "post", boom)
    with pytest.raises(JobSearchError):
        search_eures("python")


def test_search_includes_eures_when_location_is_spain(client, auth_headers, monkeypatch):
    from app.core.config import settings

    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    _set_profile(client, auth_headers)  # ubicación: Barcelona
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [])
    monkeypatch.setattr(settings, "EURES_ENABLED", True)
    monkeypatch.setattr(
        matches_router,
        "search_eures",
        lambda query, seniority=None, **kw: [
            {
                "source": "eures",
                "external_id": "e1",
                "title": "Python Developer",
                "company_name": "Nórdica",
                "location": "Madrid, España",
                "description": "Python en Madrid.",
                "salary_range": None,
                "url": "https://example.com/e1",
            }
        ],
    )
    assert client.post("/matches/search", headers=auth_headers).status_code == 200
    companies = [m["job_offer"]["company_name"] for m in client.get("/matches", headers=auth_headers).json()]
    assert companies == ["Nórdica"]


def test_search_skips_eures_when_location_is_abroad(client, auth_headers, monkeypatch):
    from app.core.config import settings

    import app.routers.matches as matches_router

    client.patch("/profile", headers=auth_headers, json={"desired_position": "Dev", "skills": ["Python"]})
    client.put("/matches/filters", headers=auth_headers, json={"keywords": "python", "location": "Berlin"})
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [])
    monkeypatch.setattr(settings, "EURES_ENABLED", True)

    def fail(query, seniority=None, **kw):
        raise AssertionError("EURES no debería llamarse para Berlín")

    monkeypatch.setattr(matches_router, "search_eures", fail)
    assert client.post("/matches/search", headers=auth_headers).status_code == 200
