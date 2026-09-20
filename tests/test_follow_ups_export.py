"""Recordatorios de seguimiento y exportación a CSV."""
import csv
import io
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import settings
from tests.conftest import register_and_login


def _days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _create(client, headers, company, status="applied", days_ago: int | None = None, **extra) -> str:
    payload = {"company_name": company, "position": "Dev", "status": status, **extra}
    if days_ago is not None:
        payload["applied_at"] = _days_ago(days_ago)
    response = client.post("/applications", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _follow_ups(client, headers) -> list[dict]:
    response = client.get("/applications/follow-ups", headers=headers)
    assert response.status_code == 200
    return response.json()


# --- Seguimientos ------------------------------------------------------------------


def test_follow_ups_lists_only_stale_open_applications_oldest_first(client, auth_headers):
    _create(client, auth_headers, "Reciente", days_ago=2)
    _create(client, auth_headers, "Antigua", days_ago=20)
    _create(client, auth_headers, "Justo", days_ago=settings.FOLLOW_UP_DAYS)
    _create(client, auth_headers, "En entrevistas", status="interview", days_ago=15)
    _create(client, auth_headers, "Guardada", status="saved", days_ago=30)
    _create(client, auth_headers, "Rechazada", status="rejected", days_ago=30)
    _create(client, auth_headers, "Oferta", status="offer", days_ago=30)

    items = _follow_ups(client, auth_headers)
    assert [i["application"]["company_name"] for i in items] == ["Antigua", "En entrevistas", "Justo"]
    assert [i["days_waiting"] for i in items] == [20, 15, settings.FOLLOW_UP_DAYS]
    assert items[0]["last_activity"] == _days_ago(20)


def test_one_day_before_the_threshold_is_not_due(client, auth_headers):
    _create(client, auth_headers, "Casi", days_ago=settings.FOLLOW_UP_DAYS - 1)
    assert _follow_ups(client, auth_headers) == []


def test_a_follow_up_event_resets_the_clock(client, auth_headers):
    app_id = _create(client, auth_headers, "Con seguimiento", days_ago=20)
    assert len(_follow_ups(client, auth_headers)) == 1

    event = client.post(
        f"/applications/{app_id}/events", headers=auth_headers, json={"type": "follow_up", "description": "Correo"}
    )
    assert event.status_code == 201
    assert _follow_ups(client, auth_headers) == []


def test_an_old_event_does_not_hide_the_reminder(client, auth_headers):
    app_id = _create(client, auth_headers, "Evento viejo", days_ago=30)
    old = (datetime.now(timezone.utc) - timedelta(days=12)).isoformat()
    client.post(f"/applications/{app_id}/events", headers=auth_headers, json={"type": "note", "event_date": old})

    items = _follow_ups(client, auth_headers)
    assert [i["days_waiting"] for i in items] == [12]


def test_application_without_applied_date_counts_from_creation(client, auth_headers):
    _create(client, auth_headers, "Sin fecha")  # recién creada: no toca todavía
    assert _follow_ups(client, auth_headers) == []


def test_follow_ups_are_private_and_require_auth(client, auth_headers):
    _create(client, auth_headers, "De Ana", days_ago=20)
    other = register_and_login(client, email="otra@example.com")
    assert _follow_ups(client, other) == []
    assert client.get("/applications/follow-ups").status_code == 401


def test_follow_ups_route_is_not_swallowed_by_application_id(client, auth_headers):
    response = client.get("/applications/follow-ups", headers=auth_headers)
    assert response.status_code == 200 and response.json() == []


# --- CSV -----------------------------------------------------------------------------


def _export(client, headers) -> tuple[str, str]:
    response = client.get("/applications/export", headers=headers)
    assert response.status_code == 200
    return response.text, response.headers["content-type"]


def test_export_returns_all_own_applications_as_csv(client, auth_headers):
    _create(client, auth_headers, "Nubelia, S.L.", days_ago=3, salary_range="30.000 €", notes='Dijo "vuelve en mayo"')
    _create(client, auth_headers, "Ñandú Tech", status="saved")
    other = register_and_login(client, email="otra@example.com")
    _create(client, other, "Ajena")

    text, content_type = _export(client, auth_headers)
    assert content_type.startswith("text/csv")
    assert text.startswith(chr(0xFEFF))  # BOM: Excel respeta las tildes

    rows = list(csv.DictReader(io.StringIO(text.lstrip(chr(0xFEFF)))))
    assert {r["company"] for r in rows} == {"Nubelia, S.L.", "Ñandú Tech"}
    row = next(r for r in rows if r["company"] == "Nubelia, S.L.")
    assert row["status"] == "applied" and row["applied_at"] == _days_ago(3)
    assert row["salary_range"] == "30.000 €" and row["notes"] == 'Dijo "vuelve en mayo"'
    assert list(rows[0].keys()) == [
        "company", "position", "status", "applied_at", "source", "salary_range", "job_url", "notes", "created_at"
    ]


def test_export_has_download_filename(client, auth_headers):
    response = client.get("/applications/export", headers=auth_headers)
    assert 'filename="postulare-candidaturas.csv"' in response.headers["content-disposition"]


@pytest.mark.parametrize("dangerous", ["=HYPERLINK(\"http://x\")", "+1+1", "-2+3", "@SUM(A1)"])
def test_export_neutralizes_spreadsheet_formulas(client, auth_headers, dangerous):
    _create(client, auth_headers, dangerous, notes=dangerous)
    text, _ = _export(client, auth_headers)
    row = next(csv.DictReader(io.StringIO(text.lstrip(chr(0xFEFF)))))
    assert row["company"] == "'" + dangerous
    assert row["notes"] == "'" + dangerous


def test_export_empty_has_only_header_and_requires_auth(client, auth_headers):
    text, _ = _export(client, auth_headers)
    assert len(text.lstrip(chr(0xFEFF)).strip().splitlines()) == 1
    assert client.get("/applications/export").status_code == 401
