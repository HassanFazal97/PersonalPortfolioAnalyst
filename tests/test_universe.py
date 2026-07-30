"""Universe constituents and the evening sync job."""

from __future__ import annotations

import uuid as uuid_mod
from datetime import date, timedelta

import pytest

from app.tools import universe
from app.tools.tickers import normalize_ticker
from app.tools.universe_constituents import SP500, TSX60
from tests.fakes import FakeRepo


def test_constituent_counts_and_shape():
    assert 490 <= len(SP500) <= 520
    assert 55 <= len(TSX60) <= 65
    assert all(t.endswith(".TO") for t in TSX60)
    # Yahoo format throughout: normalization is a no-op.
    for t in [*SP500, *TSX60]:
        assert normalize_ticker(t) == t
    combined = universe.get_universe()
    assert len(combined) == len(set(combined))


def test_get_universe_limit_truncates():
    assert len(universe.get_universe(25)) == 25
    snap = universe.universe_snapshot()
    assert snap["name"] == "sp500+tsx60"
    assert snap["size"] == len(universe.get_universe())
    assert snap["constituents_as_of"]


def test_needs_full_window_decisions():
    today = date(2026, 7, 27)
    # No coverage at all -> full.
    assert universe._needs_full_window(None, today=today, history_days=420)
    # Deep and fresh -> incremental.
    deep_fresh = {"first": today - timedelta(days=430), "last": today - timedelta(days=1)}
    assert not universe._needs_full_window(deep_fresh, today=today, history_days=420)
    # Shallow history -> full.
    shallow = {"first": today - timedelta(days=100), "last": today - timedelta(days=1)}
    assert universe._needs_full_window(shallow, today=today, history_days=420)
    # Gap wider than the incremental window -> full.
    gapped = {"first": today - timedelta(days=430), "last": today - timedelta(days=40)}
    assert universe._needs_full_window(gapped, today=today, history_days=420)


class _Settings:
    picks_universe_limit = 3
    picks_history_days = 420
    picks_sync_spacing_seconds = 0.0
    fundamentals_ttl_hours = 24
    fundamentals_error_ttl_hours = 1


@pytest.fixture()
def small_universe(monkeypatch):
    tickers = ["AAA", "BBB", "CCC"]
    monkeypatch.setattr(universe, "get_universe", lambda limit=0: tickers)
    return tickers


async def test_run_universe_sync_prices_and_ttl_fundamentals(
    monkeypatch, small_universe
):
    repo = FakeRepo()
    today = date.today()
    rows = [
        {"date": (today - timedelta(days=i)).isoformat(), "adj_close": 100.0 + i}
        for i in range(5, 0, -1)
    ]

    batch_calls: list[tuple[list[str], int]] = []

    def fake_batch(tickers, days):
        batch_calls.append((list(tickers), days))
        return {t: rows for t in tickers}

    fetched: list[str] = []

    async def fake_fetch_and_store(ticker, repo_, settings_):
        fetched.append(ticker)
        await repo_.upsert_ticker_fundamentals(
            ticker=ticker, quote_type="EQUITY", data={"ticker": ticker}
        )
        return {"ticker": ticker}

    from app.tools import fundamentals, market

    monkeypatch.setattr(market, "_fetch_adjusted_closes_batch_raw", fake_batch)
    monkeypatch.setattr(fundamentals, "_fetch_and_store", fake_fetch_and_store)

    # BBB already has a fresh fundamentals row: the TTL check must skip it.
    await repo.upsert_ticker_fundamentals(
        ticker="BBB", quote_type="EQUITY", data={"ticker": "BBB"}
    )

    result = await universe.run_universe_sync(repo, _Settings())

    assert result["tickers"] == 3
    assert result["prices_synced"] == 3
    assert result["prices_failed"] == 0
    assert result["fundamentals_refreshed"] == 2
    assert result["fundamentals_fresh_skipped"] == 1
    assert sorted(fetched) == ["AAA", "CCC"]
    # First-ever sync has no stored coverage -> full window for every ticker.
    assert all(days == 420 for _, days in batch_calls)
    assert len(await repo.get_daily_prices("AAA")) == 5


