from types import SimpleNamespace

import pytest

import app.tools.market as market
from app.agent.digest_pipeline import (
    build_watchlist_section,
    resolve_digest_positions,
    run_digest_pipeline,
)
from app.agent.planner import parse_plan
from app.config import get_settings
from app.tools.digest import (
    DIGEST_MAX_CHARS,
    DIGEST_SMS_TEASER_MAX_CHARS,
    build_sms_teaser,
    send_digest,
    validate_digest_structure,
)
from tests.fakes import FakeRepo, ScriptedAnthropic, text_turn, tool_use_turn

STRUCTURED_BODY = (
    "PORTFOLIO: -1.0% today\n"
    "\n"
    "TOP RISK\n"
    "NVDA slipping on cooling AI demand chatter; largest position.\n"
    "\n"
    "WATCH TODAY: NVDA earnings after close."
)


def _padded_structured_body(total_chars: int) -> str:
    """A valid structured body padded in the TOP RISK section to an exact length."""
    head = "PORTFOLIO: -1.0% today\n\nTOP RISK\n"
    tail = "\n\nWATCH TODAY: NVDA earnings after close."
    return head + "z" * (total_chars - len(head) - len(tail)) + tail

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
    import app.tools.classify as classify
    import app.tools.news as news

    market.cache_clear()
    news.cache_clear()
    classify.cache_clear()
    # Pre-label the headline so the importance pass reads cache instead of
    # consuming one of the scripted client's turns.
    classify._signal_cache["nvda headline"] = {
        "signal": "warning", "salience": 0.9, "rationale": "",
    }
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

    digest_body = STRUCTURED_BODY
    client = ScriptedAnthropic(
        [
            text_turn('{"investigations": [{"question": "NVDA news?", "why": "holdings"}]}'),
            text_turn("NVDA quiet today."),
            tool_use_turn("d1", "send_digest", {"body": digest_body}),
        ]
    )
    repo = FakeRepo(positions=[_pos("NVDA", 10, 90.0, "USD")])

    await run_digest_pipeline(repo, client=client, force=True)

    assert 1 <= len(repo._news_items) <= get_settings().news_max_per_ticker
    assert repo._news_items[0].ticker == "NVDA"
    # Publish time is stored as a datetime — the feed sorts and labels by it.
    from datetime import datetime as _dt

    assert isinstance(repo._news_items[0].published_at, _dt)


# --- send_digest length + structure enforcement ------------------------------


async def test_send_digest_rejects_over_max_chars():
    ctx = SimpleNamespace(repo=FakeRepo(), run_id=None)
    with pytest.raises(ValueError):
        await send_digest({"body": _padded_structured_body(DIGEST_MAX_CHARS + 1)}, ctx)


async def test_send_digest_accepts_max_chars_and_writes_row():
    repo = FakeRepo()
    ctx = SimpleNamespace(repo=repo, run_id=None)
    body = _padded_structured_body(DIGEST_MAX_CHARS)
    assert len(body) == DIGEST_MAX_CHARS
    out = await send_digest({"body": body}, ctx)
    assert out["status"] == "sent"
    tz = get_settings().tz
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(tz)).date()
    assert repo.digests[today].body == body


async def test_send_digest_rejects_unstructured_body():
    ctx = SimpleNamespace(repo=FakeRepo(), run_id=None)
    with pytest.raises(ValueError):
        await send_digest({"body": "Portfolio steady today. Watch today: nothing."}, ctx)


# --- watchlist section --------------------------------------------------------


def test_build_watchlist_section_formats_lines():
    section = build_watchlist_section(
        ["SHOP.TO", "AAPL"],
        {
            "SHOP.TO": {"last_price": 98.123, "day_change_pct": 1.4},
            "AAPL": {"last_price": None, "day_change_pct": None},
        },
        news_tickers={"SHOP.TO"},
    )
    lines = section.splitlines()
    assert lines[0] == "SHOP.TO  $98.12  +1.4% today · news"
    assert lines[1] == "AAPL  n/a  n/a today"


def test_build_watchlist_section_empty_returns_none():
    assert build_watchlist_section([], {}, news_tickers=set()) is None


def test_build_watchlist_section_truncates_long_rosters():
    tickers = [f"TICKER{i}" for i in range(200)]
    quotes = {t: {"last_price": 100.0, "day_change_pct": 0.5} for t in tickers}
    section = build_watchlist_section(tickers, quotes, news_tickers=set())
    from app.agent.digest_pipeline import WATCHLIST_SECTION_MAX_CHARS

    assert len(section) <= WATCHLIST_SECTION_MAX_CHARS
    assert section.splitlines()[-1].startswith("(+")


