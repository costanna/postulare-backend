"""Filtros de búsqueda editables, tope diario global y límites por IP.

Nada de esto llama a la API real: httpx.get se sustituye por una respuesta simulada.
"""
import app.routers.matches as matches_router
from app.core.config import settings
from app.services import job_search
from tests.conftest import register_and_login

PROFILE = {
    "desired_position": "Desarrolladora Full Stack Junior",
    "skills": ["Python", "Angular", "Git", "Java"],
    "location": "Barcelona",
    "seniority": "junior",
}


def _set_profile(client, headers):
    client.patch("/profile", headers=headers, json=PROFILE)


# --- Filtros ---------------------------------------------------------------


def test_get_filters_defaults_show_the_automatic_query(client, auth_headers):
    _set_profile(client, auth_headers)

    body = client.get("/matches/filters", headers=auth_headers).json()

    assert body["filters"]["keywords"] is None
    assert body["filters"]["radius_km"] == 30
    assert body["filters"]["exclude_other_levels"] is True
    # Lo que se enviaría a Adzuna sin tocar nada (Git es genérica y se descarta)
    assert body["effective_query"] == "Desarrollador Full Stack Junior Python Angular Java"
    assert body["effective_location"] == "Barcelona"


def test_put_filters_persists_and_overrides_query_and_location(client, auth_headers):
    _set_profile(client, auth_headers)

    saved = client.put(
        "/matches/filters",
        headers=auth_headers,
        json={"keywords": "  angular   react ", "location": "Girona", "radius_km": 50, "min_score": 40},
    ).json()

    assert saved["effective_query"] == "angular react"  # espacios colapsados
    assert saved["effective_location"] == "Girona"
    again = client.get("/matches/filters", headers=auth_headers).json()
    assert again["filters"]["radius_km"] == 50
    assert again["filters"]["min_score"] == 40


def test_blank_filters_fall_back_to_automatic(client, auth_headers):
    _set_profile(client, auth_headers)
    client.put("/matches/filters", headers=auth_headers, json={"keywords": "   ", "location": ""})

    body = client.get("/matches/filters", headers=auth_headers).json()

    assert body["filters"]["keywords"] is None
    assert body["effective_location"] == "Barcelona"


def test_invalid_filter_values_are_rejected(client, auth_headers):
    for bad in ({"radius_km": 0}, {"radius_km": 500}, {"min_score": 101}, {"max_days_old": 0}):
        assert client.put("/matches/filters", headers=auth_headers, json=bad).status_code == 422


def test_filters_are_per_user(client, auth_headers):
    client.put("/matches/filters", headers=auth_headers, json={"keywords": "rust"})
    other = register_and_login(client, email="otra@example.com")

    assert client.get("/matches/filters", headers=other).json()["filters"]["keywords"] is None


def test_search_uses_the_saved_filters(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    client.put(
        "/matches/filters",
        headers=auth_headers,
        json={
            "keywords": "react node",
            "location": "Girona",
            "radius_km": 10,
            "exclude": "php, sap",
            "exclude_other_levels": False,
            "max_days_old": 14,
        },
    )
    captured = {}

    def fake_search(query, location=None, **kwargs):
        captured.update(query=query, location=location, **kwargs)
        return []

    monkeypatch.setattr(matches_router, "search_job_offers", fake_search)

    assert client.post("/matches/search", headers=auth_headers).status_code == 200
    assert captured["query"] == "react node"
    assert captured["location"] == "Girona"
    assert captured["radius_km"] == 10
    assert captured["exclude"] == "php, sap"
    assert captured["exclude_other_levels"] is False
    assert captured["max_days_old"] == 14


def test_search_with_custom_keywords_works_even_with_an_empty_profile(client, auth_headers, monkeypatch):
    client.put("/matches/filters", headers=auth_headers, json={"keywords": "python"})
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [])

    assert client.post("/matches/search", headers=auth_headers).status_code == 200


# --- Tope diario global y caché ----------------------------------------------


class _Resp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"results": [{"id": 1, "title": "Dev", "description": "Python"}]}


