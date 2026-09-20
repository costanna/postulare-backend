"""Enlace de recuperar contraseña de un solo uso e idioma guardado de la carta."""
from datetime import timedelta

import pytest

import app.routers.auth as auth_router
import app.routers.matches as matches_router
from app.core.config import settings
from app.core.security import _create_token, decode_token
from tests.test_matches import FAKE_OFFERS, _set_profile


@pytest.fixture()
def captured_token(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(auth_router, "send_password_reset_email", lambda to, token: captured.update(token=token))
    client.post("/auth/register", json={"email": "ana@example.com", "password": "supersecret123"})
    client.post("/auth/forgot-password", json={"email": "ana@example.com"})
    return captured["token"]


def _reset(client, token, password="brand-new-pass"):
    return client.post("/auth/reset-password", json={"token": token, "new_password": password})


def test_reset_link_works_once(client, captured_token):
    assert _reset(client, captured_token).status_code == 200
    again = _reset(client, captured_token, "another-pass-1")
    assert again.status_code == 400
    assert client.post("/auth/login", json={"email": "ana@example.com", "password": "brand-new-pass"}).status_code == 200


def test_an_older_link_dies_when_a_newer_one_is_used(client, monkeypatch, captured_token):
    tokens = [captured_token]
    monkeypatch.setattr(auth_router, "send_password_reset_email", lambda to, token: tokens.append(token))
    client.post("/auth/forgot-password", json={"email": "ana@example.com"})

    assert _reset(client, tokens[1]).status_code == 200
    assert _reset(client, tokens[0], "yet-another-pass").status_code == 400


def test_a_reset_token_without_the_password_fingerprint_is_rejected(client, captured_token):
    subject = decode_token(captured_token, expected_type="reset")
    legacy = _create_token(subject, "reset", timedelta(minutes=30))
    assert _reset(client, legacy).status_code == 400


@pytest.fixture()
def match_id(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kwargs: FAKE_OFFERS)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    client.post("/matches/search", headers=auth_headers)
    return client.get("/matches", headers=auth_headers).json()[0]["id"]


def test_the_letter_remembers_its_language(client, auth_headers, match_id):
    url = f"/matches/{match_id}/cover-letter"
    assert client.post(url, headers=auth_headers, json={"language": "ca"}).json()["language"] == "ca"

    stored = client.post(url, headers=auth_headers, json={"language": "en"}).json()
    assert stored["language"] == "ca"  # sin regenerar se devuelve la guardada, con su idioma
    assert client.get("/matches", headers=auth_headers).json()[0]["cover_letter_language"] == "ca"

    regenerated = client.post(url, headers=auth_headers, json={"language": "en", "regenerate": True}).json()
    assert regenerated["language"] == "en"
