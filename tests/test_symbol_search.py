"""Symbol search: normalization/filtering, caching, fail-open, endpoint."""

from fastapi.testclient import TestClient

import app.tools.symbol_search as symbol_search
from app.config import get_settings
from app.main import create_app
from tests.fakes import FakeRepo

_AUTH = {"Authorization": "Bearer test-token"}

RAW_RESULTS = [
    {"symbol": "SHOP.TO", "shortname": "Shopify Inc.", "exchDisp": "Toronto",
     "quoteType": "EQUITY"},
    {"symbol": "SHOP", "shortname": "Shopify Inc.", "exchDisp": "NYSE",
     "quoteType": "EQUITY"},
    # Dropped: instrument type the stock page can't render.
    {"symbol": "SHOP260117C00100000", "shortname": "SHOP Call",
     "quoteType": "OPTION"},
    # Dropped: symbol outside the ticker path alphabet.
    {"symbol": "BAD SYMBOL!", "shortname": "Junk", "quoteType": "EQUITY"},
    # Dropped: no symbol at all.
    {"shortname": "Mystery Co", "quoteType": "EQUITY"},
    # Deduped against the first SHOP.TO.
    {"symbol": "SHOP.TO", "longname": "Shopify duplicate", "quoteType": "EQUITY"},
]


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


async def test_search_normalizes_and_filters(monkeypatch):
    symbol_search.cache_clear()
    monkeypatch.setattr(symbol_search, "_search_raw", lambda q, n: RAW_RESULTS)

    results = await symbol_search.search_symbols("shopify")
    assert [r["symbol"] for r in results] == ["SHOP.TO", "SHOP"]
    assert results[0] == {
        "symbol": "SHOP.TO",
        "name": "Shopify Inc.",
        "exchange": "Toronto",
        "type": "EQUITY",
    }


async def test_search_short_query_skips_network(monkeypatch):
    symbol_search.cache_clear()
    calls = []
    monkeypatch.setattr(
        symbol_search, "_search_raw", lambda q, n: calls.append(q) or []
    )
    assert await symbol_search.search_symbols("") == []
    assert await symbol_search.search_symbols("a") == []
    assert await symbol_search.search_symbols("  a  ") == []
    assert calls == []


async def test_search_caches_repeat_queries(monkeypatch):
    symbol_search.cache_clear()
    calls = []
    monkeypatch.setattr(
        symbol_search, "_search_raw",
        lambda q, n: calls.append(q) or RAW_RESULTS,
    )
    first = await symbol_search.search_symbols("Shopify")
    second = await symbol_search.search_symbols("  shopify ")  # same key
    assert first == second
    assert len(calls) == 1


async def test_search_fails_open(monkeypatch):
    symbol_search.cache_clear()

    def boom(q, n):
        raise RuntimeError("yahoo down")

    monkeypatch.setattr(symbol_search, "_search_raw", boom)
    assert await symbol_search.search_symbols("shopify") == []


async def test_search_caps_results(monkeypatch):
    symbol_search.cache_clear()
    many = [
        {"symbol": f"T{i}", "shortname": f"Ticker {i}", "quoteType": "EQUITY"}
        for i in range(20)
    ]
    monkeypatch.setattr(symbol_search, "_search_raw", lambda q, n: many)
    results = await symbol_search.search_symbols("ticker", limit=50)
    assert len(results) == symbol_search.MAX_RESULTS


def test_search_endpoint_not_shadowed_by_ticker_route(monkeypatch):
    """Route-order regression: /stocks/search must hit the search handler,
    never resolve as ticker "SEARCH"."""
    symbol_search.cache_clear()
    monkeypatch.setattr(symbol_search, "_search_raw", lambda q, n: RAW_RESULTS)
    client = _client(monkeypatch, FakeRepo())

    resp = client.get("/stocks/search?q=shopify", headers=_AUTH)
    assert resp.status_code == 200
    assert [r["symbol"] for r in resp.json()["results"]] == ["SHOP.TO", "SHOP"]

    short = client.get("/stocks/search?q=a", headers=_AUTH)
    assert short.json() == {"results": []}


def test_search_endpoint_requires_auth(monkeypatch):
    client = _client(monkeypatch, FakeRepo())
    assert client.get("/stocks/search?q=shopify").status_code == 401
