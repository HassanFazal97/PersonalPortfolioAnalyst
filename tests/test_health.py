from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

TOKEN = "test-secret-token"


def _client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    return TestClient(create_app())


def test_health_requires_token(monkeypatch):
    with _client(monkeypatch) as client:
        assert client.get("/health").status_code == 401
        assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_health_ok_with_token(monkeypatch):
    with _client(monkeypatch) as client:
        resp = client.get("/health", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "db": False, "scheduler": False}


def test_protected_routes_401_without_token(monkeypatch):
    with _client(monkeypatch) as client:
        assert client.post("/chat", json={"message": "hi"}).status_code == 401
        assert client.get("/digest/latest").status_code == 401
        assert client.get("/runs").status_code == 401
