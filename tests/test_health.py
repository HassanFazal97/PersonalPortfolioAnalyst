from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_down_db_without_database_url():
    # With no DATABASE_URL configured, the repo is absent and db/scheduler are
    # both reported down, but the endpoint itself must respond 200.
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"ok": False, "db": False, "scheduler": False}
