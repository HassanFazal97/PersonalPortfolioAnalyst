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


def test_screener_page_is_public_no_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        resp = client.get("/screener")
    assert resp.status_code == 200
    assert "cheap or expensive" in resp.text.lower()


def test_screener_html_empty_state():
    from app import landing

    html = landing.screener_html({"as_of": None, "universe": {}, "rows": []})
    assert "computed nightly" in html


def test_screener_html_renders_verdict_badges():
    from app import landing

    payload = {
        "as_of": "2026-08-08",
        "universe": {"name": "sp500+tsx60", "size": 563},
        "rows": [
            {
                "ticker": "CHEAP", "name": "Cheap Co", "sector": "Technology",
                "market_cap": 5.2e10, "last_price": 42.5, "verdict": "Undervalued",
            },
            {
                "ticker": "RICH", "name": "Rich Co", "sector": "Technology",
                "market_cap": 1.1e12, "last_price": 900.0, "verdict": "Expensive",
            },
            {
                "ticker": "JUNK", "name": None, "sector": None,
                "market_cap": None, "last_price": None, "verdict": "Not enough data",
            },
        ],
    }
    html = landing.screener_html(payload)
    assert 'vd-under">Undervalued' in html
    assert 'vd-over">Expensive' in html
    assert 'vd-none">Not enough data' in html
    assert "~563 US and Canadian large caps" in html
    assert "$52.00B" in html  # market cap formatting
    assert "JUNK" in html and "&ndash;" in html  # missing fields degrade gracefully
