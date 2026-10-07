"""Fuentes gratuitas: normalización y tolerancia a fallos. Sin llamadas reales."""
import pytest

import app.services.free_boards as free_boards
from app.services.free_boards import (
    _normalize_arbeitnow,
    _normalize_remoteok,
    _normalize_remotive,
    search_free_boards,
)
from app.services.job_search import JobSearchError


def test_normalize_remotive():
    offer = _normalize_remotive(
        {
            "id": 123,
            "title": "Python Developer",
            "company_name": "Acme",
            "candidate_required_location": "Worldwide",
            "description": "<p>Hola <b>mundo</b></p>",
            "salary": "$50k",
            "url": "https://remotive.com/x",
        }
    )
    assert offer["source"] == "remotive"
    assert offer["external_id"] == "123"
    assert offer["description"] == "Hola mundo"
    assert offer["location"] == "Worldwide"


def test_normalize_remoteok():
    offer = _normalize_remoteok({"id": 9, "position": "Frontend Dev", "company": "Foo", "location": "Remote"})
    assert offer["source"] == "remoteok"
    assert offer["title"] == "Frontend Dev"


def test_normalize_arbeitnow_builds_url_from_slug():
    offer = _normalize_arbeitnow({"slug": "dev-berlin-1", "title": "Dev", "company_name": "Bar"})
    assert offer["source"] == "arbeitnow"
    assert "dev-berlin-1" in (offer["url"] or "")
    assert offer["external_id"] == "dev-berlin-1"


def test_search_free_boards_returns_partial_results(monkeypatch):
    def boom(query, max_results=20):
        raise JobSearchError("caído")

    good = [{"source": "remoteok", "external_id": "1", "title": "Dev"}]
    monkeypatch.setattr(free_boards, "search_remotive", boom)
    monkeypatch.setattr(free_boards, "search_remoteok", lambda query, max_results=20: good)
    monkeypatch.setattr(free_boards, "search_arbeitnow", boom)
    assert search_free_boards("python") == good


def test_search_free_boards_raises_when_all_fail(monkeypatch):
    def boom(query, max_results=20):
        raise JobSearchError("caído")

    monkeypatch.setattr(free_boards, "search_remotive", boom)
    monkeypatch.setattr(free_boards, "search_remoteok", boom)
    monkeypatch.setattr(free_boards, "search_arbeitnow", boom)
    with pytest.raises(JobSearchError):
        search_free_boards("python")


def test_search_includes_free_boards_when_enabled(client, auth_headers, monkeypatch):
    from app.core.config import settings

    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    _set_profile(client, auth_headers)
    client.put("/matches/filters", headers=auth_headers, json={"work_mode": "remote"})
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [])
    monkeypatch.setattr(settings, "FREE_BOARDS_ENABLED", True)
    monkeypatch.setattr(
        matches_router,
        "search_free_boards",
        lambda query, max_results=20: [
            {
                "source": "remotive",
                "external_id": "r1",
                "title": "Python Developer Remoto",
                "company_name": "Remota",
                "location": "Remoto",
                "description": "Python y FastAPI en remoto.",
                "salary_range": None,
                "url": "https://example.com/r1",
            }
        ],
    )
    assert client.post("/matches/search", headers=auth_headers).status_code == 200
    companies = [m["job_offer"]["company_name"] for m in client.get("/matches", headers=auth_headers).json()]
    assert companies == ["Remota"]
