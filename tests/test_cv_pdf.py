"""CV en PDF por idioma: subida, adjunto original y validaciones."""
import pytest

import app.services.cv_mailer as cv_mailer
from app.core.config import settings
from tests.pdf_factory import make_pdf


def _pdf_bytes() -> bytes:
    return make_pdf(
        [
            "Anna Costa",
            "Desarrolladora Full Stack",
            "Barcelona | anna@example.com",
            "PERFIL PROFESIONAL",
            "Desarrolladora con experiencia en Python, FastAPI y Angular creando aplicaciones web modernas.",
            "HABILIDADES",
            "Python, FastAPI, Angular, Docker",
        ]
    )


@pytest.fixture(autouse=True)
def _smtp(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_USER", "t@gmail.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "x")


def _upload(client, headers, lang="es", data=None, filename="CV-Anna.pdf"):
    return client.post(
        f"/profile/cvs/{lang}/file",
        headers=headers,
        files={"file": (filename, data if data is not None else _pdf_bytes(), "application/pdf")},
    )


def test_upload_pdf_stores_file_and_text(client, auth_headers):
    body = _upload(client, auth_headers).json()
    assert body["has_file"] is True
    assert body["filename"] == "CV-Anna.pdf"
    assert "Python" in body["content"]

    listed = client.get("/profile/cvs", headers=auth_headers).json()
    assert listed[0]["has_file"] is True


def test_pack_uses_pdf_text(client, auth_headers, monkeypatch):
    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    _upload(client, auth_headers)
    _set_profile(client, auth_headers)
    offer = {
        "source": "eures",
        "external_id": "pdf-1",
        "title": "Camarero con experiencia",
        "company_name": "Bar",
        "location": "Barcelona",
        "description": "Buscamos camarero con experiencia.",
        "salary_range": None,
        "url": "https://example.com/pdf",
    }
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [offer])
    client.post("/matches/search", headers=auth_headers)
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]
    pack = client.get(f"/matches/{match_id}/apply-pack", headers=auth_headers).json()
    assert pack["cv_source"] == "pdf"
    assert "FastAPI" in pack["cv_markdown"]


def test_send_attaches_original_pdf(client, auth_headers, monkeypatch):
    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    _upload(client, auth_headers)
    _set_profile(client, auth_headers)
    offer = {
        "source": "eures",
        "external_id": "pdf-2",
        "title": "Camarero con experiencia",
        "company_name": "Bar",
        "location": "Barcelona",
        "description": "Envía tu CV a empleo@empresa.com.",
        "salary_range": None,
        "url": "https://example.com/pdf2",
    }
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [offer])
    client.post("/matches/search", headers=auth_headers)
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]

    sent: dict = {}

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
            attachments = list(message.iter_attachments())
            sent["type"] = attachments[0].get_content_type()
            sent["filename"] = attachments[0].get_filename()

    class _Module:
        def SMTP(self, host, port, timeout=None):
            return _Conn()

    monkeypatch.setattr(cv_mailer, "smtplib", _Module())
    assert client.post(f"/matches/{match_id}/send-email", headers=auth_headers).status_code == 201
    assert sent == {"type": "application/pdf", "filename": "CV-Anna.pdf"}


def test_upload_rejects_not_pdf_oversize_and_bad_lang(client, auth_headers, monkeypatch):
    assert _upload(client, auth_headers, data=b"no es un pdf").status_code == 415
    assert _upload(client, auth_headers, lang="fr").status_code == 422
    monkeypatch.setattr(settings, "CV_MAX_BYTES", 10)
    assert _upload(client, auth_headers).status_code == 413
    monkeypatch.setattr(settings, "CV_MAX_BYTES", 2_000_000)
    assert _upload(client, auth_headers, data=make_pdf([])).status_code == 422


def test_text_save_clears_pdf_and_file_delete_keeps_text(client, auth_headers):
    _upload(client, auth_headers)
    saved = client.put("/profile/cvs/es", headers=auth_headers, json={"content": "Texto manual"}).json()
    assert saved["has_file"] is False and saved["content"] == "Texto manual"

    _upload(client, auth_headers)
    assert client.delete("/profile/cvs/es/file", headers=auth_headers).status_code == 204
    listed = client.get("/profile/cvs", headers=auth_headers).json()[0]
    assert listed["has_file"] is False and "Python" in listed["content"]
