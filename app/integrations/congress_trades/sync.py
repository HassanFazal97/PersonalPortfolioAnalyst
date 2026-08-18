"""Sync job: Senate + House Stock Watcher -> notable_investors / notable_investor_trades.

Both sources are fetched and processed independently so one going dark (e.g.
a bucket 404ing) never blocks the other. Every record maps via a stable key
(bioguide_id for the investor, a content hash for the trade — see mapper.py)
so re-running this against the same dump is a no-op upsert, not a duplicate
insert; this is what makes "daily, full re-fetch" an acceptable incremental
strategy for a source with no true pagination.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings
from app.db.repo import Repo
from app.integrations.congress_trades.client import fetch_transactions
from app.integrations.congress_trades.mapper import map_record

logger = logging.getLogger(__name__)


async def _sync_chamber(repo: Repo, *, chamber: str, url: str, settings: Settings) -> dict[str, Any]:
    summary = {"chamber": chamber, "fetched": 0, "new": 0, "errors": 0}
    rows = await fetch_transactions(url, settings=settings)
    summary["fetched"] = len(rows)
    for raw in rows:
        try:
            mapped = map_record(raw, chamber=chamber)
            if mapped is None:
                continue
            investor, trade = mapped
            investor_id = await repo.upsert_congress_investor(investor)
            inserted = await repo.upsert_notable_investor_trade(
                investor_id=investor_id, trade=trade
            )
            if inserted:
                summary["new"] += 1
        except Exception:  # noqa: BLE001 - one bad row must not abort the run
            summary["errors"] += 1
            logger.warning("congress_trades: failed to map/upsert a row", exc_info=True)
    return summary


async def sync_congress_trades(repo: Repo, *, settings: Settings | None = None) -> dict[str, Any]:
    """Fetch Senate + House Stock Watcher dumps and upsert into the global
    notable_investors/notable_investor_trades tables. Returns a summary dict
    used both for logging and for the heartbeat_wrapped job result."""
    settings = settings or get_settings()
    senate = await _sync_chamber(
        repo, chamber="senate", url=settings.senate_stock_watcher_url, settings=settings
    )
    house = await _sync_chamber(
        repo, chamber="house", url=settings.house_stock_watcher_url, settings=settings
    )
    total_fetched = senate["fetched"] + house["fetched"]
    if total_fetched == 0:
        # Both sources returned nothing — likely a fetch failure on both
        # (real datasets are never empty), so surface as a job failure rather
        # than a quiet success.
        raise RuntimeError("congress_trades_sync: both Senate and House fetches returned no rows")
    return {"senate": senate, "house": house}
