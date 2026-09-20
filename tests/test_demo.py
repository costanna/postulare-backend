"""Cuenta demo temporal: se crea sin registro, tiene datos de ejemplo, no puede gastar
las APIs de pago (Adzuna / IA), caduca y se limpia sola."""
from datetime import datetime, timedelta, timezone

import pytest

import app.routers.matches as matches_router
from app.core.config import settings
from app.models.application import Application
from app.models.match import Match
from app.models.user import User


def _start_demo(client, **body):
    return client.post("/auth/demo", json=body) if body else client.post("/auth/demo")


def _headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_demo_creates_account_with_sample_data(client):
    response = _start_demo(client)
    assert response.status_code == 200
    tokens = response.json()
    assert tokens["token_type"] == "bearer" and tokens["refresh_token"]

    me = client.get("/auth/me", headers=_headers(tokens)).json()
    assert me["is_demo"] is True
    assert me["email"].startswith("demo-")
    assert me["skills"] and me["desired_position"] == "Full Stack Developer"

    apps = client.get("/applications", headers=_headers(tokens)).json()
    assert apps["total"] == 7
    assert {a["status"] for a in apps["items"]} == {"saved", "applied", "interview", "offer", "rejected"}

    matches = client.get("/matches", headers=_headers(tokens)).json()
    assert len(matches) == 5
    assert all(m["job_offer"]["source"] == "demo" for m in matches)
    # Una oferta coincide con una candidatura para enseñar el aviso "ya la tienes"
    assert sum(m["already_tracked"] for m in matches) == 1


def test_demo_language_changes_sample_texts(client):
    tokens = _start_demo(client, language="ca").json()
    me = client.get("/auth/me", headers=_headers(tokens)).json()
    assert me["preferred_language"] == "ca"
    assert "Desenvolupadora" in me["about"]


def test_each_demo_is_an_independent_account_and_shares_no_data(client):
    first, second = _start_demo(client).json(), _start_demo(client).json()
    a = client.get("/auth/me", headers=_headers(first)).json()
    b = client.get("/auth/me", headers=_headers(second)).json()
    assert a["id"] != b["id"] and a["email"] != b["email"]

    client.post("/applications", headers=_headers(first), json={"company_name": "Solo A", "position": "Dev"})
    assert client.get("/applications", headers=_headers(second)).json()["total"] == 7


def test_demo_cannot_search_real_offers(client, monkeypatch):
    called = []
    monkeypatch.setattr(matches_router, "search_job_offers", lambda *a, **k: called.append(1) or [])
    response = client.post("/matches/search", headers=_headers(_start_demo(client).json()))
    assert response.status_code == 403
    assert called == []  # ni siquiera se acerca a Adzuna


def test_demo_letters_use_template_and_never_call_the_ai(client, monkeypatch):
    import app.services.cover_letter as cover_letter

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(cover_letter, "_client", lambda: pytest.fail("la demo no debe llamar a la IA"))

    headers = _headers(_start_demo(client).json())
    match_id = client.get("/matches", headers=headers).json()[0]["id"]
    body = client.post(f"/matches/{match_id}/cover-letter", headers=headers, json={}).json()
    assert body["source"] == "template"
    assert body["template_reason"] == "demo"
    assert body["ai_available"] is False


def test_demo_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_ENABLED", False)
    assert _start_demo(client).status_code == 404


def test_demo_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "DEMO_LIMIT_PER_HOUR", 2)
    assert [_start_demo(client).status_code for _ in range(3)] == [200, 200, 429]


def test_demo_has_a_global_daily_cap(client, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_ACCOUNTS_DAILY_LIMIT", 2)
    assert [_start_demo(client).status_code for _ in range(3)] == [200, 200, 503]


def _age_demo_users(db_session, hours: int) -> None:
    for user in db_session.query(User).filter(User.is_demo.is_(True)):
        user.created_at = datetime.now(timezone.utc) - timedelta(hours=hours)
    db_session.commit()


def test_expired_demo_session_is_rejected(client, db_session):
    tokens = _start_demo(client).json()
    assert client.get("/auth/me", headers=_headers(tokens)).status_code == 200

    _age_demo_users(db_session, settings.DEMO_TTL_HOURS + 1)

    assert client.get("/auth/me", headers=_headers(tokens)).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_expired_demo_accounts_are_purged_with_their_data(client, db_session):
    _start_demo(client)
    _age_demo_users(db_session, settings.DEMO_TTL_HOURS + 1)
    assert db_session.query(User).filter(User.is_demo.is_(True)).count() == 1

    _start_demo(client)  # crear una demo limpia las caducadas

    assert db_session.query(User).filter(User.is_demo.is_(True)).count() == 1
    assert db_session.query(Application).count() == 7
    assert db_session.query(Match).count() == 5


def test_purge_never_touches_real_users(client, db_session, auth_headers):
    _start_demo(client)
    db_session.query(User).update({User.created_at: datetime.now(timezone.utc) - timedelta(days=400)})
    db_session.commit()

    _start_demo(client)

    assert db_session.query(User).filter(User.email == "ana@example.com").count() == 1
    assert client.get("/auth/me", headers=auth_headers).status_code == 200


def test_demo_password_cannot_be_used_to_log_in(client):
    _start_demo(client)
    email = client.get("/auth/me", headers=_headers(_start_demo(client).json())).json()["email"]
    assert client.post("/auth/login", json={"email": email, "password": "password123"}).status_code == 401
