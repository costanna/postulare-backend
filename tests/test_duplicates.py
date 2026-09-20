"""Ofertas repetidas: reanuncios con otro id, duplicados en la misma búsqueda y ofertas
que ya están en las candidaturas del usuario."""
import app.routers.matches as matches_router
from app.services.duplicates import TrackedIndex, normalize, normalize_url, offer_key
from tests.conftest import register_and_login
from tests.test_matches import _set_profile


def _offer(external_id, title="Junior Angular Developer", company="TechCorp", location="Barcelona", url=None):
    return {
        "source": "adzuna",
        "external_id": external_id,
        "title": title,
        "company_name": company,
        "location": location,
        "description": "Angular y Python.",
        "salary_range": None,
        "url": url or f"https://example.com/jobs/{external_id}",
    }


def _search(client, headers, monkeypatch, offers):
    monkeypatch.setattr(matches_router, "search_job_offers", lambda query, location=None, **kwargs: offers)
    response = client.post("/matches/search", headers=headers)
    assert response.status_code == 200
    return response.json()


def _fresh_cooldown(db_session):
    from app.models.user import User

    db_session.query(User).update({User.last_match_search_at: None})
    db_session.commit()


def test_normalize_ignores_case_accents_and_punctuation():
    assert normalize("  Ñandú-Tech, S.L. ") == "nandu tech s l"
    assert offer_key("TechCorp", "Junior Dev", "Barcelona") == offer_key("techcorp", "JUNIOR  dev!", "barcelona")
    assert offer_key("A", "Dev", "Girona") != offer_key("A", "Dev", "Madrid")


def test_normalize_url_drops_scheme_tracking_and_trailing_slash():
    assert normalize_url("https://www.Example.com/jobs/1/?utm_source=x#top") == "example.com/jobs/1"
    assert normalize_url(None) == ""


def test_tracked_index_matches_by_company_and_position_or_by_url(client, db_session, auth_headers):
    from app.models.user import User

    client.post(
        "/applications",
        headers=auth_headers,
        json={"company_name": "TechCorp", "position": "Dev", "job_url": "https://example.com/j/9?ref=a"},
    )
    user = db_session.query(User).first()
    index = TrackedIndex.for_user(db_session, user.id)
    assert index.contains("techcorp", "DEV", None)
    assert index.contains("Otra", "Otro puesto", "http://www.example.com/j/9/")
    assert not index.contains("Otra", "Otro puesto", "https://example.com/j/10")


def test_same_offer_repeated_in_one_search_is_kept_once(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    result = _search(client, auth_headers, monkeypatch, [_offer("1"), _offer("2"), _offer("3", location="Madrid")])
    # 1 y 2 son la misma oferta (mismo título, empresa y ciudad) con ids distintos
    assert result["new_matches"] == 2
    assert result["skipped_duplicates"] == 1
    assert len(client.get("/matches", headers=auth_headers).json()) == 2


def test_repost_with_new_id_is_skipped_in_later_search(client, db_session, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    _search(client, auth_headers, monkeypatch, [_offer("1")])
    _fresh_cooldown(db_session)

    result = _search(client, auth_headers, monkeypatch, [_offer("99")])
    assert result["new_matches"] == 0 and result["skipped_duplicates"] == 1
    assert len(client.get("/matches", headers=auth_headers).json()) == 1


def test_dismissed_offer_does_not_come_back_as_repost(client, db_session, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    _search(client, auth_headers, monkeypatch, [_offer("1")])
    match_id = client.get("/matches", headers=auth_headers).json()[0]["id"]
    client.post(f"/matches/{match_id}/dismiss", headers=auth_headers)
    _fresh_cooldown(db_session)

    result = _search(client, auth_headers, monkeypatch, [_offer("77")])
    assert result["new_matches"] == 0 and result["skipped_duplicates"] == 1


def test_same_offer_again_is_refreshed_not_counted_as_duplicate(client, db_session, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    _search(client, auth_headers, monkeypatch, [_offer("1")])
    _fresh_cooldown(db_session)

    result = _search(client, auth_headers, monkeypatch, [_offer("1")])
    assert result["new_matches"] == 0
    assert result["updated_matches"] == 1
    assert result["skipped_duplicates"] == 0


def test_offer_already_in_applications_is_skipped(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    client.post("/applications", headers=auth_headers, json={"company_name": "techcorp", "position": "Junior Angular Developer"})
    client.post(
        "/applications",
        headers=auth_headers,
        json={"company_name": "Otra", "position": "Otro", "job_url": "https://www.example.com/jobs/2/?utm=x"},
    )

    result = _search(client, auth_headers, monkeypatch, [_offer("1"), _offer("2", title="Distinto", company="Nueva"), _offer("3", title="Libre", company="Libre SL")])
    assert result["new_matches"] == 1
    assert result["skipped_duplicates"] == 2
    assert [m["job_offer"]["company_name"] for m in client.get("/matches", headers=auth_headers).json()] == ["Libre SL"]


def test_duplicates_are_per_user(client, db_session, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    _search(client, auth_headers, monkeypatch, [_offer("1")])

    other = register_and_login(client, email="otra@example.com")
    _set_profile(client, other)
    result = _search(client, other, monkeypatch, [_offer("1")])
    assert result["new_matches"] == 1 and result["skipped_duplicates"] == 0


def test_already_tracked_flag_appears_after_converting_or_adding_manually(client, auth_headers, monkeypatch):
    _set_profile(client, auth_headers)
    _search(client, auth_headers, monkeypatch, [_offer("1"), _offer("2", title="Otro", company="Otra")])
    matches = client.get("/matches", headers=auth_headers).json()
    assert [m["already_tracked"] for m in matches] == [False, False]

    target = next(m for m in matches if m["job_offer"]["company_name"] == "TechCorp")
    client.post(f"/matches/{target['id']}/convert", headers=auth_headers)

    flags = {m["id"]: m["already_tracked"] for m in client.get("/matches", headers=auth_headers).json()}
    assert flags[target["id"]] is True
    assert list(flags.values()).count(True) == 1
