def _register(client, email="ana@example.com", password="supersecret123"):
    return client.post("/auth/register", json={"email": email, "password": password, "full_name": "Ana"})


def test_register_creates_user(client):
    response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ana@example.com"
    assert "hashed_password" not in body


def test_register_duplicate_email_returns_409(client):
    _register(client)
    response = _register(client)
    assert response.status_code == 409


def test_login_with_correct_credentials_returns_tokens(client):
    _register(client)
    response = client.post("/auth/login", json={"email": "ana@example.com", "password": "supersecret123"})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_with_wrong_password_returns_401(client):
    _register(client)
    response = client.post("/auth/login", json={"email": "ana@example.com", "password": "wrong-password"})
    assert response.status_code == 401


def test_me_requires_valid_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user(client):
    _register(client)
    login = client.post("/auth/login", json={"email": "ana@example.com", "password": "supersecret123"})
    token = login.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "ana@example.com"


def test_refresh_returns_new_access_token(client):
    _register(client)
    login = client.post("/auth/login", json={"email": "ana@example.com", "password": "supersecret123"})
    refresh_token = login.json()["refresh_token"]

    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_refresh_rejects_access_token(client):
    _register(client)
    login = client.post("/auth/login", json={"email": "ana@example.com", "password": "supersecret123"})
    access_token = login.json()["access_token"]

    response = client.post("/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401


def test_forgot_password_always_returns_202(client):
    response = client.post("/auth/forgot-password", json={"email": "unknown@example.com"})
    assert response.status_code == 202


def test_full_password_reset_flow(client, monkeypatch):
    import app.routers.auth as auth_router

    captured = {}

    def fake_send(to_email, reset_token):
        captured["email"] = to_email
        captured["token"] = reset_token

    monkeypatch.setattr(auth_router, "send_password_reset_email", fake_send)

    _register(client)
    response = client.post("/auth/forgot-password", json={"email": "ana@example.com"})
    assert response.status_code == 202
    assert captured["email"] == "ana@example.com"

    reset_response = client.post(
        "/auth/reset-password", json={"token": captured["token"], "new_password": "brand-new-pass"}
    )
    assert reset_response.status_code == 200

    old_login = client.post("/auth/login", json={"email": "ana@example.com", "password": "supersecret123"})
    assert old_login.status_code == 401

    new_login = client.post("/auth/login", json={"email": "ana@example.com", "password": "brand-new-pass"})
    assert new_login.status_code == 200


def test_reset_password_with_invalid_token_returns_400(client):
    response = client.post("/auth/reset-password", json={"token": "not-a-real-token", "new_password": "whatever123"})
    assert response.status_code == 400
