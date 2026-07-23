"""daily_prices store: fill-on-miss, serve-when-fresh, refetch-when-stale, sync."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.config import get_settings
from app.tools import market, price_store
from tests.fakes import FakeRepo


def _live_rows(n=200, start=100.0):
    base = date.today() - timedelta(days=n)
    return [
        {"date": (base + timedelta(days=i)).isoformat(), "adj_close": start + i * 0.1}
        for i in range(n)
    ]


def _patch_live(monkeypatch, counter):
    def fake(ticker, days):
        counter["n"] += 1
        return _live_rows()

    market.cache_clear()
    monkeypatch.setattr(market, "_fetch_adjusted_closes_raw", fake)


async def test_fill_on_miss_fetches_live_and_persists(monkeypatch):
    counter = {"n": 0}
    _patch_live(monkeypatch, counter)
    repo = FakeRepo()

    rows = await price_store.get_adjusted_closes(repo, "NVDA", 730)

    assert counter["n"] == 1  # went live on the miss
    assert rows and "adj_close" in rows[0]
    # It persisted, so a second read serves from the store (no new live fetch).
    stored = await repo.get_daily_prices("NVDA", since=date.today() - timedelta(days=730))
    assert len(stored) == len(rows)
    rows2 = await price_store.get_adjusted_closes(repo, "NVDA", 730)
    assert counter["n"] == 1  # served from store this time
    assert len(rows2) == len(rows)


async def test_serves_from_store_when_fresh(monkeypatch):
    counter = {"n": 0}
    _patch_live(monkeypatch, counter)
    repo = FakeRepo()
    # Pre-populate a fresh series (latest = today).
    base = date.today() - timedelta(days=150)
    repo.daily_prices["RY.TO"] = [
        SimpleNamespace(
            ticker="RY.TO", price_date=base + timedelta(days=i),
            adj_close=50.0 + i, close=None, currency=None,
        )
        for i in range(151)
    ]
    rows = await price_store.get_adjusted_closes(repo, "RY.TO", 730)
    assert counter["n"] == 0  # never hit the network
    assert len(rows) == 151


async def test_refetches_when_stale(monkeypatch):
    counter = {"n": 0}
    _patch_live(monkeypatch, counter)
    repo = FakeRepo()
    # Latest stored bar is 10 days old -> stale -> refetch.
    base = date.today() - timedelta(days=160)
    repo.daily_prices["MSFT"] = [
        SimpleNamespace(
            ticker="MSFT", price_date=base + timedelta(days=i),
            adj_close=300.0 + i, close=None, currency=None,
        )
        for i in range(150)  # ends ~today-10d
    ]
    await price_store.get_adjusted_closes(repo, "MSFT", 730)
    assert counter["n"] == 1  # stale -> went live


async def test_repo_none_is_passthrough(monkeypatch):
    counter = {"n": 0}
    _patch_live(monkeypatch, counter)
    rows = await price_store.get_adjusted_closes(None, "AAPL", 730)
    assert counter["n"] == 1 and rows


async def test_sync_covers_holdings_plus_benchmark_and_fx(monkeypatch):
    counter = {"n": 0}
    _patch_live(monkeypatch, counter)
    repo = FakeRepo(
        positions=[
            SimpleNamespace(ticker="NVDA", quantity=1, avg_cost=1, currency="USD", account="taxable"),
            SimpleNamespace(ticker="RY.TO", quantity=1, avg_cost=1, currency="CAD", account="TFSA"),
        ]
    )
    out = await price_store.run_daily_prices_sync(repo, get_settings())
    # Two holdings + ^GSPC + USDCAD=X.
    assert out["tickers"] == 4
    assert out["synced"] == 4
    for t in ("NVDA", "RY.TO", "^GSPC", "USDCAD=X"):
        assert t in repo.daily_prices
