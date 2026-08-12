"""Daily valuation-verdict refresh: the ``valuation_refresh`` job body.

Pure math over already-fresh data (``ticker_fundamentals``/``daily_prices``,
kept current by the ``picks_sync`` job — see ``app/tools/universe.py``), so
this costs $0 and makes no Yahoo calls: read stored fundamentals + prices for
the universe, run the cross-sectional screen, classify each ticker's verdict,
write the result to ``ticker_valuations`` (migration 028). Both
``GET /stocks/valuations`` and the ``verdict`` block on ``GET /stocks/{ticker}``
then do a flat DB read — no per-request numpy.

Kept separate from ``app/tools/universe.py`` (rather than folded into
``run_universe_sync``) because this step is pure computation over data that
job already wrote, not I/O against Yahoo — a distinct concern with its own
cron cadence.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.quant import screener, valuation
from app.tools.universe import get_universe

logger = logging.getLogger(__name__)


async def run_valuation_refresh(repo: Any, settings: Any) -> dict[str, Any]:
    """Score the universe and upsert one verdict row per ticker.

    Mirrors the picks pipeline's Stage A load (``app/agent/picks/pipeline.py``):
    same universe, same stored fundamentals/prices, same ``score_universe``
    call — but classifies every eligible ticker's *value* factor into a
    verdict rather than ranking a Top-N composite, so it doesn't inherit the
    composite's stricter "rankable" gate (see ``ScreenerResult.value_evidence``).
    """
    today = date.today()
    tickers = get_universe(settings.picks_universe_limit)

    fund_rows = await repo.get_ticker_fundamentals(tickers)
    now = datetime.now(timezone.utc)
    fundamentals: dict[str, dict[str, Any]] = {}
    ages: dict[str, float] = {}
    for t, row in fund_rows.items():
        if row.fetch_error:
            continue
        fundamentals[t] = row.data
        ages[t] = (now - row.fetched_at).total_seconds() / 3600.0

    since = today - timedelta(days=settings.picks_history_days)
    price_rows = await repo.get_daily_prices_bulk(tickers, since=since)
    closes = {
        t: [
            {"date": r.price_date.isoformat(), "adj_close": float(r.adj_close)}
            for r in rows
        ]
        for t, rows in price_rows.items()
    }
    last_price = {
        t: rows[-1]["adj_close"] for t, rows in closes.items() if rows
    }

    screen = screener.score_universe(
        fundamentals, closes, as_of=today, fundamentals_age_hours=ages
    )
    rows = valuation.compute_valuations(screen, fundamentals, last_price, tickers=tickers)

    upserted = await repo.upsert_ticker_valuations(
        [
            {
                "ticker": r["ticker"],
                "as_of": today,
                "verdict": r["verdict"],
                "sector_z": r["sector_z"],
                "metrics_used": r["metrics_used"],
                "sector": r["sector"],
                "sector_comparison": r["sector_comparison"],
                "name": r["name"],
                "market_cap": r["market_cap"],
                "last_price": r["last_price"],
                "evidence": r["evidence"],
                "not_scored_reason": r["not_scored_reason"],
            }
            for r in rows
        ]
    )
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    result = {
        "tickers": len(tickers),
        "scored": upserted,
        "verdicts": counts,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("valuation refresh: %s", result)
    return result
