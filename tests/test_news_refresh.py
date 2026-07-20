"""Daily holding-news refresh: importance filter + persistence + fan-out."""

from datetime import datetime, timezone
from types import SimpleNamespace

import app.agent.news_refresh as news_refresh
import app.tools.classify as classify
import app.tools.news as news
from app.agent.news_refresh import (
    _news_tickers_for_user,
    refresh_news_for_user,
    run_news_refresh_for_all,
    select_important,
)
from app.config import get_settings
from tests.fakes import FakeRepo


def _pos(ticker, qty, avg_cost, currency="USD"):
    return SimpleNamespace(
        ticker=ticker, quantity=qty, avg_cost=avg_cost, currency=currency,
        account="taxable",
    )


def _article(headline, published_at, **extra):
    return {
        "headline": headline,
        "source": "Reuters",
        "url": f"https://news.example/{headline.replace(' ', '-')}",
        "published_at": published_at,
        "summary": "s",
        **extra,
    }


def _seed_cache(ticker, articles):
    news._news_cache[((ticker,), 3)] = (news._clock(), (articles, "finnhub"))


def _seed_labels(labels):
    for headline, signal, salience in labels:
        classify._signal_cache[" ".join(headline.lower().split())] = {
            "signal": signal, "salience": salience, "rationale": "",
        }


# --- select_important ---------------------------------------------------------


def test_select_important_empty():
    assert select_important([], min_salience=0.5, cap=2) == []


def test_select_important_filters_neutral_low_salience():
    items = [
        _article("boring recap", "2026-07-18T10:00:00+00:00",
                 signal="neutral", salience=0.2),
        _article("earnings miss", "2026-07-18T11:00:00+00:00",
                 signal="warning", salience=0.3),
        _article("big neutral", "2026-07-18T12:00:00+00:00",
                 signal="neutral", salience=0.8),
    ]
    kept = select_important(items, min_salience=0.5, cap=5)
    # Non-neutral survives below the threshold; neutral needs salience >= 0.5.
    assert {i["headline"] for i in kept} == {"earnings miss", "big neutral"}


def test_select_important_caps_by_salience_rank():
    items = [
        _article(f"story {i}", f"2026-07-1{i}T00:00:00+00:00",
                 signal="warning", salience=i / 10)
        for i in range(1, 8)
    ]
    kept = select_important(items, min_salience=0.5, cap=2)
    assert [i["headline"] for i in kept] == ["story 7", "story 6"]


def test_select_important_untagged_falls_back_to_recency():
    items = [
        _article("old", "2026-07-15T00:00:00+00:00"),
        _article("newest", "2026-07-18T00:00:00+00:00"),
        _article("middle", "2026-07-17T00:00:00+00:00"),
    ]
    kept = select_important(items, min_salience=0.5, cap=2)
    assert [i["headline"] for i in kept] == ["newest", "middle"]


# --- ticker scope per plan ------------------------------------------------------


def test_news_tickers_pro_covers_all_holdings():
    positions = [_pos("NVDA", 10, 90), _pos("SHOP.TO", 5, 40), _pos("NVDA", 2, 95)]
    out = _news_tickers_for_user(
        positions, plan="pro", settings=get_settings(), digest_tickers=[]
    )
    assert out == ["NVDA", "SHOP.TO"]


def test_news_tickers_free_uses_watchlist_then_book_value():
    settings = get_settings()  # free cap defaults to 3
    positions = [
        _pos("A", 1, 100), _pos("B", 1, 500), _pos("C", 1, 300),
        _pos("D", 1, 50), _pos("E", 1, 10),
    ]
    watch = _news_tickers_for_user(
        positions, plan="free", settings=settings, digest_tickers=["D", "A"]
    )
    assert watch == ["D", "A"]
    fallback = _news_tickers_for_user(
        positions, plan="free", settings=settings, digest_tickers=[]
    )
    assert fallback == ["B", "C", "A"]


# --- refresh pipeline -----------------------------------------------------------


