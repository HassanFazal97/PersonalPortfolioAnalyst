"""Web app pages: /app, /app/onboarding, /app/dashboard.

These are auth-exempt HTML shells; the browser authenticates API calls with a
Supabase JWT. Verify they render with config injected, and degrade gracefully
when Supabase isn't configured.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "sb_publishable_test123")
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


@pytest.mark.parametrize("path", ["/app", "/app/onboarding", "/app/dashboard"])
def test_app_pages_render_without_token(client, path):
    resp = client.get(path)
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "https://example.supabase.co" in resp.text
    assert "sb_publishable_test123" in resp.text
    assert "supabase-js" in resp.text  # CDN script tag


def test_dashboard_has_news_sections(client):
    resp = client.get("/app/dashboard")
    assert resp.status_code == 200
    assert 'id="general-news"' in resp.text
    assert 'id="holding-news"' in resp.text
    assert 'id="watchlist-card"' in resp.text


def test_onboarding_has_watchlist_panel(client):
    resp = client.get("/app/onboarding")
    assert resp.status_code == 200
    assert 'id="panel-watchlist"' in resp.text


def test_app_pages_noindex(client):
    resp = client.get("/app")
    assert '<meta name="robots" content="noindex">' in resp.text


@pytest.mark.parametrize("path", ["/app", "/app/onboarding", "/app/dashboard"])
def test_app_pages_503_when_supabase_not_configured(monkeypatch, path):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        resp = client.get(path)
    get_settings.cache_clear()
    assert resp.status_code == 503
    assert "not available" in resp.text.lower()


def test_landing_nav_links_to_app(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        resp = client.get("/")
    get_settings.cache_clear()
    assert 'href="/app"' in resp.text


def test_api_still_requires_auth(client):
    # The HTML shells are public, but the API endpoints they call are not.
    assert client.get("/portfolio/status").status_code == 401
    assert client.get("/me").status_code == 401
