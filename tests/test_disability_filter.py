"""Filtro "discapacidad": solo empresas que la mencionan / excluirlas / no filtrar."""
import pytest

import app.routers.matches as matches_router
from app.services.job_search import filter_by_disability, mentions_disability
from tests.test_matches import _set_profile


def _offer(external_id, title="Desarrollador Python", company="Acme", description="Python y FastAPI."):
    return {
        "source": "adzuna", "external_id": external_id, "title": title, "company_name": company,
        "location": "Barcelona", "description": description, "salary_range": None, "url": None,
    }


@pytest.mark.parametrize(
    "text",
    [
        "Empresa comprometida con la inclusión de personas con discapacidad",
        "Es valorarà el certificat de discapacitat",
        "Se ofrece a candidatos con DISCAPACIDAD reconocida",
        "Centro especial de empleo para personas discapacitadas",
        "Reconocimiento de minusvalía igual o superior al 33%",
        "We are a disability confident employer",
        "Apostamos por la diversidad funcional",
    ],
)
def test_it_recognizes_the_word_in_spanish_catalan_and_english(text):
    assert mentions_disability(_offer("x", description=text))


def test_it_also_looks_at_the_company_name_and_the_title():
    assert mentions_disability(_offer("x", company="Fundación para la Discapacidad"))
    assert mentions_disability(_offer("x", title="Programador/a (personas con discapacidad)"))


@pytest.mark.parametrize("text", ["Desarrollador Python en equipo ágil", "", None, "Capacidad de análisis y aprendizaje"])
def test_it_does_not_fire_on_unrelated_text(text):
    assert not mentions_disability(_offer("x", description=text))


def test_filter_modes():
    offers = [_offer("a"), _offer("b", description="Personas con discapacidad"), _offer("c")]
    assert [o["external_id"] for o in filter_by_disability(offers, "any")] == ["a", "b", "c"]
    assert [o["external_id"] for o in filter_by_disability(offers, "require")] == ["b"]
    assert [o["external_id"] for o in filter_by_disability(offers, "exclude")] == ["a", "c"]


OFFERS = [
    _offer("1", title="Desarrollador Python A", company="Alfa", description="Inclusión de personas con discapacidad."),
    _offer("2", title="Desarrollador Python B", company="Beta"),
    _offer("3", title="Desarrollador Python C", company="Gamma"),
]


@pytest.fixture()
def calls(monkeypatch):
    seen = []

    def fake(query, location=None, **kwargs):
        seen.append(kwargs)
        return OFFERS

    monkeypatch.setattr(matches_router, "search_job_offers", fake)
    return seen


def _search(client, headers, disability):
    _set_profile(client, headers)
    client.put("/matches/filters", headers=headers, json={"disability": disability})
    response = client.post("/matches/search", headers=headers)
    assert response.status_code == 200
    return response.json(), sorted(m["job_offer"]["company_name"] for m in client.get("/matches", headers=headers).json())


def test_default_does_not_filter_and_asks_for_the_usual_page_size(client, auth_headers, calls):
    result, companies = _search(client, auth_headers, "any")
    assert companies == ["Alfa", "Beta", "Gamma"] and calls[0]["results_per_page"] == 20


def test_require_keeps_only_inclusive_offers_and_asks_for_more_results(client, auth_headers, calls):
    result, companies = _search(client, auth_headers, "require")
    assert companies == ["Alfa"] and result["fetched"] == 1
    assert calls[0]["results_per_page"] == 50


def test_exclude_drops_offers_that_mention_disability(client, auth_headers, calls):
    _, companies = _search(client, auth_headers, "exclude")
    assert companies == ["Beta", "Gamma"]


def test_the_choice_is_saved_and_defaults_to_any(client, auth_headers):
    assert client.get("/matches/filters", headers=auth_headers).json()["filters"]["disability"] == "any"
    client.put("/matches/filters", headers=auth_headers, json={"disability": "require"})
    assert client.get("/matches/filters", headers=auth_headers).json()["filters"]["disability"] == "require"


def test_an_invalid_value_is_rejected(client, auth_headers):
    assert client.put("/matches/filters", headers=auth_headers, json={"disability": "maybe"}).status_code == 422


def test_filters_saved_before_this_option_existed_still_load(client, auth_headers, db_session):
    from app.models.user import User

    user = db_session.query(User).first()
    user.search_filters = {"keywords": "angular", "radius_km": 30}
    db_session.commit()
    body = client.get("/matches/filters", headers=auth_headers).json()
    assert body["filters"]["disability"] == "any" and body["filters"]["keywords"] == "angular"
