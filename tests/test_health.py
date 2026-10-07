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


def test_health_and_warmup_accept_head_for_uptime_monitors(client: TestClient):
    # Monitores como Better Uptime/UptimeRobot pueden comprobar con HEAD para
    # ahorrar ancho de banda: antes devolvían 405 y disparaban incidentes.
    assert client.head("/health").status_code == 200
    assert client.head("/warmup").status_code == 200
