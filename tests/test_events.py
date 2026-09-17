from tests.conftest import register_and_login


def _create_application(client, headers):
    payload = {"company_name": "Acme Corp", "position": "Backend Developer"}
    return client.post("/applications", headers=headers, json=payload).json()["id"]


def test_create_and_list_events(client, auth_headers):
    application_id = _create_application(client, auth_headers)

    create = client.post(
        f"/applications/{application_id}/events",
        headers=auth_headers,
        json={"type": "interview", "description": "Entrevista técnica"},
    )
    assert create.status_code == 201

    response = client.get(f"/applications/{application_id}/events", headers=auth_headers)
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["type"] == "interview"


def test_create_event_on_missing_application_returns_404(client, auth_headers):
    import uuid

    response = client.post(
        f"/applications/{uuid.uuid4()}/events",
        headers=auth_headers,
        json={"type": "note", "description": "test"},
    )
    assert response.status_code == 404


def test_delete_event(client, auth_headers):
    application_id = _create_application(client, auth_headers)
    event_id = client.post(
        f"/applications/{application_id}/events",
        headers=auth_headers,
        json={"type": "follow_up", "description": "Seguimiento"},
    ).json()["id"]

    response = client.delete(f"/events/{event_id}", headers=auth_headers)
    assert response.status_code == 204

    events = client.get(f"/applications/{application_id}/events", headers=auth_headers).json()
    assert events == []


def test_user_cannot_delete_another_users_event(client, auth_headers):
    application_id = _create_application(client, auth_headers)
    event_id = client.post(
        f"/applications/{application_id}/events",
        headers=auth_headers,
        json={"type": "note", "description": "privado"},
    ).json()["id"]

    other_headers = register_and_login(client, email="other@example.com")
    response = client.delete(f"/events/{event_id}", headers=other_headers)
    assert response.status_code == 404
