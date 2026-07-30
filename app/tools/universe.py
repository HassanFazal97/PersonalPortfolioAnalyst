"""Screening universe (S&P 500 + TSX 60) and its evening data-sync job.

``get_universe`` returns the combined constituent list (generated module,
refreshed quarterly by ``scripts/refresh_universe.py``). ``run_universe_sync``
is the ``picks_sync`` job body: it fills the ``daily_prices`` and
``ticker_fundamentals`` stores for the whole universe the evening before the
pre-market picks run, so the morning pipeline is pure DB reads — fast and
independent of Yahoo uptime.

Rate-limit posture: prices go through the batched ``yf.download`` seam (~a
dozen requests for the whole universe); fundamentals have no batch API, so
they go serially with spacing but **TTL-aware** — only rows that are stale or
errored past their retry window are re-fetched, which also makes a crashed
run cheap to re-run.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.tools import fundamentals, market
from app.tools.tickers import normalize_tickers
from app.tools.universe_constituents import AS_OF, SP500, TSX60

logger = logging.getLogger(__name__)

UNIVERSE_NAME = "sp500+tsx60"

# yf.download chunk size: large enough that the universe is ~a dozen requests,
# small enough that one bad symbol can't poison a huge response.
_PRICE_CHUNK_SIZE = 50
# Incremental daily window; anything with a gap wider than this (or no stored
# history) gets the full settings.picks_history_days window instead.
_INCREMENTAL_DAYS = 30


def get_universe(limit: int = 0) -> list[str]:
    """Combined, normalized, deduped universe. ``limit`` (>0) truncates for
    cheap smoke runs (PICKS_UNIVERSE_LIMIT)."""
    tickers = normalize_tickers([*SP500, *TSX60])
    return tickers[:limit] if limit > 0 else tickers


def universe_snapshot(limit: int = 0) -> dict[str, Any]:
    """Audit block persisted into every picks run payload."""
    tickers = get_universe(limit)
    return {"name": UNIVERSE_NAME, "size": len(tickers), "constituents_as_of": AS_OF}


def _needs_full_window(
    coverage: dict[str, Any] | None, *, today: date, history_days: int
) -> bool:
    """Full-window fetch when the stored series is absent, too shallow, or has
    a gap wider than the incremental window. Mondays refetch everything (the
    caller checks) to re-absorb yfinance's silent re-adjustments."""
    if not coverage:
        return True
    first = coverage.get("first")
    last = coverage.get("last")
    if first is None or last is None:
        return True
    # Shallow: series doesn't reach back near the full window (2-week slack for
    # holidays and the fact that a N-day request returns ~0.7N trading days).
    if (today - first).days < history_days - 14:
        return True
    # Gapped: incremental fetch wouldn't reconnect to the stored series.
    return (today - last).days >= _INCREMENTAL_DAYS


async def _sync_prices(
    repo: Any, tickers: list[str], *, history_days: int, spacing_s: float
) -> tuple[int, int]:
    """Batch-download adjusted closes and upsert per ticker.

    Returns (synced, failed) counts. Full-vs-incremental is decided per ticker
    from stored coverage; Mondays force full windows for everything.
    """
    today = date.today()
    force_full = today.weekday() == 0
    try:
        coverage = await repo.daily_price_coverage(tickers)
    except Exception:  # noqa: BLE001 - coverage read is best-effort
        logger.warning("daily_price_coverage failed; forcing full windows", exc_info=True)
        coverage = {}
        force_full = True

    full: list[str] = []
    incremental: list[str] = []
    for t in tickers:
        if force_full or _needs_full_window(
            coverage.get(t), today=today, history_days=history_days
        ):
            full.append(t)
        else:
            incremental.append(t)

    synced = 0
    failed = 0
    first_chunk = True
    for batch, days in ((full, history_days), (incremental, _INCREMENTAL_DAYS)):
        for i in range(0, len(batch), _PRICE_CHUNK_SIZE):
            chunk = batch[i : i + _PRICE_CHUNK_SIZE]
            if not first_chunk:
                await asyncio.sleep(spacing_s)
            first_chunk = False
            try:
                rows_by_ticker = await asyncio.to_thread(
                    market._fetch_adjusted_closes_batch_raw, chunk, days
                )
            except Exception:  # noqa: BLE001 - one bad chunk never aborts the run
                logger.warning("price chunk download failed (%d tickers)", len(chunk), exc_info=True)
                failed += len(chunk)
                continue
            for ticker in chunk:
                rows = rows_by_ticker.get(ticker)
                if not rows:
                    failed += 1
                    continue
                try:
                    await repo.upsert_daily_prices(ticker, rows)
                    synced += 1
                except Exception:  # noqa: BLE001
                    logger.warning("daily_prices upsert failed for %s", ticker, exc_info=True)
                    failed += 1
    return synced, failed


