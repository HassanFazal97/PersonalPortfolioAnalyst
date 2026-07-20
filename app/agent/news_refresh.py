"""Daily holding-news refresh: fetch, importance-filter, persist.

Runs 7 days a week (unlike the weekday digest) so weekend news lands in the
feed on the day it happens instead of arriving as a Monday backlog. The
digest pipeline routes its own persistence through ``persist_important_news``
too, so both paths apply the same importance filter and per-ticker cap;
``UNIQUE (user_id, fingerprint)`` makes overlapping runs no-ops.

No ``agent_runs`` row is created and no per-user monthly cost cap is checked:
classification is headline-cached and shared across users, so attributing its
cost to one user's cap would be arbitrary. The in-process ``Budget`` bounds
spend instead (``NEWS_REFRESH_MAX_COST_USD``).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from app.agent.budget import Budget
from app.auth.context import set_current_user_id
from app.config import DEFAULT_USER_ID, Settings, get_settings
from app.db.repo import Repo
from app.plans import max_digest_holdings, user_plan_and_tz
from app.tools import news
from app.tools.classify import classify_news

_OWNER_USER_ID = uuid.UUID(DEFAULT_USER_ID)


def _get_client(client: Any) -> Any:
    if client is not None:
        return client
    try:
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    except Exception:  # noqa: BLE001 - no client just means no importance filter
        return None


def _published(item: dict[str, Any]) -> str:
    # ISO-8601 strings compare chronologically; missing dates sort last.
    return item.get("published_at") or ""


def select_important(
    items: list[dict[str, Any]], *, min_salience: float, cap: int
) -> list[dict[str, Any]]:
    """Pick up to ``cap`` items worth showing a user.

    Classified items are kept when their signal is non-neutral or their
    salience clears ``min_salience``, ranked salience-first. When nothing is
    classified (no client, batch failure) fail open to the most recent few —
    the cap alone still bounds volume.
    """
    if not items:
        return []
    tagged = [it for it in items if it.get("signal")]
    if not tagged:
        return sorted(items, key=_published, reverse=True)[:cap]
    kept = [
        it
        for it in tagged
        if it.get("signal") != "neutral"
        or float(it.get("salience") or 0.0) >= min_salience
    ]
    kept.sort(
        key=lambda it: (float(it.get("salience") or 0.0), _published(it)),
        reverse=True,
    )
    return kept[:cap]


async def persist_important_news(
    db: Repo,
    user_id: uuid.UUID,
    tickers: list[str],
    *,
    client: Any = None,
    run_id: uuid.UUID | None = None,
    budget: Budget | None = None,
) -> int:
    """Classify the cached articles per ticker and store the important ones.

    Reads ``news.get_cached_news_for_ticker`` with its default lookback, which
    must match the ``prefetch_news_for_tickers`` defaults or the cache misses.
    """
    settings = get_settings()
    items: list[dict[str, Any]] = []
    for ticker in tickers:
        articles = news.get_cached_news_for_ticker(ticker)
        if not articles:
            continue
        articles = news._dedupe(articles, max_results=8)
        if client is not None and (budget is None or not budget.cost_exceeded()):
            ctx = SimpleNamespace(
                client=client,
                budget=budget,
                repo=db if run_id is not None else None,
                run_id=run_id,
            )
            articles = await classify_news(articles, ctx)
        kept = select_important(
            articles,
            min_salience=settings.news_min_salience,
            cap=settings.news_max_per_ticker,
        )
        items.extend({**a, "ticker": ticker} for a in kept)
    if not items:
        return 0
    return await db.insert_news_items_if_new(user_id, items, run_id=run_id)


def _news_tickers_for_user(
    positions: list[Any],
    *,
    plan: str,
    settings: Settings,
    digest_tickers: list[str],
) -> list[str]:
    """Which tickers get feed news — mirrors the digest's holdings scope so
    Free users don't receive news for holdings their digest never covers."""
    cap = max_digest_holdings(plan, settings)
    book_value: dict[str, float] = {}
    for p in positions:
        try:
            bv = float(p.quantity) * float(p.avg_cost)
        except (TypeError, ValueError):
            bv = 0.0
        book_value[p.ticker] = book_value.get(p.ticker, 0.0) + bv
    if cap is None:
        return sorted(book_value)
    picked = [t for t in digest_tickers if t in book_value][:cap]
    if picked:
        return picked
    # No watchlist: largest holdings by book value (market value needs live
    # quotes, which this daily job deliberately avoids).
    return sorted(book_value, key=lambda t: book_value[t], reverse=True)[:cap]


async def refresh_news_for_user(
    db: Repo, user_id: uuid.UUID | None = None, *, client: Any = None
) -> dict[str, Any]:
    settings = get_settings()
    uid = user_id or _OWNER_USER_ID
    user = await db.get_user(uid)
    plan, _tz = user_plan_and_tz(user, user_id=uid, settings=settings)

    positions = await db.list_positions(user_id=uid)
    if not positions:
        return {"user_id": str(uid), "status": "skipped_no_positions", "plan": plan}

    digest_tickers = await db.get_digest_tickers(uid)
    tickers = _news_tickers_for_user(
        positions, plan=plan, settings=settings, digest_tickers=digest_tickers
    )

    set_current_user_id(uid)
    try:
        await news.prefetch_news_for_tickers(tickers)
        budget = Budget(
            max_iterations=1,
            max_cost_usd=settings.news_refresh_max_cost_usd,
            model=settings.classifier_model,
        )
        inserted = await persist_important_news(
            db, uid, tickers, client=_get_client(client), budget=budget
        )
    finally:
        set_current_user_id(None)

    return {
        "user_id": str(uid),
        "status": "completed",
        "plan": plan,
        "tickers": len(tickers),
        "inserted": inserted,
    }


async def run_news_refresh_for_all(
    db: Repo, *, client: Any = None
) -> list[dict[str, Any]]:
    """Scheduled entry point: one refresh per digest recipient, best-effort."""
    client = _get_client(client)
    results: list[dict[str, Any]] = []
    for uid in await db.list_digest_recipients():
        try:
            results.append(await refresh_news_for_user(db, uid, client=client))
        except Exception:  # noqa: BLE001 - one user must not block the rest
            results.append({"user_id": str(uid), "status": "error"})
    return results
