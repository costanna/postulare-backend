"""Detección de idioma de la oferta y kit multilingüe. Sin llamadas reales."""
import pytest

from app.services.lang_detect import detect_language


def test_detects_spanish():
    assert detect_language("Buscamos camarero con experiencia", "Contrato indefinido y salario fijo.") == "es"


def test_detects_catalan():
    assert detect_language("Cerquem cambrer amb experiència", "Oferim jornada completa i incorporació.") == "ca"


def test_detects_english():
    assert detect_language("We are looking for a waiter", "Full-time position with benefits.") == "en"


def test_returns_none_without_signals():
    assert detect_language("Python Developer", "Angular FastAPI SQL") is None
    assert detect_language("", None) is None


def test_tie_returns_none():
    # "con" (es) + "with" (en): empate a 1, sin ganador claro.
    assert detect_language("Trabaja con with pasión") is None


@pytest.mark.parametrize("lang", ["es", "ca", "en"])
def test_pack_uses_offer_language(client, auth_headers, monkeypatch, lang):
    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    bodies = {
        "es": ("Camarero con experiencia", "Buscamos camarero con experiencia y contrato."),
        "ca": ("Cambrer amb experiència", "Cerquem cambrer amb experiència per incorporar."),
        "en": ("Experienced waiter", "We are looking for a waiter with experience."),
    }
    title, description = bodies[lang]
    offer = {
        "source": "eures",
        "external_id": f"lang-{lang}",
        "title": title,
        "company_name": "Bar",
        "location": "Barcelona",
        "description": description,
        "salary_range": None,
        "url": "https://example.com/lang",
    }
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [offer])
    client.post("/matches/search", headers=auth_headers)
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]

    pack = client.get(f"/matches/{match_id}/apply-pack", headers=auth_headers).json()
    assert pack["language"] == lang
    assert pack["detected_language"] == lang
    if lang == "en":
        assert pack["email_subject"].startswith("Application:")
        assert "## Skills" in pack["cv_markdown"]
        assert "Job posting:" in pack["email_body"]
    else:
        assert pack["email_subject"].startswith("Candidatura:")
        assert "Oferta: https://example.com/lang" in pack["email_body"]
    if lang == "ca":
        assert "## Habilitats" in pack["cv_markdown"]


def test_pack_falls_back_to_user_language(client, auth_headers, monkeypatch):
    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    offer = {
        "source": "adzuna",
        "external_id": "neutral",
        "title": "Python Developer",
        "company_name": "Tech",
        "location": "Barcelona",
        "description": "Python FastAPI SQL.",
        "salary_range": None,
        "url": "https://example.com/neutral",
    }
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [offer])
    client.post("/matches/search", headers=auth_headers)
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]

    pack = client.get(f"/matches/{match_id}/apply-pack", headers=auth_headers).json()
    assert pack["detected_language"] is None
    assert pack["language"] == "es"