async def _sync_fundamentals(
    repo: Any, settings: Any, tickers: list[str], *, spacing_s: float
) -> tuple[int, int, int]:
    """TTL-aware serial fundamentals refresh (the run_fundamentals_refresh
    pattern, minus re-fetching rows that are still fresh).

    Returns (refreshed, skipped_fresh, failed)."""
    try:
        rows = await repo.get_ticker_fundamentals(tickers)
    except Exception:  # noqa: BLE001 - treat as all-miss
        logger.warning("bulk fundamentals read failed; refreshing all", exc_info=True)
        rows = {}
    now = datetime.now(timezone.utc)
    ttl = timedelta(hours=settings.fundamentals_ttl_hours)
    error_ttl = timedelta(hours=settings.fundamentals_error_ttl_hours)

    stale: list[str] = []
    skipped = 0
    for ticker in tickers:
        row = rows.get(ticker)
        if row is None:
            stale.append(ticker)
            continue
        age = now - row.fetched_at
        if row.fetch_error:
            if age >= error_ttl:
                stale.append(ticker)
            else:
                skipped += 1
        elif age >= ttl:
            stale.append(ticker)
        else:
            skipped += 1

    refreshed = 0
    failed = 0
    for i, ticker in enumerate(stale):
        if i:
            await asyncio.sleep(spacing_s)
        data = await fundamentals._fetch_and_store(ticker, repo, settings)
        if data is None:
            failed += 1
        else:
            refreshed += 1
    return refreshed, skipped, failed


async def _departed_pick_tickers(repo: Any, universe: set[str]) -> list[str]:
    """Tickers referenced by track-record entries (last 365d) that are no
    longer in the universe — index removals and delistings. Their prices must
    keep syncing so blown-up picks show their real loss instead of a gap."""
    try:
        referenced = await repo.list_pick_entry_tickers(
            since=date.today() - timedelta(days=365)
        )
    except Exception:  # noqa: BLE001 - provenance extras are best-effort
        logger.warning("pick-entry ticker read failed", exc_info=True)
        return []
    return [t for t in referenced if t not in universe]


async def _snapshot_fundamentals(repo: Any, tickers: list[str]) -> int:
    """Append today's point-in-time copy of each ticker's fundamentals
    (migration 026). Error rows are skipped — a snapshot must record what the
    screener can actually use, not a fetch failure."""
    try:
        rows = await repo.get_ticker_fundamentals(tickers)
        payloads = {
            t: row.data
            for t, row in rows.items()
            if row is not None and not row.fetch_error and row.data
        }
        return await repo.insert_fundamentals_snapshots(date.today(), payloads)
    except Exception:  # noqa: BLE001 - snapshots must never break the sync
        logger.warning("fundamentals snapshot failed", exc_info=True)
        return 0


async def _sync_membership(repo: Any) -> dict[str, Any]:
    """Diff the deployed constituent lists into membership history
    (migration 027)."""
    as_of = date.fromisoformat(AS_OF)
    out: dict[str, Any] = {}
    for name, constituents in (("sp500", SP500), ("tsx60", TSX60)):
        try:
            out[name] = await repo.sync_universe_membership(
                name, normalize_tickers(list(constituents)), as_of=as_of
            )
        except Exception:  # noqa: BLE001
            logger.warning("membership sync failed for %s", name, exc_info=True)
            out[name] = {"error": True}
    return out


async def run_universe_sync(repo: Any, settings: Any) -> dict[str, Any]:
    """``picks_sync`` job body: prices then fundamentals for the universe,
    plus the data-provenance writes (PIT snapshots, membership history,
    departed-pick price coverage)."""
    tickers = get_universe(settings.picks_universe_limit)
    spacing = settings.picks_sync_spacing_seconds
    departed = await _departed_pick_tickers(repo, set(tickers))

    prices_synced, prices_failed = await _sync_prices(
        repo,
        [*tickers, *departed],
        history_days=settings.picks_history_days,
        spacing_s=spacing,
    )
    refreshed, skipped, fund_failed = await _sync_fundamentals(
        repo, settings, tickers, spacing_s=spacing
    )
    snapshots = await _snapshot_fundamentals(repo, tickers)
    membership = await _sync_membership(repo)
    result = {
        "tickers": len(tickers),
        "departed_tracked": len(departed),
        "prices_synced": prices_synced,
        "prices_failed": prices_failed,
        "fundamentals_refreshed": refreshed,
        "fundamentals_fresh_skipped": skipped,
        "fundamentals_failed": fund_failed,
        "snapshots_added": snapshots,
        "membership": membership,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("universe sync: %s", result)
    return result
