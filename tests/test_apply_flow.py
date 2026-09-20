"""Aplicar a una oferta: fecha, estado y rastro en la línea de tiempo; y los bugs de entrada
nula / mayúsculas en el email que se detectaron en la revisión."""
from datetime import date

import pytest

import app.core.rate_limit as rate_limit
import app.routers.matches as matches_router
from app.core.security import hash_password
from app.models.user import User
from tests.conftest import register_and_login
from tests.test_matches import FAKE_OFFERS, _set_profile


def _create(client, headers, **extra) -> dict:
    response = client.post("/applications", headers=headers, json={"company_name": "A", "position": "B", **extra})
    assert response.status_code == 201
    return response.json()


def _events(client, headers, app_id) -> list[dict]:
    return client.get(f"/applications/{app_id}/events", headers=headers).json()


def test_creating_an_applied_application_stamps_today(client, auth_headers):
    created = _create(client, auth_headers, status="applied")
    assert created["applied_at"] == date.today().isoformat()


def test_creating_a_saved_application_has_no_applied_date(client, auth_headers):
    assert _create(client, auth_headers)["applied_at"] is None


def test_creating_keeps_an_explicit_applied_date(client, auth_headers):
    assert _create(client, auth_headers, status="applied", applied_at="2026-01-15")["applied_at"] == "2026-01-15"


def test_moving_to_applied_sets_the_date_and_records_the_change(client, auth_headers):
    app_id = _create(client, auth_headers)["id"]

    updated = client.patch(f"/applications/{app_id}", headers=auth_headers, json={"status": "applied"}).json()

    assert updated["status"] == "applied"
    assert updated["applied_at"] == date.today().isoformat()
    events = _events(client, auth_headers, app_id)
    assert [(e["type"], e["description"]) for e in events] == [("status_change", "saved → applied")]


def test_later_status_changes_keep_the_original_date_and_add_events(client, auth_headers):
    app_id = _create(client, auth_headers, status="applied", applied_at="2026-01-15")["id"]

    updated = client.patch(f"/applications/{app_id}", headers=auth_headers, json={"status": "interview"}).json()

    assert updated["applied_at"] == "2026-01-15"
    assert [e["description"] for e in _events(client, auth_headers, app_id)] == ["applied → interview"]


def test_patching_without_changing_status_adds_no_event(client, auth_headers):
    app_id = _create(client, auth_headers, status="applied")["id"]
    client.patch(f"/applications/{app_id}", headers=auth_headers, json={"notes": "hola", "status": "applied"})
    assert _events(client, auth_headers, app_id) == []


def test_withdrawing_a_saved_application_does_not_invent_an_applied_date(client, auth_headers):
    app_id = _create(client, auth_headers)["id"]
    updated = client.patch(f"/applications/{app_id}", headers=auth_headers, json={"status": "withdrawn"}).json()
    assert updated["applied_at"] is None


def test_an_explicit_date_in_the_same_update_wins(client, auth_headers):
    app_id = _create(client, auth_headers)["id"]
    updated = client.patch(
        f"/applications/{app_id}", headers=auth_headers, json={"status": "applied", "applied_at": "2026-02-02"}
    ).json()
    assert updated["applied_at"] == "2026-02-02"


@pytest.fixture()
def match_id(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kwargs: FAKE_OFFERS)
    client.post("/matches/search", headers=auth_headers)
    return client.get("/matches", headers=auth_headers).json()[0]["id"]


def test_convert_defaults_to_saved(client, auth_headers, match_id):
    application = client.post(f"/matches/{match_id}/convert", headers=auth_headers).json()
    assert application["status"] == "saved" and application["applied_at"] is None


def test_convert_as_applied_creates_a_sent_application_with_the_users_date(client, auth_headers, match_id):
    response = client.post(
        f"/matches/{match_id}/convert", headers=auth_headers, json={"applied": True, "applied_at": "2026-03-04"}
    )
    assert response.status_code == 201
    assert response.json()["status"] == "applied"
    assert response.json()["applied_at"] == "2026-03-04"
    stats = client.get("/stats/summary", headers=auth_headers).json()
    assert stats["total_applied"] == 1


def test_convert_as_applied_without_date_uses_today(client, auth_headers, match_id):
    application = client.post(f"/matches/{match_id}/convert", headers=auth_headers, json={"applied": True}).json()
    assert application["applied_at"] == date.today().isoformat()


