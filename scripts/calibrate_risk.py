"""Backtest the tail-risk engine's Value at Risk against realized returns.

Sibling of ``scripts/calibrate_detectors.py``: a dev tool (hits the network for
real, caches to ``scripts/.calib_cache/``, NOT imported by ``app/`` and NOT run
by pytest). It answers the only question that makes a VaR number honest — *does
it get breached about as often as it claims?* A 95%% VaR should be exceeded on
~5%% of days; too few breaches means the model overstates risk, too many means
it understates it (the dangerous direction).

Two standard tests per method/confidence:

- **Kupiec POF (unconditional coverage).** Is the breach *rate* statistically
  consistent with 1 − confidence? Likelihood-ratio statistic ~ χ²(1).
- **Christoffersen (conditional coverage).** Adds an independence test — do
  breaches *cluster* (a breach today makes a breach tomorrow more likely)?
  Clustering means the model misses volatility regimes even when the average
  rate looks fine. LR_cc = LR_pof + LR_ind ~ χ²(2).

Methods compared: parametric Gaussian, Cornish-Fisher (with the production
validity guard → historical fallback), and empirical historical VaR — each
estimated from a rolling trailing window using only past data, then checked
against the next day's realized return.

Usage:
    python scripts/calibrate_risk.py                       # cached data if present
    python scripts/calibrate_risk.py --refresh             # re-download history
    python scripts/calibrate_risk.py --tickers SPY XIU.TO --window 250
    python scripts/calibrate_risk.py --confidences 0.95 0.99
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import chi2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.quant import tailrisk  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / ".calib_cache"

# Large-cap US, Canadian banks, US + Canadian ETFs — same spirit as the
# detector basket, spanning volatility regimes and both exchange calendars.
DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "RY.TO", "TD.TO", "SPY", "XIU.TO"]
DEFAULT_DAYS = 1250  # ~5 trading years so the rolling backtest has runway.
DEFAULT_WINDOW = 250  # trailing estimation window (one trading year).


def load_adjusted_closes(ticker: str, days: int, refresh: bool) -> list[float]:
    """Adjusted daily closes (oldest first), cached per (ticker, days).

    Uses the SAME adjusted-close seam production's returns engine uses — a VaR
    backtest on unadjusted close would be corrupted by split-date jumps.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker.replace('/', '_')}_{days}d_adj.json"
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())

    from app.tools.market import _fetch_adjusted_closes_raw

    rows = _fetch_adjusted_closes_raw(ticker, days)
    closes = [float(r["adj_close"]) for r in rows]
    cache_file.write_text(json.dumps(closes))
    return closes


def simple_returns(closes: list[float]) -> np.ndarray:
    c = np.asarray(closes, dtype=float)
    return c[1:] / c[:-1] - 1.0


def _var_for_method(window: np.ndarray, confidence: float, method: str) -> float:
    """One-day VaR (positive loss) from a trailing window, per method."""
    if method == "gaussian":
        mu = float(window.mean())
        sigma = float(window.std(ddof=1))
        return tailrisk.gaussian_var(mu, sigma, confidence)
    if method == "historical":
        return tailrisk.historical_var(window, confidence)
    # "headline" = production behaviour: Cornish-Fisher when valid, else historical.
    return tailrisk.value_at_risk(window, confidence).headline_pct


def breach_indicators(
    returns: np.ndarray, window: int, confidence: float, method: str
) -> np.ndarray:
    """1 where the next-day realized loss exceeded the VaR forecast, else 0."""
    flags = []
    for t in range(window, len(returns)):
        trailing = returns[t - window : t]
        var = _var_for_method(trailing, confidence, method)
        realized = returns[t]
        flags.append(1 if realized < -var else 0)
    return np.array(flags, dtype=int)


def kupiec_pof(breaches: np.ndarray, p: float) -> tuple[float, float]:
    """Kupiec proportion-of-failures LR statistic and its χ²(1) p-value."""
    n = breaches.size
    x = int(breaches.sum())
    if n == 0:
        return 0.0, 1.0
    rate = x / n
    # Null log-likelihood at the claimed rate p.
    ll_null = (n - x) * np.log(1 - p) + x * np.log(p)
    # Unrestricted log-likelihood at the observed rate (limits handle x∈{0,n}).
    ll_alt = 0.0
    if 0 < rate < 1:
        ll_alt = (n - x) * np.log(1 - rate) + x * np.log(rate)
    lr = -2 * (ll_null - ll_alt)
    lr = max(lr, 0.0)
    return lr, float(chi2.sf(lr, 1))