def _configure(monkeypatch, daily_limit, cache_minutes=360):
    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(settings, "ADZUNA_APP_KEY", "key")
    monkeypatch.setattr(settings, "ADZUNA_DAILY_LIMIT", daily_limit)
    monkeypatch.setattr(settings, "ADZUNA_CACHE_MINUTES", cache_minutes)
    monkeypatch.setattr(settings, "MATCH_SEARCH_COOLDOWN_MINUTES", 0)
    calls = []
    monkeypatch.setattr(job_search.httpx, "get", lambda url, params, timeout: calls.append(params) or _Resp())
    return calls


def _search_with(client, headers, keywords):
    client.put("/matches/filters", headers=headers, json={"keywords": keywords})
    return client.post("/matches/search", headers=headers)


def test_daily_limit_blocks_real_calls_with_503_and_retry_after(client, auth_headers, monkeypatch):
    calls = _configure(monkeypatch, daily_limit=2)

    assert _search_with(client, auth_headers, "python").status_code == 200
    assert _search_with(client, auth_headers, "angular").status_code == 200
    blocked = _search_with(client, auth_headers, "java")

    assert blocked.status_code == 503
    assert int(blocked.headers["Retry-After"]) > 0
    assert len(calls) == 2  # la tercera NO llegó a Adzuna


def test_daily_limit_is_shared_across_users(client, auth_headers, monkeypatch):
    calls = _configure(monkeypatch, daily_limit=1)
    other = register_and_login(client, email="otra@example.com")

    assert _search_with(client, auth_headers, "python").status_code == 200
    assert _search_with(client, other, "angular").status_code == 503
    assert len(calls) == 1


def test_cache_hits_do_not_consume_the_daily_limit(client, auth_headers, monkeypatch):
    calls = _configure(monkeypatch, daily_limit=1)
    other = register_and_login(client, email="otra@example.com")

    assert _search_with(client, auth_headers, "python").status_code == 200
    # Misma búsqueda, otro usuario: sale de la caché, no gasta cuota ni llama a Adzuna
    assert _search_with(client, other, "python").status_code == 200
    assert len(calls) == 1


def test_daily_limit_zero_means_unlimited(client, auth_headers, monkeypatch):
    calls = _configure(monkeypatch, daily_limit=0)

    for keywords in ("a", "b", "c", "d"):
        assert _search_with(client, auth_headers, keywords).status_code == 200
    assert len(calls) == 4


def test_remaining_searches_are_reported_in_filters(client, auth_headers, monkeypatch):
    _configure(monkeypatch, daily_limit=5)
    assert client.get("/matches/filters", headers=auth_headers).json()["daily_remaining"] == 5

    _search_with(client, auth_headers, "python")

    assert client.get("/matches/filters", headers=auth_headers).json()["daily_remaining"] == 4


def test_no_limit_reports_none(client, auth_headers, monkeypatch):
    _configure(monkeypatch, daily_limit=0)
    assert client.get("/matches/filters", headers=auth_headers).json()["daily_remaining"] is None


# --- Límite por IP en endpoints públicos ---------------------------------------


def _register(client, n, ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post(
        "/auth/register",
        headers=headers,
        json={"email": f"user{n}@example.com", "password": "supersecret123", "full_name": "U"},
    )


def test_register_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "REGISTER_LIMIT_PER_HOUR", 2)

    assert _register(client, 1, "1.1.1.1").status_code == 201
    assert _register(client, 2, "1.1.1.1").status_code == 201
    blocked = _register(client, 3, "1.1.1.1")

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    # Otra IP no se ve afectada
    assert _register(client, 4, "2.2.2.2").status_code == 201


def test_login_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "LOGIN_LIMIT_PER_MINUTE", 3)
    bad = {"email": "nadie@example.com", "password": "mala-clave"}

    statuses = [client.post("/auth/login", json=bad).status_code for _ in range(5)]

    assert statuses == [401, 401, 401, 429, 429]


def test_rate_limits_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(settings, "REGISTER_LIMIT_PER_HOUR", 1)

    assert all(_register(client, n).status_code == 201 for n in range(4))
