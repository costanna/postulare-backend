"""Automatización gratuita: apply-pack, auto-apply y CV generado en local."""
from datetime import date

import app.routers.matches as matches_router
from tests.test_matches import FAKE_OFFERS, _set_profile


def _match_id(client, headers, monkeypatch):
    _set_profile(client, headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kwargs: FAKE_OFFERS)
    client.post("/matches/search", headers=headers)
    return client.get("/matches", headers=headers).json()[0]["id"]


def test_cv_document_from_profile(client, auth_headers):
    client.patch("/profile", headers=auth_headers, json={"full_name": "Ana Costa", "skills": ["Python"]})
    response = client.get("/profile/cv-document?format=markdown", headers=auth_headers)
    assert response.status_code == 200
    assert "Ana Costa" in response.json()["content"]
    assert "Python" in response.json()["content"]


def test_apply_pack_does_not_convert(client, auth_headers, monkeypatch):
    match_id = _match_id(client, auth_headers, monkeypatch)
    pack = client.get(f"/matches/{match_id}/apply-pack", headers=auth_headers).json()
    assert "cover_letter" in pack and "cv_markdown" in pack
    assert "mailto_link" in pack and pack["mailto_link"].startswith("mailto:")
    assert isinstance(pack["checklist"], list) and pack["checklist"]
    # Sigue como nuevo: solo previsualiza.
    assert client.get("/matches?status=new", headers=auth_headers).json()[0]["id"] == match_id


def test_auto_apply_converts_and_returns_pack(client, auth_headers, monkeypatch):
    match_id = _match_id(client, auth_headers, monkeypatch)
    response = client.post(f"/matches/{match_id}/auto-apply", headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["application"]["status"] == "applied"
    assert body["application"]["applied_at"] == date.today().isoformat()
    assert body["pack"]["cover_letter"]
    assert body["needs_manual_step"] is True
    # Segunda vez: conflicto, sin duplicados.
    assert client.post(f"/matches/{match_id}/auto-apply", headers=auth_headers).status_code == 409


def test_bulk_auto_apply_converts_top_matches(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kwargs: FAKE_OFFERS)
    client.post("/matches/search", headers=auth_headers)
    response = client.post("/matches/auto-apply-bulk", headers=auth_headers, json={"min_score": 0, "limit": 5})
    assert response.status_code == 201
    assert len(response.json()["converted"]) >= 1
