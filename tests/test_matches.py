"""Tests del modulo de matching. Nunca llaman a la API real de Adzuna:
search_job_offers se sustituye por datos simulados con monkeypatch."""
import app.routers.matches as matches_router
from tests.conftest import register_and_login

FAKE_OFFERS = [
    {
        "source": "adzuna",
        "external_id": "1",
        "title": "Junior Full Stack Developer (Angular + Python)",
        "company_name": "TechCorp",
        "location": "Barcelona, España",
        "description": "Buscamos perfil junior con Angular, Python y FastAPI.",
        "salary_range": "24.000 - 28.000",
        "url": "https://example.com/jobs/1",
    },
    {
        "source": "adzuna",
        "external_id": "2",
        "title": "Senior Java Backend Engineer",
        "company_name": "OtherCorp",
        "location": "Madrid, España",
        "description": "Java, Spring Boot, microservicios.",
        "salary_range": "45.000 - 55.000",
        "url": "https://example.com/jobs/2",
    },
]


def _set_profile(client, headers):
    client.patch(
        "/profile",
        headers=headers,
        json={
            "skills": ["Angular", "Python", "FastAPI"],
            "location": "Barcelona",
            "desired_position": "Junior Full Stack Developer",
            "seniority": "junior",
        },
    )


def test_search_requires_complete_profile(client, auth_headers):
    response = client.post("/matches/search", headers=auth_headers)
    assert response.status_code == 400


def test_search_creates_matches_scored_and_sorted(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None: FAKE_OFFERS)

    response = client.post("/matches/search", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["fetched"] == 2
    assert body["new_matches"] == 2

    matches = client.get("/matches", headers=auth_headers).json()
    assert len(matches) == 2
    # El primero debe ser el mas afin (mas skills + seniority + ubicacion coinciden)
    assert matches[0]["job_offer"]["title"].startswith("Junior Full Stack")
    assert matches[0]["score"] > matches[1]["score"]
    assert matches[0]["status"] == "new"


def test_search_is_rate_limited(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None: FAKE_OFFERS)

    first = client.post("/matches/search", headers=auth_headers)
    assert first.status_code == 200

    second = client.post("/matches/search", headers=auth_headers)
    assert second.status_code == 429


def test_search_propagates_provider_error_as_502(client, auth_headers, monkeypatch):
    from app.services.job_search import JobSearchError

    _set_profile(client, auth_headers)

    def boom(query, location=None):
        raise JobSearchError("fallo simulado")

    monkeypatch.setattr(matches_router, "search_job_offers", boom)

    response = client.post("/matches/search", headers=auth_headers)
    assert response.status_code == 502


def test_convert_match_creates_application(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None: FAKE_OFFERS)
    client.post("/matches/search", headers=auth_headers)

    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]
    response = client.post(f"/matches/{match_id}/convert", headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["status"] == "saved"

    matches = client.get("/matches", headers=auth_headers).json()
    converted = next(m for m in matches if m["id"] == match_id)
    assert converted["status"] == "converted"


def test_dismiss_match(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None: FAKE_OFFERS)
    client.post("/matches/search", headers=auth_headers)

    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]
    response = client.post(f"/matches/{match_id}/dismiss", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"


def test_user_cannot_convert_another_users_match(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None: FAKE_OFFERS)
    client.post("/matches/search", headers=auth_headers)
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]

    other_headers = register_and_login(client, email="other@example.com")
    response = client.post(f"/matches/{match_id}/convert", headers=other_headers)
    assert response.status_code == 404
