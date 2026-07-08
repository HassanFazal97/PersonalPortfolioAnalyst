"""Head metadata, static assets, and app footer.

Marketing pages carry favicon + OG/Twitter cards with absolute image URLs;
app pages carry favicon/theme-color only (they are noindex) plus the quiet
footer; /static serves the committed brand PNGs.
"""

import re

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


@pytest.mark.parametrize("path", ["/", "/pricing", "/contact", "/privacy", "/terms"])
def test_marketing_pages_have_og_tags(client, path):
    html = client.get(path).text
    assert '<meta property="og:title"' in html
    assert '<meta property="og:description"' in html
    assert '<meta property="og:type" content="website">' in html
    assert '<meta property="og:site_name" content="Cirvia">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    # og:url reflects the page path; og:image is an absolute https URL.
    # (Base origin comes from PUBLIC_BASE_URL, default https://cirvia.ca.)
    og_url = re.search(r'<meta property="og:url" content="(https://[^"]+)">', html)
    assert og_url is not None and og_url.group(1).endswith(path)
    og_image = re.search(r'<meta property="og:image" content="(https://[^"]+)">', html)
    assert og_image is not None and og_image.group(1).endswith("/static/og.png")


@pytest.mark.parametrize(
    "path", ["/", "/pricing", "/app", "/app/onboarding", "/app/dashboard"]
)
def test_all_pages_have_favicon_and_theme_color(client, path):
    html = client.get(path).text
    assert '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,' in html
    assert '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">' in html
    assert '<meta name="theme-color" content="#08060c">' in html


@pytest.mark.parametrize("path", ["/app", "/app/onboarding", "/app/dashboard"])
def test_app_pages_have_no_og_tags(client, path):
    html = client.get(path).text
    assert 'property="og:' not in html


@pytest.mark.parametrize("path", ["/app/onboarding", "/app/dashboard"])
def test_app_pages_have_footer(client, path):
    html = client.get(path).text
    assert 'class="app-foot"' in html
    assert 'href="/privacy"' in html
    assert 'href="/terms"' in html
    assert 'href="/contact"' in html
    assert "Not financial advice." in html


@pytest.mark.parametrize(
    ("path", "content_type"),
    [("/static/og.png", "image/png"), ("/static/apple-touch-icon.png", "image/png")],
)
def test_static_assets_served(client, path, content_type):
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == content_type
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