def christoffersen_cc(breaches: np.ndarray, p: float) -> tuple[float, float]:
    """Conditional-coverage LR (Kupiec + independence) and its χ²(2) p-value."""
    n = breaches.size
    if n < 2:
        return 0.0, 1.0
    n00 = n01 = n10 = n11 = 0
    for prev, cur in zip(breaches[:-1], breaches[1:]):
        if prev == 0 and cur == 0:
            n00 += 1
        elif prev == 0 and cur == 1:
            n01 += 1
        elif prev == 1 and cur == 0:
            n10 += 1
        else:
            n11 += 1

    def _xlog(count: int, prob: float) -> float:
        return count * np.log(prob) if count > 0 and prob > 0 else 0.0

    pi01 = n01 / (n00 + n01) if (n00 + n01) else 0.0
    pi11 = n11 / (n10 + n11) if (n10 + n11) else 0.0
    pi = (n01 + n11) / n if n else 0.0

    ll_ind_null = _xlog(n00 + n10, 1 - pi) + _xlog(n01 + n11, pi)
    ll_ind_alt = (
        _xlog(n00, 1 - pi01)
        + _xlog(n01, pi01)
        + _xlog(n10, 1 - pi11)
        + _xlog(n11, pi11)
    )
    lr_ind = max(-2 * (ll_ind_null - ll_ind_alt), 0.0)
    lr_pof, _ = kupiec_pof(breaches, p)
    lr_cc = lr_pof + lr_ind
    return lr_cc, float(chi2.sf(lr_cc, 2))


def backtest_series(
    name: str, returns: np.ndarray, window: int, confidences: list[float]
) -> list[dict]:
    rows = []
    for c in confidences:
        p = 1 - c
        for method in ("headline", "gaussian", "historical"):
            flags = breach_indicators(returns, window, c, method)
            n = flags.size
            x = int(flags.sum())
            _, pof_p = kupiec_pof(flags, p)
            _, cc_p = christoffersen_cc(flags, p)
            rows.append(
                {
                    "series": name,
                    "method": method,
                    "confidence": c,
                    "n": n,
                    "breaches": x,
                    "breach_rate": x / n if n else 0.0,
                    "expected_rate": p,
                    "kupiec_p": pof_p,
                    "cc_p": cc_p,
                    # A model passes when neither test rejects at 5%.
                    "pass": pof_p > 0.05 and cc_p > 0.05,
                }
            )
    return rows


def equal_weight_portfolio(series_by_ticker: dict[str, list[float]]) -> np.ndarray:
    """An equal-weight portfolio's daily simple returns, date-aligned by index.

    A rough blend (positional, assuming shared calendar) — enough to exercise
    the VaR math on a diversified series; the production tool does the rigorous
    date-intersection alignment.
    """
    rets = [simple_returns(c) for c in series_by_ticker.values()]
    min_len = min(len(r) for r in rets)
    stacked = np.column_stack([r[-min_len:] for r in rets])
    return stacked.mean(axis=1)


def _fmt(rows: list[dict]) -> str:
    header = (
        "| series | method | conf | n | breaches | breach% | exp% | "
        "Kupiec p | CC p | pass |"
    )
    sep = "|" + "---|" * 10
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"| {r['series']} | {r['method']} | {r['confidence']:.0%} | {r['n']} | "
            f"{r['breaches']} | {r['breach_rate']:.2%} | {r['expected_rate']:.2%} | "
            f"{r['kupiec_p']:.3f} | {r['cc_p']:.3f} | {'✅' if r['pass'] else '❌'} |"
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    ap.add_argument("--confidences", nargs="+", type=float, default=[0.95, 0.99])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    series_by_ticker: dict[str, list[float]] = {}
    all_rows: list[dict] = []
    for ticker in args.tickers:
        try:
            closes = load_adjusted_closes(ticker, args.days, args.refresh)
        except Exception as exc:  # noqa: BLE001 - one bad ticker never aborts
            print(f"skip {ticker}: {exc}", file=sys.stderr)
            continue
        if len(closes) < args.window + 30:
            print(f"skip {ticker}: only {len(closes)} closes", file=sys.stderr)
            continue
        series_by_ticker[ticker] = closes
        all_rows += backtest_series(
            ticker, simple_returns(closes), args.window, args.confidences
        )

    if len(series_by_ticker) >= 2:
        port = equal_weight_portfolio(series_by_ticker)
        all_rows += backtest_series(
            "EQUAL_WEIGHT", port, args.window, args.confidences
        )

    print(_fmt(all_rows))
    passed = sum(1 for r in all_rows if r["pass"])
    print(f"\n{passed}/{len(all_rows)} series·method·confidence combos pass at 5%.")


if __name__ == "__main__":
    main()
