"""Descubrimiento de email en la web de la empresa. Sin llamadas reales."""
import pytest

import app.services.company_lookup as lookup
from app.services.company_lookup import discover_company_email, domain_for_company


class _Resp:
    def __init__(self, payload=None, text="", status=200):
        self._payload = payload
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code != 200:
            import httpx

            raise httpx.HTTPStatusError("err", request=None, response=None)  # type: ignore[arg-type]

    def json(self):
        return self._payload


def _mock(monkeypatch, clearbit, pages):
    def fake_get(url, params=None, headers=None, follow_redirects=False, timeout=None):
        if "clearbit" in url:
            return _Resp(payload=clearbit)
        return _Resp(text=pages.get(url, ""), status=200 if url in pages else 404)

    monkeypatch.setattr(lookup.httpx, "get", fake_get)


def test_direct_email_wins_without_http(monkeypatch):
    monkeypatch.setattr(
        lookup.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sin HTTP"))
    )
    email, source = discover_company_email("Acme", "Dev", "Escribe a hola@acme.example.")
    assert (email, source) == ("hola@acme.example", "offer")


def test_discovers_email_on_company_website(monkeypatch):
    _mock(
        monkeypatch,
        [{"name": "Acme Corp", "domain": "acme.example"}],
        {"https://acme.example": "<p>Escríbenos a jobs@acme.example o a prensa@otro.com</p>"},
    )
    assert domain_for_company("Acme Corp") == "acme.example"
    email, source = discover_company_email("Acme Corp", "Dev", "Sin email aquí.")
    assert (email, source) == ("jobs@acme.example", "website")


def test_ignores_other_domains_and_non_contact(monkeypatch):
    _mock(
        monkeypatch,
        [{"name": "Acme Corp", "domain": "acme.example"}],
        {"https://acme.example": "x@noreply@acme.example y webmaster@acme.example"},
    )
    email, source = discover_company_email("Acme Corp", "Dev", "Sin email.")
    assert (email, source) == (None, None)


def test_no_domain_match_returns_none(monkeypatch):
    _mock(monkeypatch, [{"name": "Otra Cosa", "domain": "otra.example"}], {})
    assert discover_company_email("Acme Corp", "Dev", "Sin email.") == (None, None)


def test_pack_shows_discovered_email(client, auth_headers, monkeypatch):
    import app.routers.matches as matches_router
    from tests.test_matches import _set_profile

    _mock(
        monkeypatch,
        [{"name": "Acme", "domain": "acme.example"}],
        {"https://acme.example": "Jobs: jobs@acme.example"},
    )
    _set_profile(client, auth_headers)
    offer = {
        "source": "eures",
        "external_id": "lookup-1",
        "title": "Camarero con experiencia",
        "company_name": "Acme",
        "location": "Barcelona",
        "description": "Buscamos camarero con experiencia.",
        "salary_range": None,
        "url": "https://example.com/lookup",
    }
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kw: [offer])
    client.post("/matches/search", headers=auth_headers)
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]
    pack = client.get(f"/matches/{match_id}/apply-pack", headers=auth_headers).json()
    assert pack["contact_email"] == "jobs@acme.example"
    assert pack["contact_source"] == "website"
    assert pack["mailto_link"].startswith("mailto:jobs@acme.example?")
