from types import SimpleNamespace

import pytest

import app.tools.market as market
from app.agent.digest_pipeline import resolve_digest_positions, run_digest_pipeline
from app.agent.planner import parse_plan
from app.config import get_settings
from app.tools.digest import DIGEST_MAX_CHARS, send_digest
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn, tool_use_turn

# --- planner JSON parsing ---------------------------------------------------


def test_parse_plan_plain_json():
    out = parse_plan('{"investigations": [{"question": "q1", "why": "w1"}]}')
    assert out == [{"question": "q1", "why": "w1"}]


def test_parse_plan_strips_code_fences():
    fenced = '```json\n{"investigations": [{"question": "q", "why": "w"}]}\n```'
    assert parse_plan(fenced) == [{"question": "q", "why": "w"}]


def test_parse_plan_caps_at_four():
    items = ", ".join('{"question": "q", "why": "w"}' for _ in range(6))
    out = parse_plan(f'{{"investigations": [{items}]}}')
    assert len(out) == 4


def test_parse_plan_invalid_returns_none():
    assert parse_plan("not json") is None
    assert parse_plan('{"investigations": []}') is None


def test_resolve_digest_positions_uses_watchlist():
    positions = [
        {"ticker": "A", "market_value": 100},
        {"ticker": "B", "market_value": 500},
        {"ticker": "C", "market_value": 300},
        {"ticker": "D", "market_value": 50},
    ]
    settings = get_settings()
    out = resolve_digest_positions(
        positions,
        plan="free",
        settings=settings,
        digest_tickers=["D", "A"],
    )
    assert [p["ticker"] for p in out] == ["D", "A"]


def test_resolve_digest_positions_falls_back_to_market_value():
    positions = [
        {"ticker": "A", "market_value": 100},
        {"ticker": "B", "market_value": 500},
        {"ticker": "C", "market_value": 300},
        {"ticker": "D", "market_value": 50},
    ]
    settings = get_settings()
    out = resolve_digest_positions(
        positions,
        plan="free",
        settings=settings,
        digest_tickers=[],
    )
    assert [p["ticker"] for p in out] == ["B", "C", "A"]


async def test_digest_pipeline_persists_prefetched_news(monkeypatch):
    import app.tools.news as news

    market.cache_clear()
    news.cache_clear()
    monkeypatch.setattr(
        market,
        "_fetch_quote_raw",
        lambda t: {"last_price": 100.0, "previous_close": 101.0, "volume": 10},
    )
    monkeypatch.setattr(
        market,
        "_fetch_history_raw",
        lambda t, d: [
            {"date": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100.0, "volume": 1},
            {"date": "2024-01-05", "open": 100, "high": 103, "low": 100, "close": 102.0, "volume": 1},
        ],
    )

    async def fake_prefetch(tickers, **kwargs):
        news._news_cache[(("NVDA",), 3)] = (
            news._clock(),
            ([{"headline": "NVDA headline", "source": "Reuters", "url": "https://x.com",
               "published_at": "2024-01-01T00:00:00+00:00", "summary": "Summary"}],
             "finnhub"),
        )

    monkeypatch.setattr(news, "prefetch_news_for_tickers", fake_prefetch)

    digest_body = "Portfolio steady today."
    client = ScriptedAnthropic(
        [
            text_turn('{"investigations": [{"question": "NVDA news?", "why": "holdings"}]}'),
            text_turn("NVDA quiet today."),
            tool_use_turn("d1", "send_digest", {"body": digest_body}),
        ]
    )
    repo = FakeRepo(positions=[_pos("NVDA", 10, 90.0, "USD")])

    await run_digest_pipeline(repo, client=client, force=True)

    assert len(repo._news_items) >= 1
    assert repo._news_items[0].ticker == "NVDA"


# --- send_digest length enforcement -----------------------------------------


async def test_send_digest_rejects_901_chars():
    ctx = SimpleNamespace(repo=FakeRepo(), run_id=None)
    with pytest.raises(ValueError):
        await send_digest({"body": "x" * (DIGEST_MAX_CHARS + 1)}, ctx)


async def test_send_digest_accepts_900_and_writes_row():
    repo = FakeRepo()
    ctx = SimpleNamespace(repo=repo, run_id=None)
    out = await send_digest({"body": "y" * DIGEST_MAX_CHARS}, ctx)
    assert out["status"] == "sent"
    tz = get_settings().tz
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(tz)).date()
    assert repo.digests[today].body == "y" * DIGEST_MAX_CHARS


# --- full pipeline with mocked model + market data --------------------------


def _pos(ticker, qty, avg_cost, currency):
    return SimpleNamespace(
        ticker=ticker, quantity=qty, avg_cost=avg_cost, currency=currency, account="taxable"
    )


async def test_digest_pipeline_creates_bounded_digest(monkeypatch):
    market.cache_clear()
    monkeypatch.setattr(
        market,
        "_fetch_quote_raw",
        lambda t: {"last_price": 100.0, "previous_close": 101.0, "volume": 10},
    )
    monkeypatch.setattr(
        market,
        "_fetch_history_raw",
        lambda t, d: [
            {"date": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100.0, "volume": 1},
            {"date": "2024-01-05", "open": 100, "high": 103, "low": 100, "close": 102.0, "volume": 1},
        ],
    )

    digest_body = (
        "Portfolio down 1% today, led by NVDA slipping on cooling AI demand chatter. "
        "SHOP flat. Nothing extends yesterday. Watch today: NVDA earnings after close."
    )
    client = ScriptedAnthropic(
        [
            text_turn('{"investigations": [{"question": "Why is NVDA down?", "why": "biggest mover"}]}'),
            text_turn("NVDA slipped ~1% on AI demand chatter; no company-specific news."),
            tool_use_turn("d1", "send_digest", {"body": digest_body}),
        ]
    )
    repo = FakeRepo(positions=[_pos("NVDA", 10, 90.0, "USD")])

    result = await run_digest_pipeline(repo, client=client, force=True)

    assert result["status"] == "completed"
    assert len(result["body"]) <= DIGEST_MAX_CHARS
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(get_settings().tz)).date()
    assert today in repo.digests
    assert repo.digests[today].body == digest_body
