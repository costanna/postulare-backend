"""Descubrimiento automático: ofertas propias + hilo HN. Sin llamadas reales."""
import pytest

import app.services.hn_hiring as hn_hiring
import app.services.cv_mailer as cv_mailer
from app.core.config import settings


THREAD = {"hits": [{"objectID": "999", "title": "Ask HN: Who is hiring? (October 2026)"}]}
COMMENTS = {
    "children": [
        {"text": "Acme Corp | Remote (EU) | Python developer | jobs@acme.example | Buscamos Python con Django."},
        {"text": "Beta Inc | Berlin onsite | Java role | hire@beta.example"},
        {"text": "Sin email aquí | Remote | Python developer"},
    ]
}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture()
def _hn(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if "items" in url:
            return _Resp(COMMENTS)
        return _Resp(THREAD)

    monkeypatch.setattr(hn_hiring.httpx, "get", fake_get)


@pytest.fixture(autouse=True)
def _smtp(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_USER", "t@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "x")
    monkeypatch.setattr(settings, "SEND_EMAIL_DAILY_LIMIT_PER_USER", 5)


@pytest.fixture()
def _fake_smtp(monkeypatch):
    sent: list = []

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            sent.append(message["To"])

    class _Module:
        def SMTP(self, host, port, timeout=None):
            return _Conn()

    monkeypatch.setattr(cv_mailer, "smtplib", _Module())
    return sent


def _skilled_profile(client, headers):
    client.patch(
        "/profile", headers=headers, json={"skills": ["Python", "Django"], "desired_position": "Backend Developer"}
    )


def test_suggestions_from_offers(client, auth_headers, monkeypatch):
    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    _set_profile(client, auth_headers)
    offer = {
        "source": "eures",
        "external_id": "sug-1",
        "title": "Python Developer",
        "company_name": "Acme SL",
        "location": "Barcelona",
        "description": "Buscamos Python. Escribe a hola@acme.example.",
        "salary_range": None,
        "url": "https://example.com/sug",
    }
    monkeypatch.setattr(
        matches_router, "search_job_offers", lambda query, location=None, **kw: [offer]
    )
    client.post("/matches/search", headers=auth_headers)

    body = client.get("/targets/suggestions", headers=auth_headers).json()
    assert body["from_offers"][0]["email"] == "hola@acme.example"
    assert "Python" in body["from_offers"][0]["tags"]


def test_suggestions_from_hn(client, auth_headers, _hn):
    _skilled_profile(client, auth_headers)
    body = client.get("/targets/suggestions", headers=auth_headers).json()
    assert [(s["name"], s["email"]) for s in body["from_hn"]] == [("Acme Corp", "jobs@acme.example")]
    # Beta pide Java (sin encaje) y el tercero no trae email: fuera.
    assert body["from_hn"][0]["match_score"] >= 1


def test_hn_failure_does_not_break_suggestions(client, auth_headers, monkeypatch):
    import httpx

    _skilled_profile(client, auth_headers)
    monkeypatch.setattr(
        hn_hiring.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("caído"))
    )
    body = client.get("/targets/suggestions", headers=auth_headers).json()
    assert body["from_hn"] == [] and body["from_offers"] == []


def test_import_skips_existing(client, auth_headers):
    payload = {"items": [{"name": "Acme", "email": "JOBS@acme.example", "language": "es", "tags": ["python"]}]}
    assert client.post("/targets/import", headers=auth_headers, json=payload).json() == {
        "imported": 1,
        "skipped": 0,
    }
    assert client.post("/targets/import", headers=auth_headers, json=payload).json() == {
        "imported": 0,
        "skipped": 1,
    }


def test_autopilot_imports_and_sends_without_manual_targets(client, auth_headers, _hn, _fake_smtp):
    _skilled_profile(client, auth_headers)
    assert client.get("/targets", headers=auth_headers).json() == []

    body = client.post("/targets/autopilot", headers=auth_headers, json={}).json()
    assert [r["sent_to"] for r in body["sent"] if r["ok"]] == ["jobs@acme.example"]
    assert _fake_smtp == ["jobs@acme.example"]
    # Quedó importada con tags de evidencia para el matching.
    listed = client.get("/targets", headers=auth_headers).json()
    assert listed[0]["tags"] and listed[0]["match_score"] > 0


def test_autopilot_without_suggestions_flag_sends_nothing_new(client, auth_headers, _hn, _fake_smtp):
    _skilled_profile(client, auth_headers)
    body = client.post("/targets/autopilot", headers=auth_headers, json={"include_suggestions": False}).json()
    assert body["sent"] == []
    assert client.get("/targets", headers=auth_headers).json() == []
