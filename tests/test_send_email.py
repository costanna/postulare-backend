"""Envío directo por email: solo cuentas reales, con email de contacto y SMTP."""
import pytest

import app.routers.matches as matches_router
import app.services.cv_mailer as cv_mailer
from app.core.config import settings


def _offer(external_id="send-1", description="Buscamos camarero. Envía tu CV a empleo@empresa.com."):
    return {
        "source": "eures",
        "external_id": external_id,
        "title": f"Camarero con experiencia {external_id}",
        "company_name": f"Bar {external_id}",
        "location": "Barcelona",
        "description": description,
        "salary_range": None,
        "url": f"https://example.com/{external_id}",
    }


class _FakeConn:
    def __init__(self, sent):
        self._sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        assert user == "test@gmail.com" and password == "app-password"

    def send_message(self, message):
        self._sent["to"] = message["To"]
        self._sent["subject"] = message["Subject"]
        attachments = list(message.iter_attachments())
        self._sent["attachment"] = attachments[0].get_filename() if attachments else None


class _FakeSmtpModule:
    def __init__(self, sent):
        self._sent = sent

    def SMTP(self, host, port, timeout=None):
        assert host == "smtp.gmail.com"
        return _FakeConn(self._sent)


@pytest.fixture()
def _search_results(monkeypatch):
    monkeypatch.setattr(
        matches_router, "search_job_offers", lambda query, location=None, **kw: [_offer("send-1"), _offer("send-2")]
    )


@pytest.fixture()
def match_ids(client, auth_headers, _search_results):
    from tests.test_matches import _set_profile

    _set_profile(client, auth_headers)
    client.post("/matches/search", headers=auth_headers)
    return [m["id"] for m in client.get("/matches", headers=auth_headers).json()]


@pytest.fixture(autouse=True)
def _smtp(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "test@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(settings, "SEND_EMAIL_DAILY_LIMIT_PER_USER", 10)


def test_demo_cannot_send_email(client):
    tokens = client.post("/auth/demo").json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = client.post("/matches/00000000-0000-0000-0000-000000000000/send-email", headers=headers)
    assert response.status_code == 403


def test_send_email_delivers_and_converts(client, auth_headers, match_ids, monkeypatch):
    sent = {}
    monkeypatch.setattr(cv_mailer, "smtplib", _FakeSmtpModule(sent))

    response = client.post(f"/matches/{match_ids[0]}/send-email", headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["sent_to"] == "empleo@empresa.com"
    assert body["subject"].startswith("Candidatura:")
    assert body["application"]["status"] == "applied"
    assert sent["to"] == "empleo@empresa.com"
    assert (sent["attachment"] or "").startswith("CV")
    # Segunda vez: ya es candidatura.
    assert client.post(f"/matches/{match_ids[0]}/send-email", headers=auth_headers).status_code == 409


def test_send_email_without_contact_email_is_422(client, auth_headers, monkeypatch):
    from tests.test_matches import _set_profile

    _set_profile(client, auth_headers)
    monkeypatch.setattr(
        matches_router, "search_job_offers", lambda query, location=None, **kw: [_offer("x", "Sin email aquí.")]
    )
    client.post("/matches/search", headers=auth_headers)
    other_id = client.get("/matches", headers=auth_headers).json()[0]["id"]
    assert client.post(f"/matches/{other_id}/send-email", headers=auth_headers).status_code == 422


def test_send_email_without_smtp_is_503(client, auth_headers, match_ids, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert client.post(f"/matches/{match_ids[0]}/send-email", headers=auth_headers).status_code == 503


def test_send_email_respects_daily_limit(client, auth_headers, match_ids, monkeypatch):
    monkeypatch.setattr(settings, "SEND_EMAIL_DAILY_LIMIT_PER_USER", 1)
    monkeypatch.setattr(cv_mailer, "smtplib", _FakeSmtpModule({}))
    assert client.post(f"/matches/{match_ids[0]}/send-email", headers=auth_headers).status_code == 201
    assert client.post(f"/matches/{match_ids[1]}/send-email", headers=auth_headers).status_code == 429
