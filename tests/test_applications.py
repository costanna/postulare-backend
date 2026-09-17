from tests.conftest import register_and_login


def _create_application(client, headers, **overrides):
    payload = {
        "company_name": "Acme Corp",
        "position": "Backend Developer",
        "status": "saved",
        "source": "LinkedIn",
        "applied_at": "2026-01-10",
    }
    payload.update(overrides)
    return client.post("/applications", headers=headers, json=payload)


def test_create_and_get_application(client, auth_headers):
    create = _create_application(client, auth_headers)
    assert create.status_code == 201
    application_id = create.json()["id"]

    response = client.get(f"/applications/{application_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["company_name"] == "Acme Corp"


def test_list_applications_is_paginated(client, auth_headers):
    for i in range(3):
        _create_application(client, auth_headers, company_name=f"Company {i}")

    response = client.get("/applications?page=1&page_size=2", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["pages"] == 2
    assert len(body["items"]) == 2


def test_list_applications_filters_by_status(client, auth_headers):
    _create_application(client, auth_headers, company_name="Saved Co", status="saved")
    _create_application(client, auth_headers, company_name="Offer Co", status="offer")

    response = client.get("/applications?status=offer", headers=auth_headers)
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_name"] == "Offer Co"


def test_list_applications_filters_by_company_substring(client, auth_headers):
    _create_application(client, auth_headers, company_name="Google")
    _create_application(client, auth_headers, company_name="Amazon")

    response = client.get("/applications?company=goog", headers=auth_headers)
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["company_name"] == "Google"


def test_update_application_status_for_kanban(client, auth_headers):
    create = _create_application(client, auth_headers)
    application_id = create.json()["id"]

    response = client.patch(f"/applications/{application_id}", headers=auth_headers, json={"status": "interview"})
    assert response.status_code == 200
    assert response.json()["status"] == "interview"


def test_delete_application(client, auth_headers):
    create = _create_application(client, auth_headers)
    application_id = create.json()["id"]

    response = client.delete(f"/applications/{application_id}", headers=auth_headers)
    assert response.status_code == 204

    response = client.get(f"/applications/{application_id}", headers=auth_headers)
    assert response.status_code == 404


def test_user_cannot_access_another_users_application(client, auth_headers):
    create = _create_application(client, auth_headers)
    application_id = create.json()["id"]

    other_headers = register_and_login(client, email="other@example.com")
    response = client.get(f"/applications/{application_id}", headers=other_headers)
    assert response.status_code == 404


def test_applications_require_auth(client):
    response = client.get("/applications")
    assert response.status_code == 401
