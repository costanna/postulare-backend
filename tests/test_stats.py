def _create_application(client, headers, **overrides):
    payload = {"company_name": "Acme", "position": "Dev", "status": "saved"}
    payload.update(overrides)
    return client.post("/applications", headers=headers, json=payload)


def test_summary_on_empty_account(client, auth_headers):
    response = client.get("/stats/summary", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_applications"] == 0
    assert body["response_rate"] == 0.0


def test_summary_computes_response_rate(client, auth_headers):
    _create_application(client, auth_headers, status="saved")
    _create_application(client, auth_headers, status="applied")
    _create_application(client, auth_headers, status="interview")
    _create_application(client, auth_headers, status="rejected")

    response = client.get("/stats/summary", headers=auth_headers)
    body = response.json()
    assert body["total_applications"] == 4
    assert body["total_applied"] == 3  # todas menos "saved"
    assert body["total_interviews"] == 1
    assert body["total_rejected"] == 1
    # respondidas (interview+offer+rejected) = 2 de 3 aplicadas -> 66.7%
    assert body["response_rate"] == 66.7


def test_by_status_includes_all_statuses_even_with_zero(client, auth_headers):
    _create_application(client, auth_headers, status="saved")

    response = client.get("/stats/by-status", headers=auth_headers)
    body = response.json()
    statuses = {item["status"]: item["count"] for item in body}
    assert statuses["saved"] == 1
    assert statuses["offer"] == 0
    assert set(statuses.keys()) == {"saved", "applied", "interview", "offer", "rejected", "withdrawn"}


def test_timeline_groups_by_month(client, auth_headers):
    _create_application(client, auth_headers, company_name="A", applied_at="2026-01-15")
    _create_application(client, auth_headers, company_name="B", applied_at="2026-01-20")
    _create_application(client, auth_headers, company_name="C", applied_at="2026-02-01")

    response = client.get("/stats/timeline", headers=auth_headers)
    body = response.json()
    assert body == [{"month": "2026-01", "count": 2}, {"month": "2026-02", "count": 1}]


def test_by_source_groups_and_orders_by_count(client, auth_headers):
    _create_application(client, auth_headers, company_name="A", source="LinkedIn")
    _create_application(client, auth_headers, company_name="B", source="LinkedIn")
    _create_application(client, auth_headers, company_name="C", source="Referido")
    _create_application(client, auth_headers, company_name="D")  # sin source

    response = client.get("/stats/by-source", headers=auth_headers)
    body = response.json()
    assert body[0] == {"source": "LinkedIn", "count": 2}
    sources = {item["source"] for item in body}
    assert "Desconocido" in sources


def test_stats_are_isolated_between_users(client, auth_headers):
    from tests.conftest import register_and_login

    _create_application(client, auth_headers, status="applied")

    other_headers = register_and_login(client, email="other@example.com")
    response = client.get("/stats/summary", headers=other_headers)
    assert response.json()["total_applications"] == 0


def test_stats_require_auth(client):
    response = client.get("/stats/summary")
    assert response.status_code == 401
