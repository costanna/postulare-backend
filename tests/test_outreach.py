"""CVs por idioma, directorio de espontáneas y límites 5/día + 15 días."""
import pytest

import app.services.cv_mailer as cv_mailer
from app.core.config import settings
from app.services.companies import normalize_company


def test_normalize_company_ignores_legal_suffixes():
    assert normalize_company("Acme SL") == normalize_company("ACME S.A.")
    assert normalize_company("Nórdica Tech S.L.U.") == "nordica tech"
    assert normalize_company(None) == ""


@pytest.fixture(autouse=True)
def _smtp(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "test@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(settings, "SEND_EMAIL_DAILY_LIMIT_PER_USER", 5)


class _FakeSmtpModule:
    def __init__(self, sent):
        self._sent = sent

    def SMTP(self, host, port, timeout=None):
        out = self._sent

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
                out.append({"to": message["To"], "subject": message["Subject"]})

        return _Conn()


@pytest.fixture()
def _fake_smtp(monkeypatch):
    sent: list = []
    monkeypatch.setattr(cv_mailer, "smtplib", _FakeSmtpModule(sent))
    return sent


def _target(client, headers, name="Nórdica Tech SL", email="jobs@nordica.example", language="es"):
    response = client.post(
        "/targets", headers=headers, json={"name": name, "email": email, "language": language}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_cv_crud_and_validation(client, auth_headers):
    assert client.get("/profile/cvs", headers=auth_headers).json() == []
    assert client.put("/profile/cvs/fr", headers=auth_headers, json={"content": "x"}).status_code == 422

    saved = client.put("/profile/cvs/en", headers=auth_headers, json={"content": "My CV text"}).json()
    assert saved["language"] == "en" and saved["content"] == "My CV text"
    assert [cv["language"] for cv in client.get("/profile/cvs", headers=auth_headers).json()] == ["en"]

    # Vacío = borrar.
    assert client.put("/profile/cvs/en", headers=auth_headers, json={"content": "  "}).status_code == 204
    assert client.get("/profile/cvs", headers=auth_headers).json() == []


def test_targets_crud_and_duplicates(client, auth_headers):
    created = _target(client, auth_headers)
    assert created["can_send"] is True and created["retry_in_days"] == 0

    dup = client.post(
        "/targets", headers=auth_headers, json={"name": "Otro nombre", "email": "jobs@nordica.example"}
    )
    assert dup.status_code == 409

    updated = client.patch(
        "/targets/" + created["id"], headers=auth_headers, json={"language": "ca"}
    ).json()
    assert updated["language"] == "ca"

    assert client.delete("/targets/" + created["id"], headers=auth_headers).status_code == 204
    assert client.get("/targets", headers=auth_headers).json() == []


def test_spontaneous_send_uses_target_language_and_records(client, auth_headers, _fake_smtp):
    target = _target(client, auth_headers, language="ca")
    response = client.post(f"/targets/{target['id']}/send", headers=auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sent_to"] == "jobs@nordica.example"
    assert body["subject"].startswith("Candidatura espontània:")
    assert body["application"]["status"] == "applied"
    assert body["application"]["source"] == "spontaneous"
    assert len(_fake_smtp) == 1

    listed = client.get("/targets", headers=auth_headers).json()[0]
    assert listed["can_send"] is False
    assert listed["retry_in_days"] == 15


def test_cooldown_blocks_same_company_variants(client, auth_headers, _fake_smtp):
    first = _target(client, auth_headers, name="Acme SL", email="a@acme.example")
    assert client.post(f"/targets/{first['id']}/send", headers=auth_headers).status_code == 201

    second = _target(client, auth_headers, name="ACME S.A.", email="b@acme.example")
    blocked = client.post(f"/targets/{second['id']}/send", headers=auth_headers)
    assert blocked.status_code == 409
    assert "15" in blocked.json()["detail"]

    # Otra empresa el mismo día sí puede.
    third = _target(client, auth_headers, name="Otra SL", email="c@otra.example")
    assert client.post(f"/targets/{third['id']}/send", headers=auth_headers).status_code == 201


def test_daily_limit_and_bulk(client, auth_headers, _fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "SEND_EMAIL_DAILY_LIMIT_PER_USER", 2)
    ids = [
        _target(client, auth_headers, name=f"Empresa {i}", email=f"jobs{i}@x.example")["id"] for i in range(3)
    ]
    body = client.post("/targets/send-bulk", headers=auth_headers, json={"target_ids": ids}).json()
    assert [r["ok"] for r in body["sent"]] == [True, True, False]
    assert body["daily_remaining"] == 0


def test_demo_cannot_send_spontaneous(client):
    tokens = client.post("/auth/demo").json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (
        client.post("/targets/00000000-0000-0000-0000-000000000000/send", headers=headers).status_code == 403
    )
    assert client.post("/targets/send-bulk", headers=headers, json={"target_ids": []}).status_code == 403


def test_pack_prefers_saved_cv(client, auth_headers, monkeypatch):
    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    client.put("/profile/cvs/es", headers=auth_headers, json={"content": "MI CV EN ESPAÑOL"})
    _set_profile(client, auth_headers)
    offer = {
        "source": "eures",
        "external_id": "cv-1",
        "title": "Camarero con experiencia",
        "company_name": "Bar",
        "location": "Barcelona",
        "description": "Buscamos camarero con experiencia.",
        "salary_range": None,
        "url": "https://example.com/cv",
    }
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [offer])
    client.post("/matches/search", headers=auth_headers)
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]
    pack = client.get(f"/matches/{match_id}/apply-pack", headers=auth_headers).json()
    assert pack["cv_source"] == "saved"
    assert pack["cv_markdown"] == "MI CV EN ESPAÑOL"
