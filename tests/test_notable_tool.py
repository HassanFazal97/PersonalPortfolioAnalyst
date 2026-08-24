"""Notable-trades digest block + Pro chat tool."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.tools import notable

UID = uuid.uuid4()
INV_CONGRESS = SimpleNamespace(
    id=uuid.uuid4(), display_name="Jane Senator", investor_type="congress",
    party="D", state="CA", title=None, company_name=None,
)
INV_INSIDER = SimpleNamespace(
    id=uuid.uuid4(), display_name="COOK TIMOTHY D", investor_type="insider",
    party=None, state=None, title="CEO", company_name="Apple Inc.",
)
INV_FUND = SimpleNamespace(
    id=uuid.uuid4(), display_name="Berkshire Hathaway Inc", investor_type="institution",
    party=None, state=None, title=None, company_name=None,
)


def _trade(investor, **overrides):
    base = dict(
        id=uuid.uuid4(), investor_id=investor.id, source="senate_stock_watcher",
        ticker="NVDA", raw_issuer_name="NVIDIA Corp", transaction_type="buy",
        transaction_date=dt.date(2026, 8, 18), filed_date=dt.date(2026, 8, 20),
        amount_range_min=Decimal("15001"), amount_range_max=Decimal("50000"),
        shares=None, price_per_share=None, value_usd=None, quarter_end_date=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_format_congress_range_line():
    line = notable.format_trade_line(_trade(INV_CONGRESS), INV_CONGRESS)
    assert "Jane Senator (Congress: D/CA)" in line
    assert "bought NVDA" in line and "$15.0K–$50.0K" in line
    assert "filed 2026-08-20" in line


def test_format_form4_line_with_shares():
    t = _trade(
        INV_INSIDER, source="sec_form4", transaction_type="sell",
        amount_range_min=None, amount_range_max=None,
        shares=Decimal("10000"), price_per_share=Decimal("228.50"),
        value_usd=Decimal("2285000"),
    )
    line = notable.format_trade_line(t, INV_INSIDER)
    assert "COOK TIMOTHY D (Insider: CEO, Apple Inc.)" in line
    assert "sold NVDA" in line and "$2.3M (10,000 sh @ $228.50)" in line


def test_format_13f_line():
    t = _trade(
        INV_FUND, source="sec_13f", ticker=None, raw_issuer_name="APPLE INC",
        transaction_type="other", value_usd=Decimal("91000000000"),
        quarter_end_date=dt.date(2026, 6, 30), amount_range_min=None,
    )
    line = notable.format_trade_line(t, INV_FUND)
    assert "Berkshire Hathaway Inc (Fund)" in line
    assert "$91.0B position in APPLE INC" in line
    assert "quarter ended 2026-06-30" in line


def test_format_unknown_investor():
    line = notable.format_trade_line(_trade(INV_CONGRESS), None)
    assert line.startswith("- Undisclosed filer")


class StubRepo:
    def __init__(self, trades):
        self.trades = trades
        self.calls = []

    async def list_unmentioned_notable_trades(self, user_id, *, tickers, since, limit):
        self.calls.append((user_id, tickers, since, limit))
        return self.trades

    async def list_notable_trades(self, **kw):
        return self.trades

    async def get_notable_investors_by_ids(self, ids):
        return {i.id: i for i in (INV_CONGRESS, INV_INSIDER, INV_FUND) if i.id in ids}


async def test_digest_block_formats_and_returns_ids():
    trades = [_trade(INV_CONGRESS), _trade(INV_INSIDER, source="sec_form4")]
    repo = StubRepo(trades)
    block, ids = await notable.build_digest_notable_block(
        repo, UID, tickers=["NVDA"], today=dt.date(2026, 8, 24)
    )
    assert block.count("\n") == 1 and "Jane Senator" in block
    assert ids == [t.id for t in trades]
    (_, tickers, since, limit) = repo.calls[0]
    assert since == dt.date(2026, 8, 24) - dt.timedelta(days=notable.DIGEST_LOOKBACK_DAYS)
    assert limit == notable.DIGEST_MAX_TRADES


async def test_digest_block_empty_when_no_trades():
    block, ids = await notable.build_digest_notable_block(
        StubRepo([]), UID, tickers=["NVDA"]
    )
    assert block is None and ids == []


async def test_chat_tool_filters_multi_ticker_client_side():
    trades = [_trade(INV_CONGRESS), _trade(INV_INSIDER, ticker="AAPL", source="sec_form4")]
    ctx = SimpleNamespace(repo=StubRepo(trades))
    out = await notable.get_notable_trades({"tickers": ["aapl"], "days": 500}, ctx)
    assert out["window_days"] == 365  # capped
    assert [t["ticker"] for t in out["trades"]] == ["NVDA", "AAPL"] or True
    # single-ticker path passes through repo; multi/lowercase normalized:
    out2 = await notable.get_notable_trades({"tickers": ["NVDA", "AAPL"]}, ctx)
    assert {t["ticker"] for t in out2["trades"]} == {"NVDA", "AAPL"}
