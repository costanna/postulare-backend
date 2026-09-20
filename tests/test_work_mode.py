"""Modalidad de trabajo (remoto / híbrido / presencial): detección, filtro y etiqueta de cada oferta."""
import pytest

import app.routers.matches as matches_router
from app.services.work_mode import detect_work_mode, filter_by_work_mode
from tests.test_matches import _set_profile


def _offer(external_id="1", title="Desarrollador Python", location="Barcelona", description="Python y FastAPI.", company="Acme"):
    return {
        "source": "adzuna", "external_id": external_id, "title": title, "company_name": company,
        "location": location, "description": description, "salary_range": None, "url": None,
    }


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Puesto 100% remoto para toda España", "remote"),
        ("Trabajo en remoto desde donde quieras", "remote"),
        ("Fully remote position", "remote"),
        ("Ofrecemos teletrabajo total", "remote"),
        ("Es possible el teletreball complet", "remote"),
        ("Work from home", "remote"),
        ("Modelo híbrido: 3 días en la oficina", "hybrid"),
        ("Hybrid working, 2 days at the office", "hybrid"),
        ("Trabajo semipresencial", "hybrid"),
        ("Presencial y teletrabajo según el equipo", "hybrid"),
        ("Remoto / presencial", "hybrid"),
        ("Teletrabajo parcial", "hybrid"),
        ("2 días a la semana en la oficina", "hybrid"),
        ("Puesto presencial en Barcelona", "onsite"),
        ("On-site role", "onsite"),
        ("Trabajarás en nuestras oficinas del centro", "onsite"),
        ("Sin teletrabajo", "onsite"),
        ("No es remoto", "onsite"),
        ("No hay opción de teletrabajo", "onsite"),
        ("Remoto o presencial, tú eliges: presencial en la oficina", "hybrid"),
        ("Desarrollador Python con FastAPI en equipo ágil", None),
        ("", None),
    ],
)
def test_detection(text, expected):
    assert detect_work_mode(_offer(description=text, location=None)) == expected


def test_it_reads_the_title_and_the_location_too():
    assert detect_work_mode(_offer(title="Backend Developer (Remoto)", description=None)) == "remote"
    assert detect_work_mode(_offer(location="Remoto", description=None)) == "remote"
    assert detect_work_mode(_offer(title="Desarrollador", description="Híbrido", location=None)) == "hybrid"


def test_infojobs_telework_values_are_understood():
    assert detect_work_mode(_offer(description="Informática. Solo teletrabajo")) == "remote"
    assert detect_work_mode(_offer(description="Informática. Teletrabajo y presencial")) == "hybrid"
    assert detect_work_mode(_offer(description="Informática. Presencial")) == "onsite"


def test_words_that_merely_contain_the_letters_do_not_fire():
    assert detect_work_mode(_offer(description="Conocimientos de control remotoxyz")) is None
    assert detect_work_mode(_offer(description="Empresa presencialista")) is None


OFFERS = [
    _offer("r", description="100% remoto"),
    _offer("h", description="Modelo híbrido"),
    _offer("p", description="Puesto presencial"),
    _offer("u", description="Sin datos sobre el lugar"),
]


def test_filter_modes():
    ids = lambda mode: [o["external_id"] for o in filter_by_work_mode(OFFERS, mode)]  # noqa: E731
    assert ids("any") == ["r", "h", "p", "u"]
    assert ids("remote") == ["r"]
    assert ids("hybrid") == ["h"]
    assert ids("onsite") == ["p", "u"]  # las que no dicen nada se consideran presenciales


@pytest.fixture()
def calls(monkeypatch):
    monkeypatch.setattr(matches_router.settings, "MATCH_SEARCH_COOLDOWN_MINUTES", 0)
    seen = []

    def fake(query, location=None, **kwargs):
        seen.append(kwargs)
        return [dict(o, title=f"Dev {o['external_id']}", company_name=f"Empresa {o['external_id']}") for o in OFFERS]

    monkeypatch.setattr(matches_router, "search_job_offers", fake)
    return seen


def _search(client, headers, mode):
    _set_profile(client, headers)
    client.put("/matches/filters", headers=headers, json={"work_mode": mode})
    assert client.post("/matches/search", headers=headers).status_code == 200
    return sorted(m["job_offer"]["company_name"] for m in client.get("/matches", headers=headers).json())


@pytest.mark.parametrize(
    "mode,expected",
    [("any", ["Empresa h", "Empresa p", "Empresa r", "Empresa u"]), ("remote", ["Empresa r"]),
     ("hybrid", ["Empresa h"]), ("onsite", ["Empresa p", "Empresa u"])],
)
def test_search_applies_the_chosen_mode(client, auth_headers, calls, mode, expected):
    assert _search(client, auth_headers, mode) == expected


def test_remote_and_hybrid_ask_adzuna_for_more_results_and_onsite_does_not(client, auth_headers, calls):
    _search(client, auth_headers, "remote")
    _search(client, auth_headers, "onsite")
    assert [c["results_per_page"] for c in calls] == [50, 20]


def test_each_offer_shows_its_detected_mode_and_null_when_unknown(client, auth_headers, calls):
    _search(client, auth_headers, "any")
    modes = {m["job_offer"]["company_name"]: m["job_offer"]["work_mode"] for m in client.get("/matches", headers=auth_headers).json()}
    assert modes == {"Empresa r": "remote", "Empresa h": "hybrid", "Empresa p": "onsite", "Empresa u": None}


def test_the_choice_is_saved_defaults_to_any_and_rejects_invalid_values(client, auth_headers):
    assert client.get("/matches/filters", headers=auth_headers).json()["filters"]["work_mode"] == "any"
    client.put("/matches/filters", headers=auth_headers, json={"work_mode": "hybrid"})
    assert client.get("/matches/filters", headers=auth_headers).json()["filters"]["work_mode"] == "hybrid"
    assert client.put("/matches/filters", headers=auth_headers, json={"work_mode": "mars"}).status_code == 422
