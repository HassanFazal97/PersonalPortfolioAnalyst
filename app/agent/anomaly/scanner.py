"""Global, model-free detector pass over daily closes.

Detectors run on daily **log returns**, not raw closes: prices are a random
walk (a rolling z-score or frozen-baseline CUSUM on raw prices flags
constantly on any trending stock), while returns are approximately
stationary. Bar-to-bar returns also sidestep weekend/holiday calendar gaps.

State is not persisted: each run instantiates fresh detectors per ticker and
replays the history window, and only the FINAL bar's verdict counts. CUSUM's
reset-after-flag means yesterday's already-flagged shift replays as a
mid-history flag (ignored) and the final bar is post-reset — most
day-over-day repeats vanish without any persistence.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

from pydantic import BaseModel

from app.config import Settings
from app.detectors import (
    AnomalyDetector,
    CUSUMDetector,
    DetectionResult,
    DivergenceDetector,
    ZScoreDetector,
)
from app.tools import market

logger = logging.getLogger(__name__)

# yfinance throttling: at most this many concurrent history fetches, with a
# small stagger between task starts.
_FETCH_CONCURRENCY = 3
_FETCH_STAGGER_S = 0.25

_BENCHMARK_PEER = "benchmark"


class AnomalyFlag(BaseModel):
    """One detector's final-bar verdict on one ticker, ready for aggregation."""

    ticker: str
    detector: str
    direction: str  # "up" | "down" | "decoupled"
    severity: float
    score: float
    explanation: str
    last_close: float
    day_change_pct: float | None = None


def log_returns(closes: list[float]) -> list[float]:
    """Daily log returns; skips non-positive prices defensively."""
    out: list[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev <= 0 or cur <= 0:
            out.append(0.0)
        else:
            out.append(math.log(cur / prev))
    return out


def min_bars_required(settings: Settings) -> int:
    """Fewest daily bars a ticker needs before the detectors can speak.

    Driven by the z-score warm-up (min_samples = window // 2, floor 10) plus
    the one bar consumed by the returns transform. CUSUM needs more bars to
    leave warm-up; with fewer it simply never flags, which is fine.
    """
    return max(10, settings.anomaly_zscore_window // 2) + 2


def _build_detectors(
    settings: Settings, *, with_divergence: bool
) -> list[AnomalyDetector]:
    detectors: list[AnomalyDetector] = [
        ZScoreDetector(window=settings.anomaly_zscore_window, k=settings.anomaly_zscore_k),
        CUSUMDetector(
            warmup=settings.anomaly_cusum_warmup,
            delta=settings.anomaly_cusum_delta,
            h=settings.anomaly_cusum_h,
        ),
    ]
    if with_divergence:
        detectors.append(
            DivergenceDetector(
                peer=_BENCHMARK_PEER,
                window=settings.anomaly_divergence_window,
                calibration=settings.anomaly_divergence_calibration,
                threshold=settings.anomaly_divergence_threshold,
            )
        )
    return detectors


def _direction(result: DetectionResult) -> str:
    if result.method == "zscore":
        z = result.params.get("z", 0.0)
        return "up" if z > 0 else "down"
    if result.method == "cusum":
        # CUSUM zeroes S_h/S_l on flag, so params are post-reset — the
        # explanation string is the only place direction survives.
        return "up" if "upward" in result.explanation else "down"
    return "decoupled"  # divergence is one-sided: correlation dropped


def run_detectors_on_series(
    ticker: str,
    rows: list[dict],
    *,
    settings: Settings,
    benchmark_returns: dict[str, float] | None = None,
) -> list[AnomalyFlag]:
    """Replay one ticker's daily bars through fresh detectors; return the
    final bar's anomalies (already filtered to severity >= anomaly_min_severity).

    ``benchmark_returns`` maps date (ISO string) -> benchmark log return; when
    provided, the divergence detector runs with the benchmark as its peer.
    Bars whose date is missing from the map leave the divergence detector
    untouched (it returns early without ingesting), keeping the pair aligned.
    """
    closes = [float(r["close"]) for r in rows]
    if len(closes) < min_bars_required(settings):
        logger.debug("anomaly scan: skipping %s (only %d bars)", ticker, len(closes))
        return []

    returns = log_returns(closes)
    dates = [r["date"] for r in rows[1:]]  # returns[i] belongs to rows[i+1]

    detectors = _build_detectors(
        settings, with_divergence=benchmark_returns is not None
    )
    finals: list[DetectionResult] = []
    for det in detectors:
        result: DetectionResult | None = None
        for date_str, ret in zip(dates, returns):
            try:
                ts = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
            except ValueError:
                ts = datetime.now(timezone.utc)
            if isinstance(det, DivergenceDetector):
                peer = (benchmark_returns or {}).get(date_str)
                result = det.update(ret, ts, peer_value=peer)
            else:
                result = det.update(ret, ts)
        if result is not None:
            finals.append(result)

    day_change_pct = None
    if len(closes) >= 2 and closes[-2] > 0:
        day_change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100

    flags: list[AnomalyFlag] = []
    for result in finals:
        if not result.is_anomaly:
            continue
        if result.severity < settings.anomaly_min_severity:
            continue
        flags.append(
            AnomalyFlag(
                ticker=ticker,
                detector=result.method,
                direction=_direction(result),
                severity=result.severity,
                score=result.score,
                explanation=result.explanation,
                last_close=closes[-1],
                day_change_pct=day_change_pct,
            )
        )
    return flags


async def _fetch_history(ticker: str, days: int) -> list[dict]:
    return await asyncio.to_thread(market._fetch_history_raw, ticker, days)


async def scan_tickers(
    tickers: list[str], *, settings: Settings
) -> dict[str, list[AnomalyFlag]]:
    """Run the detectors over every distinct ticker; return only flagged ones.

    A per-ticker fetch failure skips that ticker — it never aborts the scan.
    """
    days = settings.anomaly_history_days

    benchmark_returns: dict[str, float] | None = None
    bench = settings.anomaly_benchmark_ticker.strip()
    if bench:
        try:
            rows = await _fetch_history(bench, days)
            rets = log_returns([float(r["close"]) for r in rows])
            benchmark_returns = {r["date"]: ret for r, ret in zip(rows[1:], rets)}
        except Exception:
            logger.warning(
                "anomaly scan: benchmark %s fetch failed; divergence disabled this run",
                bench,
                exc_info=True,
            )

    sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def scan_one(index: int, ticker: str) -> tuple[str, list[AnomalyFlag]]:
        async with sem:
            await asyncio.sleep(_FETCH_STAGGER_S * index)
            try:
                rows = await _fetch_history(ticker, days)
            except Exception:
                logger.warning("anomaly scan: fetch failed for %s", ticker, exc_info=True)
                return ticker, []
        return ticker, run_detectors_on_series(
            ticker, rows, settings=settings, benchmark_returns=benchmark_returns
        )

    results = await asyncio.gather(
        *(scan_one(i, t) for i, t in enumerate(sorted(set(tickers))))
    )
    return {ticker: flags for ticker, flags in results if flags}
