"""Email anti-ATS: solo skills reales, localización y formato plano."""
from app.services.ats import ats_block, matched_keywords


def test_matches_only_real_skills_in_offer_order():
    keywords = matched_keywords(
        "Python Developer",
        "Buscamos Python con SQL. Java sería un plus.",
        ["Python", "SQL", "Rust"],
    )
    # Rust no está en la oferta: no se inventa. Orden de aparición.
    assert keywords == ["Python", "SQL"]


def test_whole_words_only():
    # "SQL" no debe casar con "PostgreSQL"/"MySQL": son skills distintas.
    assert matched_keywords("Backend", "PostgreSQL y MySQL.", ["SQL"]) == []


def test_limit_and_dedup():
    skills = ["Python", "python ", "PYTHON"] + [f"tech{i}" for i in range(20)]
    assert matched_keywords("Python", "Python.", skills) == ["Python"]


def test_ats_block_localized_and_honest():
    lines = ats_block("Dev", "junior", "Barcelona", "Dev Python", "Acme", ["Python"], "en")
    assert lines[0] == "Re: Dev Python — Acme"
    assert lines[1] == "Key matches: Python"
    assert lines[2] == "Profile: Dev · junior · Barcelona"


def test_ats_block_skips_missing_data():
    assert ats_block(None, None, None, None, None, [], "es") == []
    assert ats_block(None, None, None, "Dev", None, [], "es") == ["Re: Dev"]


def test_pack_body_has_ats_lines(client, auth_headers, monkeypatch):
    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    _set_profile(client, auth_headers)
    offer = {
        "source": "eures",
        "external_id": "ats-1",
        "title": "Python Developer",
        "company_name": "Acme",
        "location": "Barcelona",
        "description": "Buscamos Python con FastAPI.",
        "salary_range": None,
        "url": "https://example.com/ats",
    }
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [offer])
    client.post("/matches/search", headers=auth_headers)
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]
    pack = client.get(f"/matches/{match_id}/apply-pack", headers=auth_headers).json()
    assert "Re: Python Developer — Acme" in pack["email_body"]
    assert "Coincidencias clave: Python, FastAPI" in pack["email_body"]
    assert "Oferta: https://example.com/ats" in pack["email_body"]
