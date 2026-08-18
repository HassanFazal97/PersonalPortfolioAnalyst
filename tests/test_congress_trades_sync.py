"""sync_congress_trades: Senate/House Stock Watcher -> notable_investors /
notable_investor_trades, offline via FakeRepo + a monkeypatched fetch."""

from unittest.mock import AsyncMock

import pytest

from app.integrations.congress_trades.sync import sync_congress_trades
from tests.fakes import FakeRepo

_SENATE_ROW = {
    "senator": "Jane Smith",
    "state": "TX",
    "party": "R",
    "ticker": "NVDA",
    "asset_description": "NVIDIA Corp",
    "type": "Purchase",
    "amount": "$1,001 - $15,000",
    "transaction_date": "2026-08-01",
    "disclosure_date": "2026-08-10",
    "ptr_link": "https://example.com/senate.pdf",
}
_HOUSE_ROW = {
    "representative": "John Doe",
    "district": "TX39",
    "ticker": "AAPL",
    "asset_description": "Apple Inc",
    "type": "Sale (Full)",
    "amount": "$15,001 - $50,000",
    "transaction_date": "2026-08-02",
    "disclosure_date": "2026-08-11",
    "ptr_link": "https://example.com/house.pdf",
}


def _patch_fetch(monkeypatch, *, senate=None, house=None):
    async def fake_fetch(url, *, settings):
        if url == settings.senate_stock_watcher_url:
            return senate or []
        if url == settings.house_stock_watcher_url:
            return house or []
        return []

    monkeypatch.setattr(
        "app.integrations.congress_trades.sync.fetch_transactions", fake_fetch
    )


async def test_sync_congress_trades_upserts_both_chambers(monkeypatch):
    repo = FakeRepo()
    _patch_fetch(monkeypatch, senate=[_SENATE_ROW], house=[_HOUSE_ROW])
    settings = _fake_settings()

    summary = await sync_congress_trades(repo, settings=settings)

    assert summary["senate"]["new"] == 1
    assert summary["house"]["new"] == 1
    trades = await repo.list_notable_trades()
    assert {t.ticker for t in trades} == {"NVDA", "AAPL"}
    investors = await repo.get_notable_investors_by_ids(
        [t.investor_id for t in trades]
    )
    names = {inv.display_name for inv in investors.values()}
    assert names == {"Jane Smith", "John Doe"}


async def test_sync_congress_trades_is_idempotent(monkeypatch):
    """Re-running against the same dump must not duplicate rows — this is
    what makes 'daily, full re-fetch' an acceptable strategy for a source
    with no true incremental API."""
    repo = FakeRepo()
    _patch_fetch(monkeypatch, senate=[_SENATE_ROW], house=[_HOUSE_ROW])
    settings = _fake_settings()

    await sync_congress_trades(repo, settings=settings)
    summary2 = await sync_congress_trades(repo, settings=settings)

    assert summary2["senate"]["new"] == 0
    assert summary2["house"]["new"] == 0
    trades = await repo.list_notable_trades()
    assert len(trades) == 2  # not 4


async def test_sync_congress_trades_one_chamber_failing_does_not_block_the_other(
    monkeypatch,
):
    repo = FakeRepo()

    async def fake_fetch(url, *, settings):
        if url == settings.senate_stock_watcher_url:
            raise RuntimeError("senate bucket is gone")
        return [_HOUSE_ROW]

    async def sync_one_chamber_safe(*args, **kwargs):
        try:
            return await fake_fetch(*args, **kwargs)
        except RuntimeError:
            return []

    monkeypatch.setattr(
        "app.integrations.congress_trades.sync.fetch_transactions",
        sync_one_chamber_safe,
    )
    settings = _fake_settings()

    summary = await sync_congress_trades(repo, settings=settings)

    assert summary["senate"]["new"] == 0
    assert summary["house"]["new"] == 1
    trades = await repo.list_notable_trades()
    assert len(trades) == 1
    assert trades[0].ticker == "AAPL"


async def test_sync_congress_trades_raises_when_both_sources_return_nothing(
    monkeypatch,
):
    repo = FakeRepo()
    _patch_fetch(monkeypatch)  # both empty
    settings = _fake_settings()

    with pytest.raises(RuntimeError):
        await sync_congress_trades(repo, settings=settings)


async def test_sync_congress_trades_one_bad_row_does_not_abort_the_run(monkeypatch):
    repo = FakeRepo()
    bad_row = dict(_SENATE_ROW, disclosure_date=None)  # mapper returns None for this
    _patch_fetch(monkeypatch, senate=[bad_row, _SENATE_ROW])
    settings = _fake_settings()

    summary = await sync_congress_trades(repo, settings=settings)

    assert summary["senate"]["fetched"] == 2
    assert summary["senate"]["new"] == 1
    trades = await repo.list_notable_trades()
    assert len(trades) == 1


def _fake_settings():
    class _Settings:
        senate_stock_watcher_url = "https://example.com/senate.json"
        house_stock_watcher_url = "https://example.com/house.json"
        sec_edgar_user_agent = "Cirvia/1.0 (contact: ops@cirvia.ca)"

    return _Settings()
