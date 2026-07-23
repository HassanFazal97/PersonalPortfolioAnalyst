"""Persistent adjusted-close store in front of the yfinance seam.

The quant engine's return history reads through here instead of hitting
yfinance on every risk call. Behaviour:

- **Read (fill-on-miss).** Serve the stored series when it's fresh (its latest
  bar is within ``STALE_DAYS`` of today); otherwise fetch the full window live
  (``market.get_adjusted_closes``), persist it, and serve that. The first-ever
  read of a ticker always fetches the full window, so the store is deep from
  the start and later reads are shallow-but-fresh only if the sync job lapses.
- **Sync.** ``run_daily_prices_sync`` refreshes every held ticker (+ benchmark
  + FX) nightly so reads stay on the fast, reproducible DB path.

Why persist at all: yfinance silently re-adjusts history, so re-fetching isn't
reproducible — the same portfolio would drift across reloads. A stored series
makes risk numbers deterministic and enables an honest point-in-time VaR
backtest, and decouples the request path from Yahoo uptime.

Fail-open: any DB hiccup falls back to a live fetch, so risk analytics never
break because the store is unavailable. When ``repo`` is None (unit contexts),
this is a thin pass-through to the live fetch.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.tools import market

logger = logging.getLogger(__name__)

# A stored series is fresh enough to serve if its latest bar is within this many
# calendar days of today (covers weekends + holidays without a refetch).
STALE_DAYS = 4
# yfinance throttling for the nightly sync: serial with a small stagger.
_SYNC_SPACING_SECONDS = 0.75
# Extra symbols the quant engine needs beyond the user's holdings.
_BENCHMARK_TICKER = "^GSPC"
_FX_TICKER = "USDCAD=X"


def _rows_from_stored(stored: list[Any]) -> list[dict[str, Any]]:
    return [
        {"date": r.price_date.isoformat(), "adj_close": float(r.adj_close)}
        for r in stored
    ]


async def get_adjusted_closes(
    repo: Any, ticker: str, days: int
) -> list[dict[str, Any]]:
    """Adjusted daily closes for ``ticker`` over the trailing ``days`` window,
    served from the store when fresh, else fetched live and persisted."""
    if repo is None:
        return await market.get_adjusted_closes(ticker, days)

    since = date.today() - timedelta(days=days)
    try:
        stored = await repo.get_daily_prices(ticker, since=since)
    except Exception:  # noqa: BLE001 - store read is best-effort
        logger.warning("daily_prices read failed for %s; fetching live", ticker, exc_info=True)
        stored = []

    if stored:
        latest = stored[-1].price_date
        if (date.today() - latest).days <= STALE_DAYS:
            return _rows_from_stored(stored)

    # Miss or stale: fetch the full window live and persist for next time.
    live = await market.get_adjusted_closes(ticker, days)
    if live:
        try:
            await repo.upsert_daily_prices(ticker, live)
        except Exception:  # noqa: BLE001 - persistence is best-effort
            logger.warning("daily_prices upsert failed for %s", ticker, exc_info=True)
    return live


async def sync_ticker(repo: Any, ticker: str, days: int) -> int:
    """Fetch the full window live and upsert it. Returns rows stored."""
    live = await market.get_adjusted_closes(ticker, days)
    if not live:
        return 0
    return await repo.upsert_daily_prices(ticker, live)


async def run_daily_prices_sync(repo: Any, settings: Any) -> dict[str, Any]:
    """Nightly job body: refresh stored history for every held ticker plus the
    benchmark and FX, serially with spacing so Yahoo doesn't rate-limit us."""
    days = settings.daily_prices_history_days
    tickers = await repo.list_distinct_tickers()
    # The engine also needs these two, which are never "held".
    for extra in (_BENCHMARK_TICKER, _FX_TICKER):
        if extra not in tickers:
            tickers = [*tickers, extra]

    synced = 0
    failed = 0
    for i, ticker in enumerate(tickers):
        if i:
            await asyncio.sleep(_SYNC_SPACING_SECONDS)
        try:
            n = await sync_ticker(repo, ticker, days)
            synced += 1 if n else 0
        except Exception:  # noqa: BLE001 - one bad ticker never aborts the run
            logger.warning("daily_prices sync failed for %s", ticker, exc_info=True)
            failed += 1
    return {
        "tickers": len(tickers),
        "synced": synced,
        "failed": failed,
        "at": datetime.now(timezone.utc).isoformat(),
    }
