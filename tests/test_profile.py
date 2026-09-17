def test_get_profile_requires_auth(client):
    response = client.get("/profile")
    assert response.status_code == 401


def test_get_profile_returns_defaults(client, auth_headers):
    response = client.get("/profile", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "ana@example.com"
    assert body["skills"] == []
    assert body["preferred_language"] == "es"


def test_patch_profile_updates_only_sent_fields(client, auth_headers):
    response = client.patch(
        "/profile",
        headers=auth_headers,
        json={
            "skills": ["Angular", "Python", "FastAPI"],
            "location": "Barcelona",
            "seniority": "junior",
            "preferred_language": "ca",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["skills"] == ["Angular", "Python", "FastAPI"]
    assert body["location"] == "Barcelona"
    assert body["seniority"] == "junior"
    assert body["preferred_language"] == "ca"
    assert body["full_name"] == "Ana"  # no tocado, se mantiene


def test_patch_profile_rejects_negative_salary(client, auth_headers):
    response = client.patch("/profile", headers=auth_headers, json={"min_salary": -100})
    assert response.status_code == 422
