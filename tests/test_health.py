"""/health (Render's own health check) and /warmup (pinged by the frontend to wake a sleeping
free-tier instance) must both stay up and return the same trivial payload - see the comment on
/warmup in app/main.py for why there are two."""

from fastapi.testclient import TestClient


def test_health(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_warmup(client: TestClient):
    response = client.get("/warmup")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