async def test_send_digest_appends_watchlist_to_rich_body_only():
    repo = FakeRepo()
    import uuid as _uuid

    uid = _uuid.uuid4()
    # SMS user: the outbound body is the short core, never the rich body.
    repo.seed_user(uid, plan="pro")
    repo._users_by_id[uid].preferred_channel = "sms"
    ctx = SimpleNamespace(
        repo=repo, run_id=None, user_id=uid,
        watchlist_section="SHOP.TO  $98.12  +1.4% today · news",
    )
    out = await send_digest({"body": STRUCTURED_BODY}, ctx)
    assert out["status"] == "sent"

    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo(get_settings().tz)).date()
    stored = repo._digests_by_user[(uid, today)].body
    assert "\n\nWATCHLIST\nSHOP.TO  $98.12  +1.4% today · news" in stored
    # The queued SMS body is the derived teaser: portfolio line, top risk,
    # link — never the rich body or the watchlist section.
    queued = repo.outbound[-1]
    assert queued.startswith("PORTFOLIO: -1.0% today")
    assert "TOP RISK: NVDA slipping" in queued
    assert queued.endswith("/app/dashboard#tab-digest")
    assert "WATCHLIST" not in queued
    assert len(queued) <= DIGEST_SMS_TEASER_MAX_CHARS


async def test_send_digest_without_watchlist_section_unchanged():
    repo = FakeRepo()
    ctx = SimpleNamespace(repo=repo, run_id=None)
    await send_digest({"body": STRUCTURED_BODY}, ctx)
    assert "WATCHLIST" not in repo.outbound[-1]


# --- SMS teaser ---------------------------------------------------------------

_LINK = "https://cirvia.ca/app/dashboard#tab-digest"


def test_sms_teaser_extracts_portfolio_risk_and_link():
    teaser = build_sms_teaser(STRUCTURED_BODY, link=_LINK)
    assert teaser.splitlines() == [
        "PORTFOLIO: -1.0% today",
        "TOP RISK: NVDA slipping on cooling AI demand chatter; largest position.",
        f"Full digest: {_LINK}",
    ]


def test_sms_teaser_caps_length_and_keeps_link():
    body = (
        "PORTFOLIO: " + "x" * 400 + "\n\nTOP RISK\n" + "y" * 400
        + "\n\nWATCH TODAY: nothing."
    )
    teaser = build_sms_teaser(body, link=_LINK)
    assert len(teaser) <= DIGEST_SMS_TEASER_MAX_CHARS
    assert teaser.endswith(f"Full digest: {_LINK}")
    assert teaser.startswith("PORTFOLIO: xxx")
    assert "TOP RISK: yyy" in teaser


def test_sms_teaser_degrades_without_risk_content():
    body = "PORTFOLIO: +0.2% today\n\nTOP RISK\n\nWATCH TODAY: Fed minutes."
    teaser = build_sms_teaser(body, link=_LINK)
    assert teaser.splitlines() == [
        "PORTFOLIO: +0.2% today",
        f"Full digest: {_LINK}",
    ]


def test_sms_teaser_normalizes_non_gsm7_punctuation():
    body = (
        "PORTFOLIO: down 1% — “risk-off” day\n\nTOP RISK\n"
        "NVDA’s momentum fading…\n\nWATCH TODAY: CPI."
    )
    teaser = build_sms_teaser(body, link=_LINK)
    assert "—" not in teaser and "“" not in teaser and "’" not in teaser
    assert 'down 1% - "risk-off" day' in teaser
    assert "NVDA's momentum fading..." in teaser


def test_validate_structure_requires_portfolio_first_line():
    body = "TOP RISK\nSomething.\n\nWATCH TODAY: Fed minutes."
    assert "PORTFOLIO" in validate_digest_structure(body)


def test_validate_structure_requires_top_risk_label():
    body = "PORTFOLIO: +0.2% today\n\nAll quiet.\n\nWATCH TODAY: Fed minutes."
    assert "TOP RISK" in validate_digest_structure(body)


def test_validate_structure_requires_watch_today_last_line():
    body = "PORTFOLIO: +0.2% today\n\nTOP RISK\nConcentration in NVDA."
    assert "WATCH TODAY" in validate_digest_structure(body)


def test_validate_structure_accepts_body_without_notable():
    assert validate_digest_structure(STRUCTURED_BODY) is None


def test_validate_structure_accepts_notable_bullets():
    body = (
        "PORTFOLIO: -0.8% today (-$1,240)\n"
        "\n"
        "TOP RISK\n"
        "NVDA down 4.2% pre-market on export curb headlines; 18% of portfolio.\n"
        "\n"
        "NOTABLE\n"
        "- AAPL earnings Thu after close\n"
        "- CAD strength trimming US gains\n"
        "\n"
        "WATCH TODAY: Fed minutes 2pm ET"
    )
    assert validate_digest_structure(body) is None


# --- full pipeline with mocked model + market data --------------------------


def _pos(ticker, qty, avg_cost, currency):
    return SimpleNamespace(
        ticker=ticker, quantity=qty, avg_cost=avg_cost, currency=currency, account="taxable"
    )


async def test_digest_pipeline_creates_bounded_digest(monkeypatch):
    import app.tools.news as news

    market.cache_clear()
    news.cache_clear()

    async def no_prefetch(tickers, **kwargs):
        return None

    # Keep the pipeline off the network: an empty news cache makes the
    # persist step a no-op, so no classify call eats a scripted turn.
    monkeypatch.setattr(news, "prefetch_news_for_tickers", no_prefetch)
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

    digest_body = STRUCTURED_BODY
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
