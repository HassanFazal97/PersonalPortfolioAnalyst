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


def test_nav_swaps_to_signed_in_state_when_supabase_configured(monkeypatch):
    from app import landing

    monkeypatch.setenv("SUPABASE_URL", "https://myref.supabase.co")
    get_settings.cache_clear()
    html = landing._layout("t", "d", "<p>body</p>")
    # Static markup renders signed-out; the swap hooks + script do the rest.
    assert 'data-auth="signin"' in html
    assert 'data-auth="cta"' in html
    assert "sb-myref-auth-token" in html
    assert "Open dashboard" in html
    # Signed-in CTAs skip the /app session-check hop.
    assert "/app/dashboard" in html


def test_nav_swap_script_omitted_without_supabase(monkeypatch):
    from app import landing

    monkeypatch.setenv("SUPABASE_URL", "")
    get_settings.cache_clear()
    html = landing._layout("t", "d", "<p>body</p>")
    assert "auth-token" not in html
