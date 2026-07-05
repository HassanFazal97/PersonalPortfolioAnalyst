from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_landing_public_no_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Cirvia" in resp.text
    assert "Not financial advice" in resp.text
