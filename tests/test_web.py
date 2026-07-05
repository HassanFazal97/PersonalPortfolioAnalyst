from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def _client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    return TestClient(create_app())


def test_public_pages_no_token(monkeypatch):
    # The marketing + legal pages must be reachable without a bearer token
    # (users and SnapTrade/partner reviewers hit them unauthenticated).
    with _client(monkeypatch) as client:
        for path in ("/", "/contact", "/privacy", "/terms", "/pricing"):
            resp = client.get(path)
            assert resp.status_code == 200, path
            assert "text/html" in resp.headers.get("content-type", ""), path
            assert "Cirvia" in resp.text, path


def test_pages_have_expected_content(monkeypatch):
    with _client(monkeypatch) as client:
        assert "Not financial advice" in client.get("/").text
        assert "fazalhassan@live.ca" in client.get("/contact").text
        assert "Privacy Policy" in client.get("/privacy").text
        assert "Terms of Service" in client.get("/terms").text
        pricing = client.get("/pricing").text
        assert "Free" in pricing and "Pro" in pricing and "$12" in pricing
        # cross-links between pages
        home = client.get("/").text
        assert "/privacy" in home and "/terms" in home and "/contact" in home


def test_protected_route_still_requires_token(monkeypatch):
    with _client(monkeypatch) as client:
        assert client.post("/chat", json={"message": "hi"}).status_code == 401
