"""Importar CV: parser (texto y PDF) y endpoint. Los PDFs se fabrican en el test."""
import pytest

from app.core.config import settings
from app.services.cv_parser import CvParseError, extract_text, parse_cv_pdf, parse_cv_text
from tests.pdf_factory import FAKE_CV_LINES, make_pdf


def test_parser_extracts_profile_from_pdf():
    proposal = parse_cv_pdf(make_pdf(FAKE_CV_LINES), max_pages=6)

    assert proposal.full_name == "Laura Ejemplo"
    assert proposal.desired_position == "Desarrolladora Full Stack Junior"
    assert proposal.location == "Girona"
    assert proposal.seniority == "junior"
    assert proposal.about is not None and proposal.about.startswith("Desarrolladora junior con proyectos")
    # Las skills salen con su mayúscula canónica y sin duplicados
    for skill in ("Python", "FastAPI", "Angular", "TypeScript", "PostgreSQL", "Docker", "JavaScript"):
        assert skill in proposal.skills
    assert len(proposal.skills) == len(set(proposal.skills))


def test_parser_puts_searchable_skills_before_generic_tools():
    proposal = parse_cv_text("\n".join(FAKE_CV_LINES))
    assert proposal.skills.index("Python") < proposal.skills.index("Git")
    assert proposal.skills.index("Angular") < proposal.skills.index("Scrum")


def test_parser_does_not_confuse_java_with_javascript_or_sql_with_postgresql():
    only_js = parse_cv_text("ANA X\nDeveloper\nTrabajo con JavaScript y PostgreSQL todos los dias en la empresa.")
    assert "JavaScript" in only_js.skills and "PostgreSQL" in only_js.skills
    assert "Java" not in only_js.skills
    assert "SQL" not in only_js.skills


def test_parser_returns_partial_result_when_data_is_missing():
    proposal = parse_cv_text("solo un texto suelto sin estructura con Python dentro de la frase larga aqui")
    assert proposal.skills == ["Python"]
    assert proposal.full_name is None
    assert proposal.seniority is None
    assert proposal.about is None


def test_extract_text_rejects_pdf_without_text():
    with pytest.raises(CvParseError):
        extract_text(make_pdf([]), max_pages=6)


def test_extract_text_rejects_garbage():
    with pytest.raises(CvParseError):
        extract_text(b"%PDF-1.4 esto no es un pdf de verdad", max_pages=6)


def _upload(client, headers, content: bytes, name="cv.pdf", content_type="application/pdf"):
    return client.post("/profile/import-cv", headers=headers, files={"file": (name, content, content_type)})


def test_import_cv_endpoint_returns_proposal_and_saves_nothing(client, auth_headers):
    response = _upload(client, auth_headers, make_pdf(FAKE_CV_LINES))
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Laura Ejemplo"
    assert body["desired_position"] == "Desarrolladora Full Stack Junior"
    assert body["seniority"] == "junior"
    assert "Python" in body["skills"]

    # Es solo una propuesta: el perfil no cambia hasta que el usuario la confirme
    profile = client.get("/profile", headers=auth_headers).json()
    assert profile["skills"] == []
    assert profile["desired_position"] is None
    assert profile["about"] is None


def test_import_cv_requires_auth(client):
    response = client.post("/profile/import-cv", files={"file": ("cv.pdf", make_pdf(FAKE_CV_LINES), "application/pdf")})
    assert response.status_code == 401


def test_import_cv_rejects_non_pdf(client, auth_headers):
    response = _upload(client, auth_headers, b"hola, soy un texto", name="cv.pdf")
    assert response.status_code == 415


def test_import_cv_rejects_oversized_file(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "CV_MAX_BYTES", 500)
    response = _upload(client, auth_headers, make_pdf(FAKE_CV_LINES) + b"0" * 600)
    assert response.status_code == 413


def test_import_cv_rejects_pdf_without_text(client, auth_headers):
    response = _upload(client, auth_headers, make_pdf([]))
    assert response.status_code == 422


def test_import_cv_is_rate_limited_per_ip(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "CV_IMPORT_LIMIT_PER_HOUR", 2)
    statuses = [_upload(client, auth_headers, make_pdf(FAKE_CV_LINES)).status_code for _ in range(3)]
    assert statuses == [200, 200, 429]


def test_profile_accepts_and_limits_about(client, auth_headers):
    ok = client.patch("/profile", headers=auth_headers, json={"about": "Me encanta programar."})
    assert ok.status_code == 200
    assert ok.json()["about"] == "Me encanta programar."

    too_long = client.patch("/profile", headers=auth_headers, json={"about": "x" * 2001})
    assert too_long.status_code == 422