async def test_run_news_refresh_persists_important_only(monkeypatch):
    news.cache_clear()
    classify.cache_clear()
    repo = FakeRepo(positions=[_pos("NVDA", 10, 90.0)])

    async def fake_prefetch(tickers, **kwargs):
        _seed_cache("NVDA", [
            _article("NVDA earnings warning", "2026-07-18T10:00:00+00:00"),
            _article("NVDA product launch", "2026-07-19T10:00:00+00:00"),
            _article("NVDA daily recap", "2026-07-19T11:00:00+00:00"),
            _article("NVDA analyst chatter", "2026-07-19T12:00:00+00:00"),
        ])

    monkeypatch.setattr(news, "prefetch_news_for_tickers", fake_prefetch)
    _seed_labels([
        ("NVDA earnings warning", "warning", 0.9),
        ("NVDA product launch", "opportunity", 0.6),
        ("NVDA daily recap", "neutral", 0.1),
        ("NVDA analyst chatter", "neutral", 0.2),
    ])

    # Non-None client makes classify_news read the pre-seeded cache; no API call.
    results = await run_news_refresh_for_all(repo, client=SimpleNamespace())

    assert len(results) == 1
    assert results[0]["status"] == "completed"
    assert results[0]["inserted"] == 2
    headlines = {n.headline for n in repo._news_items}
    assert headlines == {"NVDA earnings warning", "NVDA product launch"}
    # published_at survives as a datetime, not a raw ISO string.
    assert all(isinstance(n.published_at, datetime) for n in repo._news_items)

    # Idempotent: a second run inserts nothing (fingerprint dedup).
    again = await run_news_refresh_for_all(repo, client=SimpleNamespace())
    assert again[0]["inserted"] == 0
    assert len(repo._news_items) == 2


async def test_refresh_caps_per_ticker_without_classifier(monkeypatch):
    news.cache_clear()
    classify.cache_clear()
    repo = FakeRepo(positions=[_pos("NVDA", 10, 90.0)])

    headlines = [
        "NVDA ships new accelerator line",
        "Regulators probe GPU export rules",
        "Datacenter demand cools in Europe",
        "Analysts split on AI capex cycle",
        "Foundry partner expands capacity",
        "Gaming revenue beats expectations",
    ]

    async def fake_prefetch(tickers, **kwargs):
        _seed_cache("NVDA", [
            _article(h, f"2026-07-1{i}T00:00:00+00:00")
            for i, h in enumerate(headlines, start=1)
        ])

    monkeypatch.setattr(news, "prefetch_news_for_tickers", fake_prefetch)
    # Force the no-client path (refresh auto-creates one from the env key
    # otherwise): fail-open recency selection, still capped per ticker.
    monkeypatch.setattr(news_refresh, "_get_client", lambda client: None)

    result = await refresh_news_for_user(repo, client=None)
    assert result["inserted"] == get_settings().news_max_per_ticker
    newest = max(n.published_at for n in repo._news_items)
    assert newest == datetime(2026, 7, 16, tzinfo=timezone.utc)


async def test_refresh_reads_through_real_cache_path(monkeypatch):
    """Guards the cache-key coupling: prefetch defaults must match
    get_cached_news_for_ticker's, or the refresh silently persists nothing."""
    news.cache_clear()
    classify.cache_clear()
    repo = FakeRepo(positions=[_pos("NVDA", 10, 90.0)])

    monkeypatch.setattr(
        news,
        "_fetch_finnhub_news",
        lambda query, lookback_days, max_results: [
            {"headline": "NVDA wins big contract", "source": "Reuters",
             "url": "https://x.com/1", "datetime": 1789000000, "summary": "s"},
        ],
    )
    monkeypatch.setattr(news_refresh, "_get_client", lambda client: None)

    result = await refresh_news_for_user(repo, client=None)
    assert result["inserted"] == 1
    assert repo._news_items[0].ticker == "NVDA"


async def test_refresh_skips_users_without_positions():
    repo = FakeRepo()
    result = await refresh_news_for_user(repo, client=None)
    assert result["status"] == "skipped_no_positions"
