import logging

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


# --------------------------------------------------------------------------
# SEO infrastructure: robots.txt, sitemap.xml, canonical tags, JSON-LD
# --------------------------------------------------------------------------

_PUBLIC_PAGES = [
    "/", "/pricing", "/track-record", "/screener", "/sample-digest",
    "/methodology", "/contact", "/privacy", "/terms",
]


def test_robots_txt(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    # Pin PUBLIC_BASE_URL explicitly: local dev's .env sets it to
    # http://localhost:8000, which would make this test's expectations
    # depend on the machine it runs on.
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://cirvia.ca")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    assert "Disallow: /app" in resp.text
    assert "Sitemap: https://cirvia.ca/sitemap.xml" in resp.text


def test_sitemap_xml_lists_all_public_pages(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://cirvia.ca")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert "xml" in resp.headers.get("content-type", "")
    for path in _PUBLIC_PAGES:
        assert f"<loc>https://cirvia.ca{path}</loc>" in resp.text


def test_canonical_tag_present_and_correct():
    # LANDING_HTML/PRICING_HTML/etc. are frozen once at module-import time
    # (same as their existing og:url tags), so this asserts structure
    # (tag present, href ends with the right path) rather than a hardcoded
    # domain — the actual base varies with whatever PUBLIC_BASE_URL was set
    # when app.landing first imported (e.g. local dev's .env).
    import re

    from app.landing import CONTACT_HTML, LANDING_HTML, METHODOLOGY_HTML, PRICING_HTML

    for html, path in (
        (LANDING_HTML, "/"),
        (PRICING_HTML, "/pricing"),
        (METHODOLOGY_HTML, "/methodology"),
        (CONTACT_HTML, "/contact"),
    ):
        match = re.search(r'<link rel="canonical" href="([^"]+)">', html)
        assert match, f"canonical tag missing for {path}"
        assert match.group(1).endswith(path)


def test_og_image_dimensions_present():
    from app.landing import LANDING_HTML

    assert 'og:image:width" content="1200"' in LANDING_HTML
    assert 'og:image:height" content="630"' in LANDING_HTML


def test_homepage_jsonld_organization_and_faq():
    from app.landing import LANDING_HTML

    assert 'application/ld+json' in LANDING_HTML
    assert '"Organization"' in LANDING_HTML
    assert '"FAQPage"' in LANDING_HTML
    # Proves the JSON-LD is wired to the real FAQ content, not a hardcoded
    # duplicate that could silently drift from the visible copy.
    assert "Can Cirvia trade for me?" in LANDING_HTML


def test_pricing_jsonld_has_product_offer_and_no_rating():
    from app.landing import PRICING_HTML

    assert '"Product"' in PRICING_HTML
    assert '"Offer"' in PRICING_HTML
    assert '"20.00"' in PRICING_HTML
    assert '"160.00"' in PRICING_HTML
    assert '"CAD"' in PRICING_HTML
    # No testimonials exist on this site to source a rating from; a
    # fabricated one would violate the site's own honesty posture.
    assert "aggregateRating" not in PRICING_HTML
    assert '"review"' not in PRICING_HTML
    assert '"Review"' not in PRICING_HTML


def test_homepage_pricing_teaser_present():
    from app.landing import LANDING_HTML, PRICING_HTML

    assert 'id="pricing-teaser"' in LANDING_HTML
    assert "/pricing" in LANDING_HTML
    for figure in ("$0", "$20", "$160/yr CAD"):
        assert figure in LANDING_HTML
        assert figure in PRICING_HTML  # guards against the two pages drifting


def test_funnel_log_captures_referer_and_utm(monkeypatch, caplog):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        with caplog.at_level(logging.INFO, logger="cirvia.funnel"):
            client.get(
                "/?utm_source=twitter&utm_medium=social",
                headers={"referer": "https://twitter.com/x"},
            )
    messages = [r.message for r in caplog.records if r.name == "cirvia.funnel"]
    assert any(
        "referer=https://twitter.com/x" in m
        and "utm_source=twitter" in m
        and "utm_medium=social" in m
        for m in messages
    )