def test_converting_twice_is_rejected_and_creates_no_duplicate(client, auth_headers, match_id):
    assert client.post(f"/matches/{match_id}/convert", headers=auth_headers).status_code == 201
    assert client.post(f"/matches/{match_id}/convert", headers=auth_headers).status_code == 409
    assert client.get("/applications", headers=auth_headers).json()["total"] == 1


# --- Nulos explícitos: antes devolvían 500 ---------------------------------------


@pytest.mark.parametrize("field", ["company_name", "position", "status"])
def test_application_update_rejects_null_required_fields(client, auth_headers, field):
    app_id = _create(client, auth_headers)["id"]
    response = client.patch(f"/applications/{app_id}", headers=auth_headers, json={field: None})
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["skills", "preferred_language"])
def test_profile_update_rejects_null_required_fields(client, auth_headers, field):
    assert client.patch("/profile", headers=auth_headers, json={field: None}).status_code == 422


def test_optional_fields_can_still_be_cleared_with_null(client, auth_headers):
    app_id = _create(client, auth_headers, notes="x", salary_range="1")["id"]
    updated = client.patch(f"/applications/{app_id}", headers=auth_headers, json={"notes": None}).json()
    assert updated["notes"] is None and updated["salary_range"] == "1"
    assert client.patch("/profile", headers=auth_headers, json={"location": None}).status_code == 200


# --- Emails sin distinguir mayúsculas -----------------------------------------------


def test_email_is_stored_lowercase_and_login_ignores_case(client):
    response = client.post("/auth/register", json={"email": "Ana.Mayus@Example.COM", "password": "supersecret123"})
    assert response.json()["email"] == "ana.mayus@example.com"
    for variant in ("ana.mayus@example.com", "ANA.MAYUS@EXAMPLE.COM", " Ana.Mayus@example.com "):
        login = client.post("/auth/login", json={"email": variant, "password": "supersecret123"})
        assert login.status_code == 200, variant


def test_registering_the_same_email_with_other_case_is_a_conflict(client):
    client.post("/auth/register", json={"email": "dup@example.com", "password": "supersecret123"})
    again = client.post("/auth/register", json={"email": "DUP@Example.com", "password": "supersecret123"})
    assert again.status_code == 409


def test_accounts_created_before_the_fix_with_capitals_can_still_log_in(client, db_session):
    db_session.add(User(email="Vieja.Cuenta@Example.com", hashed_password=hash_password("supersecret123")))
    db_session.commit()
    login = client.post("/auth/login", json={"email": "vieja.cuenta@example.com", "password": "supersecret123"})
    assert login.status_code == 200


def test_rate_limiter_forgets_old_clients(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(rate_limit, "_MAX_TRACKED_KEYS", 3)
    rate_limit.reset_rate_limits()
    for i in range(6):
        rate_limit._check("login", f"10.0.0.{i}", 5, 60)
    now = rate_limit.time.monotonic()
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now + 4000)
    rate_limit._check("login", "10.0.9.9", 5, 60)
    assert len(rate_limit._hits) == 1


# --- Recuperar contraseña ------------------------------------------------------------


def test_reset_email_links_to_a_route_that_exists_in_the_frontend(monkeypatch):
    import app.services.email as email_service

    sent = []
    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "")
    monkeypatch.setattr(email_service.settings, "FRONTEND_URL", "https://postulare.example")
    monkeypatch.setattr(email_service.logger, "info", lambda message, *args: sent.append(args[-1]))

    email_service.send_password_reset_email("a@example.com", "tok123")

    assert sent == ["https://postulare.example/auth/reset-password?token=tok123"]


def test_forgot_password_answers_202_even_when_the_email_server_fails(client, monkeypatch):
    import app.routers.auth as auth_router

    def boom(to_email, reset_token):
        raise ConnectionRefusedError("smtp caído")

    monkeypatch.setattr(auth_router, "send_password_reset_email", boom)
    client.post("/auth/register", json={"email": "ana@example.com", "password": "supersecret123"})

    known = client.post("/auth/forgot-password", json={"email": "ana@example.com"})
    unknown = client.post("/auth/forgot-password", json={"email": "nadie@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


def test_malformed_adzuna_json_is_reported_as_a_search_error(monkeypatch):
    import httpx

    from app.core.config import settings
    from app.services.job_search import JobSearchError, clear_search_cache, search_job_offers

    monkeypatch.setattr(settings, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(settings, "ADZUNA_APP_KEY", "key")
    clear_search_cache()
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, content=b"<html>no es json</html>", request=httpx.Request("GET", "https://x")))

    with pytest.raises(JobSearchError):
        search_job_offers("python")
