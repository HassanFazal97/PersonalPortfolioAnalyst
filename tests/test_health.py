from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

TOKEN = "test-secret-token"


def _client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    return TestClient(create_app())


def test_health_public_no_token(monkeypatch):
    # /health is deliberately exempt from bearer auth so platform liveness
    # probes and uptime pingers (which cannot attach the token) can reach it.
    with _client(monkeypatch) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "db": False, "scheduler": False, "macro_scheduler": False, "delivery_scheduler": False}


def test_health_ok_with_token(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get("/health", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "db": False, "scheduler": False, "macro_scheduler": False, "delivery_scheduler": False}


def test_protected_routes_401_without_token(monkeypatch):
    with _client(monkeypatch) as client:
        assert client.post("/chat", json={"message": "hi"}).status_code == 401
        assert client.get("/digest/latest").status_code == 401
        assert client.get("/runs").status_code == 401