async def test_sync_writes_pit_snapshots_and_membership(
    monkeypatch, small_universe
):
    repo = FakeRepo()

    def fake_batch(tickers, days):
        return {
            t: [{"date": date.today().isoformat(), "adj_close": 10.0}]
            for t in tickers
        }

    async def fake_fetch_and_store(ticker, repo_, settings_):
        await repo_.upsert_ticker_fundamentals(
            ticker=ticker, quote_type="EQUITY", data={"ticker": ticker, "pe": 12.0}
        )
        return {"ticker": ticker}

    from app.tools import fundamentals, market

    monkeypatch.setattr(market, "_fetch_adjusted_closes_batch_raw", fake_batch)
    monkeypatch.setattr(fundamentals, "_fetch_and_store", fake_fetch_and_store)
    # An errored row must never be snapshotted as if it were data.
    await repo.upsert_ticker_fundamentals(
        ticker="CCC", quote_type="EQUITY", data={}, fetch_error="boom"
    )

    result = await universe.run_universe_sync(repo, _Settings())
    assert result["snapshots_added"] == 2  # AAA, BBB — not the errored CCC
    got = await repo.get_fundamentals_snapshots(["AAA"], as_of=date.today())
    assert got["AAA"]["pe"] == 12.0
    # Same-evening re-run appends nothing new (first write of the day wins).
    rerun = await universe.run_universe_sync(repo, _Settings())
    assert rerun["snapshots_added"] == 0

    # Membership history seeded from the deployed constituent lists.
    assert result["membership"]["sp500"]["added"] > 400
    assert result["membership"]["tsx60"]["removed"] == 0
    assert rerun["membership"]["sp500"]["added"] == 0


async def test_membership_diff_closes_removed_intervals():
    repo = FakeRepo()
    day1 = date(2026, 7, 1)
    day2 = date(2026, 10, 1)
    await repo.sync_universe_membership("sp500", ["AAA", "BBB"], as_of=day1)
    out = await repo.sync_universe_membership("sp500", ["AAA", "CCC"], as_of=day2)
    assert out == {"added": 1, "removed": 1, "open": 2}
    rows = {(r.ticker, r.removed_at) for r in repo.universe_membership}
    # BBB's interval is CLOSED, not deleted — the survivorship-bias antidote.
    assert ("BBB", day2) in rows and ("AAA", None) in rows and ("CCC", None) in rows


async def test_departed_pick_tickers_keep_price_coverage(
    monkeypatch, small_universe
):
    repo = FakeRepo()
    # A pick on DEAD (no longer in the universe) within the last year.
    await repo.insert_pick_entries(
        [
            {
                "picks_run_id": uuid_mod.uuid4(),
                "run_date": date.today() - timedelta(days=30),
                "ticker": "DEAD",
                "rank": 1,
                "composite_score": 0.5,
                "confidence": 0.5,
                "entry_price": 10.0,
                "factors": {},
                "thesis_summary": "t",
            }
        ]
    )

    synced: list[str] = []

    def fake_batch(tickers, days):
        synced.extend(tickers)
        return {
            t: [{"date": date.today().isoformat(), "adj_close": 10.0}]
            for t in tickers
        }

    async def fake_fetch_and_store(ticker, repo_, settings_):
        await repo_.upsert_ticker_fundamentals(
            ticker=ticker, quote_type="EQUITY", data={"ticker": ticker}
        )
        return {}

    from app.tools import fundamentals, market

    monkeypatch.setattr(market, "_fetch_adjusted_closes_batch_raw", fake_batch)
    monkeypatch.setattr(fundamentals, "_fetch_and_store", fake_fetch_and_store)

    result = await universe.run_universe_sync(repo, _Settings())
    assert result["departed_tracked"] == 1
    assert "DEAD" in synced  # prices keep syncing for the open pick


async def test_sync_one_bad_ticker_never_aborts(monkeypatch, small_universe):
    repo = FakeRepo()

    def fake_batch(tickers, days):
        # BBB comes back empty (Yahoo couldn't serve it).
        return {
            t: [{"date": date.today().isoformat(), "adj_close": 10.0}]
            for t in tickers
            if t != "BBB"
        }

    async def fake_fetch_and_store(ticker, repo_, settings_):
        if ticker == "CCC":
            return None  # recorded error row path
        await repo_.upsert_ticker_fundamentals(
            ticker=ticker, quote_type="EQUITY", data={}
        )
        return {}

    from app.tools import fundamentals, market

    monkeypatch.setattr(market, "_fetch_adjusted_closes_batch_raw", fake_batch)
    monkeypatch.setattr(fundamentals, "_fetch_and_store", fake_fetch_and_store)

    result = await universe.run_universe_sync(repo, _Settings())
    assert result["prices_synced"] == 2
    assert result["prices_failed"] == 1
    assert result["fundamentals_failed"] == 1
