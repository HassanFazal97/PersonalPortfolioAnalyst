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


@pytest.mark.parametrize(
    "path",
    ["/app", "/app/onboarding", "/app/dashboard", "/app/settings",
     "/app/settings/delivery", "/app/reset"],
)
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
    # Per-holding news moved to the stock detail pages.
    assert 'id="holding-news"' not in resp.text
    assert 'id="watchlist-card"' in resp.text


def test_dashboard_has_metric_columns_and_stock_links(client):
    resp = client.get("/app/dashboard")
    text = resp.text
    for header in ("<th>Weight</th>", "<th>Fwd P/E</th>", "<th>Yield</th>",
                   "<th>Off high</th>", "<th>Earnings</th>"):
        assert header in text
    assert "/portfolio/metrics" in text
    assert "ticker-link" in text
    assert "/app/stock/" in text
    assert "skl-inline" in text


def test_stock_page_renders_with_ticker_config(client):
    resp = client.get("/app/stock/NVDA")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    # Ticker travels through the JSON config blob, not markup interpolation.
    assert '"ticker": "NVDA"' in resp.text
    assert 'id="chart"' in resp.text
    assert 'id="position"' in resp.text
    assert 'id="stock-news"' in resp.text
    assert 'href="/app/dashboard"' in resp.text


def test_stock_page_normalizes_and_validates_ticker(client):
    # Lowercase input normalizes to Yahoo format.
    resp = client.get("/app/stock/shop.to")
    assert resp.status_code == 200
    assert '"ticker": "SHOP.TO"' in resp.text
    # Anything outside the symbol alphabet is rejected before rendering.
    assert client.get("/app/stock/%3Cscript%3E").status_code == 404
    assert client.get("/app/stock/AAAAAAAAAAAAAAAAAAAA").status_code == 404


def test_onboarding_has_watchlist_panel(client):
    resp = client.get("/app/onboarding")
    assert resp.status_code == 200
    assert 'id="panel-watchlist"' in resp.text


def test_settings_has_account_sections(client):
    resp = client.get("/app/settings")
    assert resp.status_code == 200
    assert 'id="pw-form"' in resp.text
    assert 'id="disconnect-btn"' in resp.text
    assert 'id="plan-limits"' in resp.text
    assert 'id="delete-confirm"' in resp.text


def test_dashboard_nav_links_to_settings(client):
    resp = client.get("/app/dashboard")
    assert 'href="/app/settings"' in resp.text


def test_login_has_forgot_password_link(client):
    resp = client.get("/app")
    assert 'id="forgot-btn"' in resp.text
    assert "resetPasswordForEmail" in resp.text
    assert "/app/reset" in resp.text


def test_reset_page_has_password_form(client):
    resp = client.get("/app/reset")
    assert resp.status_code == 200
    assert 'id="reset-form"' in resp.text
    assert 'id="new-password"' in resp.text
    assert 'id="confirm-password"' in resp.text
    assert "PASSWORD_RECOVERY" in resp.text
    assert "updateUser" in resp.text


def test_dashboard_has_delivery_setup_banner(client):
    resp = client.get("/app/dashboard")
    assert 'id="delivery-banner"' in resp.text
    assert 'href="/app/settings/delivery"' in resp.text
    assert 'id="delivery-banner-dismiss"' in resp.text
    # Hidden until /me/notifications says no working channel exists.
    assert 'id="delivery-banner" style="display:none;"' in resp.text
    # Delivery management itself has moved off the dashboard.
    assert 'id="delivery-summary"' not in resp.text
    assert 'id="schedule-editor"' not in resp.text


def test_delivery_settings_page_has_picker_and_schedule(client):
    resp = client.get("/app/settings/delivery")
    assert resp.status_code == 200
    assert 'id="delivery-summary"' in resp.text
    assert 'id="channel-options"' in resp.text
    assert 'id="schedule-editor"' in resp.text
    assert 'id="dash-send-time"' in resp.text
    assert 'href="/app/settings"' in resp.text


def test_settings_links_to_delivery_page(client):
    resp = client.get("/app/settings")
    assert 'href="/app/settings/delivery"' in resp.text
    assert 'id="delivery-overview"' in resp.text


def test_dashboard_has_connection_banner(client):
    resp = client.get("/app/dashboard")
    assert 'id="connection-banner"' in resp.text
    assert 'id="reconnect-btn"' in resp.text
    assert 'id="connection-banner-dismiss"' in resp.text
    # Hidden until /portfolio/status says the connection is broken.
    assert 'id="connection-banner" style="display:none;"' in resp.text


def test_app_pages_noindex(client):
    resp = client.get("/app")
    assert '<meta name="robots" content="noindex">' in resp.text


@pytest.mark.parametrize(
    "path",
    ["/app", "/app/onboarding", "/app/dashboard", "/app/settings",
     "/app/settings/delivery", "/app/reset"],
)
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
