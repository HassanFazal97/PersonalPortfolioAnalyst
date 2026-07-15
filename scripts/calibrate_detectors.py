"""Calibrate anomaly-detector thresholds against real daily closes.

Ports the shape of Shizen's calibration harness, adapted for daily equity
bars: false-positive rates are measured on UNMODIFIED real history (organic
flag rate on a fat-tailed noise floor), while detection lag comes from
synthetic anomalies injected into copies of that same history (known
ground-truth injection day). Detectors are fed daily LOG RETURNS — the same
transform app/agent/anomaly/scanner.py uses in production.

Downloads are cached to scripts/.calib_cache/ so the FPR denominator is
reproducible while sweeping thresholds; --refresh re-downloads. This is a
dev tool (like seed_portfolio.py it hits the network for real) — it is not
imported by app/ and not exercised by pytest.

Usage:
    python scripts/calibrate_detectors.py                       # cached data if present
    python scripts/calibrate_detectors.py --refresh             # re-download history
    python scripts/calibrate_detectors.py --tickers AAPL RY.TO --trials 40
    python scripts/calibrate_detectors.py --sweep               # grid over k / h

Prints a markdown table to stdout (paste into README/docs).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detectors import AnomalyDetector, CUSUMDetector, ZScoreDetector  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / ".calib_cache"

# Representative basket: large-cap US, Canadian banks, US + Canadian ETF.
DEFAULT_TICKERS = ["AAPL", "MSFT", "RY.TO", "TD.TO", "SPY", "XIU.TO"]
DEFAULT_DAYS = 1250  # ~5 trading years of calendar span requested from yfinance

TRADING_DAYS_PER_YEAR = 252
POST_INJECTION_DAYS = 40  # how long a trial waits for a detection before "miss"

_WARMUP_MARKERS = ("warming up", "calibrating")


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------

def load_history(ticker: str, days: int, refresh: bool) -> list[float]:
    """Daily closes, oldest first, via the same yfinance seam production uses.

    Cached per (ticker, days) so threshold sweeps see an identical dataset.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker.replace('/', '_')}_{days}d.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())

    from app.tools.market import _fetch_history_raw

    rows = _fetch_history_raw(ticker, days)
    closes = [float(r["close"]) for r in rows]
    cache_file.write_text(json.dumps(closes))
    return closes


def to_returns(closes: list[float]) -> list[float]:
    return [
        math.log(cur / prev)
        for prev, cur in zip(closes, closes[1:])
        if prev > 0 and cur > 0
    ]


# ---------------------------------------------------------------------------
# Scenarios: daily-close analogues of Shizen's spike / shift / burst,
# scaled in units of the series' trailing realized daily sigma so a volatile
# bank stock and a placid ETF get comparable injections.
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict] = {
    "spike": {"type": "spike", "sigma_mult": -4.0},          # one-day 4σ drop
    "level_shift": {"type": "shift", "sigma_mult": -0.8},    # persistent drift
    "variance_burst": {"type": "burst", "mult": 3.0, "span": 15},
}


def trailing_sigma(returns: list[float], idx: int, lookback: int = 60) -> float:
    window = returns[max(0, idx - lookback):idx]
    if len(window) < 10:
        return statistics.pstdev(returns) or 1e-9
    return statistics.pstdev(window) or 1e-9


def inject(returns: list[float], idx: int, scenario: dict, sigma: float) -> list[float]:
    """Pure list surgery on a copy of the returns series."""
    out = list(returns)
    kind = scenario["type"]
    if kind == "spike":
        out[idx] += scenario["sigma_mult"] * sigma
    elif kind == "shift":
        for i in range(idx, len(out)):
            out[i] += scenario["sigma_mult"] * sigma
    elif kind == "burst":
        for i in range(idx, min(len(out), idx + scenario["span"])):
            out[i] *= scenario["mult"]
    return out


# ---------------------------------------------------------------------------
# Trials
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TrialResult:
    fp_count: int
    pre_obs: int
    detected_at: int | None  # lag in trading days from injection, None = miss


