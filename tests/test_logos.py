"""/portfolio/logo/{ticker}: domain resolution, proxy caching, fallbacks."""

import pytest
from fastapi.testclient import TestClient

import app.tools.fundamentals as fundamentals
import app.tools.logos as logos
from app.config import get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_AUTH = {"Authorization": "Bearer test-token"}

PNG = b"\x89PNG fake-icon-bytes"


def _client(monkeypatch, repo):
    monkeypatch.setenv("API_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    app = create_app()
    app.state.repo = repo
    app.state.scheduler = None
    app.state.macro_scheduler = None
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_caches():
    fundamentals.cache_clear()
    logos.cache_clear()
    yield
    fundamentals.cache_clear()
    logos.cache_clear()


@pytest.fixture()
def repo():
    return FakeRepo()


async def _seed(repo, ticker="NVDA", website="https://www.nvidia.com/en-us/"):
    await repo.upsert_ticker_fundamentals(
        ticker=ticker,
        quote_type="EQUITY",
        data={
            "ticker": ticker,
            "quote_type": "EQUITY",
            "profile": {"name": "Test Co", "website": website},
            "valuation": {},
            "dividends": {},
            "price_action": {},
            "earnings_dates": [],
            "etf": None,
        },
    )


def _seed_icon(monkeypatch, calls=None):
    async def fake_fetch(domain):
        if calls is not None:
            calls.append(domain)
        return PNG, "image/png"

    monkeypatch.setattr(logos, "_fetch_icon_raw", fake_fetch)


def test_domain_of():
    assert logos.domain_of("https://www.nvidia.com/en-us/") == "nvidia.com"
    assert logos.domain_of("https://ir.shopify.com") == "ir.shopify.com"
    assert logos.domain_of("http://te.com:443/about") == "te.com"
    assert logos.domain_of("oklo.com") == "oklo.com"
    assert logos.domain_of("") is None
    assert logos.domain_of(None) is None
    assert logos.domain_of("   ") is None


async def test_logo_served_with_cache_headers(monkeypatch, repo):
    await _seed(repo)
    calls = []
    _seed_icon(monkeypatch, calls)
    resp = _client(monkeypatch, repo).get("/portfolio/logo/NVDA", headers=_AUTH)
    assert resp.status_code == 200
    assert resp.content == PNG
    assert resp.headers["content-type"] == "image/png"
    assert "max-age" in resp.headers["cache-control"]
    assert calls == ["nvidia.com"]


async def test_logo_fetched_once_across_requests(monkeypatch, repo):
    await _seed(repo)
    calls = []
    _seed_icon(monkeypatch, calls)
    client = _client(monkeypatch, repo)
    assert client.get("/portfolio/logo/NVDA", headers=_AUTH).status_code == 200
    assert client.get("/portfolio/logo/NVDA", headers=_AUTH).status_code == 200
    assert calls == ["nvidia.com"]


async def test_no_website_404s_without_fetching(monkeypatch, repo):
    await _seed(repo, website=None)
    calls = []
    _seed_icon(monkeypatch, calls)
    resp = _client(monkeypatch, repo).get("/portfolio/logo/NVDA", headers=_AUTH)
    assert resp.status_code == 404
    assert calls == []


async def test_icon_miss_404s_and_is_negative_cached(monkeypatch, repo):
    await _seed(repo)
    calls = []

    async def fake_fetch(domain):
        calls.append(domain)
        return None  # the favicon service 404'd

    monkeypatch.setattr(logos, "_fetch_icon_raw", fake_fetch)
    client = _client(monkeypatch, repo)
    assert client.get("/portfolio/logo/NVDA", headers=_AUTH).status_code == 404
    assert client.get("/portfolio/logo/NVDA", headers=_AUTH).status_code == 404
    assert calls == ["nvidia.com"]


async def test_pre_website_row_spawns_refresh(monkeypatch, repo):
    """Rows stored before profiles carried ``website`` self-heal: the logo
    request reports a miss now and kicks the background fundamentals refresh."""
    await repo.upsert_ticker_fundamentals(
        ticker="NVDA",
        quote_type="EQUITY",
        data={
            "ticker": "NVDA",
            "quote_type": "EQUITY",
            "profile": {"name": "Test Co"},  # no website key at all
            "valuation": {},
            "dividends": {},
            "price_action": {},
            "earnings_dates": [],
            "etf": None,
        },
    )
    refreshed = []
    monkeypatch.setattr(
        fundamentals, "_spawn_refresh", lambda t, r, s: refreshed.append(t)
    )
    _seed_icon(monkeypatch)
    resp = _client(monkeypatch, repo).get("/portfolio/logo/NVDA", headers=_AUTH)
    assert resp.status_code == 404
    assert refreshed == ["NVDA"]


async def test_garbage_ticker_404(monkeypatch, repo):
    _seed_icon(monkeypatch)
    client = _client(monkeypatch, repo)
    assert client.get("/portfolio/logo/%3Cscript%3E", headers=_AUTH).status_code == 404


async def test_logo_requires_auth(monkeypatch, repo):
    assert _client(monkeypatch, repo).get("/portfolio/logo/NVDA").status_code == 401