def _feed(det: AnomalyDetector, value: float):
    return det.update(value, datetime.now(timezone.utc))


def _run_trial(
    factory: Callable[[], AnomalyDetector],
    returns: list[float],
    inject_idx: int,
    scenario: dict,
) -> TrialResult:
    sigma = trailing_sigma(returns, inject_idx)
    series = inject(returns, inject_idx, scenario, sigma)
    det = factory()

    fp_count = 0
    pre_obs = 0
    for i in range(inject_idx):
        r = _feed(det, series[i])
        if any(m in r.explanation for m in _WARMUP_MARKERS):
            continue
        pre_obs += 1
        fp_count += int(r.is_anomaly)

    detected_at: int | None = None
    for lag in range(POST_INJECTION_DAYS):
        i = inject_idx + lag
        if i >= len(series):
            break
        r = _feed(det, series[i])
        if r.is_anomaly:
            detected_at = lag + 1
            break
    return TrialResult(fp_count=fp_count, pre_obs=pre_obs, detected_at=detected_at)


def calibrate(
    tickers: list[str],
    factories: dict[str, Callable[[], AnomalyDetector]],
    n_trials: int,
    days: int,
    refresh: bool,
    use_returns: bool,
) -> str:
    series_by_ticker: dict[str, list[float]] = {}
    for t in tickers:
        closes = load_history(t, days, refresh)
        series_by_ticker[t] = to_returns(closes) if use_returns else closes
        print(f"  {t}: {len(series_by_ticker[t])} bars", file=sys.stderr)

    lines = [
        "| Detector | Scenario | FP/yr | Median lag (days) | Misses |",
        "|---|---|---:|---:|---:|",
    ]
    for det_name, factory in factories.items():
        for scen_name, scenario in SCENARIOS.items():
            fps = obs = 0
            lags: list[int] = []
            misses = trials = 0
            for series in series_by_ticker.values():
                n = len(series)
                # Slide the injection point across the back half of the real
                # series so each trial sees a different market regime.
                lo, hi = n // 2, n - POST_INJECTION_DAYS
                if hi <= lo:
                    continue
                step = max(1, (hi - lo) // max(1, n_trials // len(series_by_ticker)))
                for inject_idx in range(lo, hi, step):
                    result = _run_trial(factory, series, inject_idx, scenario)
                    fps += result.fp_count
                    obs += result.pre_obs
                    if result.detected_at is None:
                        misses += 1
                    else:
                        lags.append(result.detected_at)
                    trials += 1
            fp_per_year = fps / obs * TRADING_DAYS_PER_YEAR if obs else float("nan")
            med_lag = statistics.median(lags) if lags else float("nan")
            lines.append(
                f"| {det_name} | {scen_name} | {fp_per_year:.2f} "
                f"| {med_lag:.0f} | {misses}/{trials} |"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _factories(k: float, h: float) -> dict[str, Callable[[], AnomalyDetector]]:
    # Mirrors app/config.py anomaly_* defaults; fresh detector per trial.
    return {
        f"zscore(W=60, k={k})": lambda: ZScoreDetector(window=60, k=k),
        f"cusum(warmup=60, δ=0.5, h={h})": lambda: CUSUMDetector(
            warmup=60, delta=0.5, h=h
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--trials", type=int, default=30, help="approx trials per scenario")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--refresh", action="store_true", help="re-download history")
    parser.add_argument("--series", choices=["returns", "closes"], default="returns")
    parser.add_argument("--sweep", action="store_true", help="grid over k and h")
    args = parser.parse_args()

    use_returns = args.series == "returns"
    if args.sweep:
        for k in (2.5, 3.0, 3.5, 4.0):
            for h in (4.0, 6.0, 8.0):
                print(f"\n### k={k}, h={h}\n")
                print(calibrate(
                    args.tickers, _factories(k, h), args.trials,
                    args.days, args.refresh, use_returns,
                ))
                args.refresh = False  # only refresh once
    else:
        print(calibrate(
            args.tickers, _factories(k=3.0, h=6.0), args.trials,
            args.days, args.refresh, use_returns,
        ))


if __name__ == "__main__":
    main()
