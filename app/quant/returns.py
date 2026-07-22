"""Build a date-aligned, CAD-based daily log-returns matrix.

This is the load-bearing primitive of the quant engine: covariance, risk
decomposition, VaR, and Monte Carlo all consume the matrix produced here.

Design decisions (each defends a specific correctness trap):

**Adjusted closes only.** Inputs are split- and dividend-adjusted closes
(``market._fetch_adjusted_closes_raw``). Raw closes inject a spurious ~-75%%
"return" on a split date; that one defect corrupts vol and every covariance
entry. See ``market.py``.

**Inner-join on common trading dates — never forward-fill.** TSX and NYSE
diverge on ~8-12 sessions/yr (Family Day, Victoria Day, Juneteenth, ...).
Forward-filling a holding across a day it didn't trade inserts a 0 return on a
day its peers moved, biasing correlations toward zero and understating
portfolio volatility. We intersect the dates and compute returns on the joined
rectangle. The FX and benchmark series are aligned onto the equity
intersection too.

**Common rectangle, not ragged pairwise windows.** Every included holding
shares one date grid. Holdings with too little overlap are *dropped and
flagged*, never zero-padded (fabricates low-vol/low-correlation data) and never
allowed to truncate the whole window to a recent IPO's short history. Ragged
per-pair windows would also produce a non-PSD covariance matrix downstream.

**Currency: everything in a common CAD base, via log additivity.** A CAD
investor's risk on a USD holding includes USD/CAD volatility. In log space this
is exact::

    ln(P_usd * USDCAD) = ln(P_usd) + ln(USDCAD)  =>  r_cad = r_usd + r_fx

So USD holdings' local log returns get the USDCAD=X log return added; CAD
holdings are unchanged. FX volatility and its correlations then flow naturally
into wᵀΣw. This is consistent with ``portfolio._to_cad`` weighting the book in
CAD — mixing local-currency returns with CAD weights would be incoherent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log
from typing import Any

import numpy as np

# USD holdings' CAD returns need this FX series' log returns added. The rest of
# the app already quotes FX with this ticker (``portfolio.FX_TICKER``).
FX_TICKER = "USDCAD=X"

# Fewest common daily observations (returns, i.e. bars - 1) a holding needs to
# earn a place in the covariance rectangle. ~120 ≈ six trading months: enough
# for a stable pairwise covariance without letting a recent IPO amputate the
# whole lookback.
DEFAULT_MIN_OBS = 120


@dataclass
class ReturnsMatrix:
    """A rectangle of aligned daily log returns, in a common CAD base.

    ``matrix`` is shape ``(n_obs, n_assets)``; column ``j`` corresponds to
    ``tickers[j]``. ``dates`` are the return dates (one per row, i.e. the later
    date of each consecutive pair). ``excluded`` maps a dropped ticker to a
    human-readable reason, surfaced to the user so a missing holding is never
    silent.
    """

    tickers: list[str]
    dates: list[str]
    matrix: np.ndarray  # (n_obs, n_assets), CAD log returns
    excluded: dict[str, str] = field(default_factory=dict)
    # Benchmark log returns (CAD-based) aligned to ``dates``; NaN on any date
    # the benchmark lacked. None when no benchmark was supplied. Used for
    # portfolio beta / scenario stress (kept out of the covariance matrix).
    benchmark_returns: np.ndarray | None = None

    @property
    def n_obs(self) -> int:
        return self.matrix.shape[0] if self.matrix.size else 0

    @property
    def n_assets(self) -> int:
        return len(self.tickers)


def _closes_by_date(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Map ISO date -> adjusted close, dropping non-positive/absent prices.

    Accepts either the ``{date, adj_close}`` shape from
    ``market._fetch_adjusted_closes_raw`` or a raw ``{date, close}`` row, so
    the pure builder can be unit-tested with either.
    """
    out: dict[str, float] = {}
    for r in rows:
        date = r.get("date")
        price = r.get("adj_close")
        if price is None:
            price = r.get("close")
        if date is None or price is None:
            continue
        price = float(price)
        if price > 0:
            out[str(date)] = price
    return out


def _log_returns_on_dates(
    closes: dict[str, float], dates: list[str]
) -> np.ndarray:
    """Log returns over consecutive ``dates`` (which must be sorted and all
    present in ``closes``). Returns length ``len(dates) - 1``."""
    prices = [closes[d] for d in dates]
    return np.array(
        [log(prices[i] / prices[i - 1]) for i in range(1, len(prices))],
        dtype=float,
    )


def _aligned_benchmark_returns(
    benchmark_rows: list[dict[str, Any]] | None,
    benchmark_currency: str,
    common_dates: list[str],
    fx_closes: dict[str, float],
) -> np.ndarray | None:
    """CAD-based benchmark log returns aligned to ``common_dates[1:]``.

    NaN on any date the benchmark (or, for a USD benchmark, the FX series)
    lacked, so beta computation can drop those pairwise.
    """
    if not benchmark_rows:
        return None
    bench = _closes_by_date(benchmark_rows)
    is_usd = (benchmark_currency or "USD").upper() == "USD"
    vec = np.full(len(common_dates) - 1, np.nan, dtype=float)
    for i in range(1, len(common_dates)):
        d0, d1 = common_dates[i - 1], common_dates[i]
        if d0 not in bench or d1 not in bench:
            continue
        r = log(bench[d1] / bench[d0])
        if is_usd:
            if d0 not in fx_closes or d1 not in fx_closes:
                continue
            r += log(fx_closes[d1] / fx_closes[d0])
        vec[i - 1] = r
    return vec


def build_returns_matrix(
    closes_by_ticker: dict[str, list[dict[str, Any]]],
    currency_by_ticker: dict[str, str],
    fx_rows: list[dict[str, Any]] | None,
    *,
    min_obs: int = DEFAULT_MIN_OBS,
    benchmark_rows: list[dict[str, Any]] | None = None,
    benchmark_currency: str = "USD",
) -> ReturnsMatrix:
    """Assemble the CAD-based, date-aligned log-returns rectangle.

    Pure: all fetching happens in the caller (the tool layer), which passes the
    already-fetched adjusted-close rows here. ``fx_rows`` is the USDCAD=X
    series; it may be ``None`` only when every holding is CAD (else USD
    holdings are excluded for want of an FX series).

    ``benchmark_rows`` (optional) is aligned onto the SAME date grid and
    returned as ``ReturnsMatrix.benchmark_returns`` (CAD-based, NaN on dates the
    benchmark lacked) — for portfolio beta / scenario stress. It is kept out of
    the covariance matrix. A USD benchmark needs ``fx_rows`` to convert to CAD.
    """
    parsed: dict[str, dict[str, float]] = {
        t: _closes_by_date(rows) for t, rows in closes_by_ticker.items()
    }
    fx_closes = _closes_by_date(fx_rows or [])

    excluded: dict[str, str] = {}

    # A USD holding needs the FX series on its own dates; treat "no FX at all"
    # as an exclusion reason rather than silently dropping FX risk.
    needs_fx = {
        t
        for t, cur in currency_by_ticker.items()
        if (cur or "CAD").upper() == "USD"
    }
    fx_available = len(fx_closes) > 0

    # Candidate tickers: enough of their OWN history to possibly reach min_obs,
    # and (for USD) an available FX series. Dropping short-history holdings up
    # front stops a recent IPO from amputating the shared window for everyone.
    candidates: list[str] = []
    for t, closes in parsed.items():
        if t in needs_fx and not fx_available:
            excluded[t] = "USD holding but USDCAD=X FX series unavailable"
            continue
        if len(closes) < min_obs + 1:
            excluded[t] = (
                f"insufficient price history ({max(0, len(closes) - 1)} "
                f"returns < {min_obs})"
            )
            continue
        candidates.append(t)

    if not candidates:
        return ReturnsMatrix(tickers=[], dates=[], matrix=np.empty((0, 0)), excluded=excluded)

    # A single common date rectangle across the included names. If the full
    # intersection is too thin, greedily drop the holding with the fewest
    # observations (the one most restricting the window) and retry — retaining
    # as many holdings as the shared grid allows.
    def _common(ts: list[str]) -> list[str]:
        common = set.intersection(*(set(parsed[t]) for t in ts))
        if (needs_fx & set(ts)) and fx_available:
            common &= set(fx_closes)
        return sorted(common)

    common_dates = _common(candidates)
    while len(common_dates) < min_obs + 1 and len(candidates) > 1:
        victim = min(candidates, key=lambda t: len(parsed[t]))
        candidates.remove(victim)
        excluded[victim] = (
            f"insufficient overlapping history "
            f"({max(0, len(common_dates) - 1)} common returns < {min_obs})"
        )
        common_dates = _common(candidates)

    if len(common_dates) < min_obs + 1:
        for t in candidates:
            excluded[t] = (
                f"insufficient overlapping history "
                f"({max(0, len(common_dates) - 1)} common returns < {min_obs})"
            )
        return ReturnsMatrix(tickers=[], dates=[], matrix=np.empty((0, 0)), excluded=excluded)

    fx_returns = (
        _log_returns_on_dates(fx_closes, common_dates)
        if (needs_fx & set(candidates)) and fx_available
        else None
    )

    columns: list[np.ndarray] = []
    included: list[str] = []
    for t in sorted(candidates):
        local = _log_returns_on_dates(parsed[t], common_dates)
        if (currency_by_ticker.get(t) or "CAD").upper() == "USD" and fx_returns is not None:
            cad = local + fx_returns  # r_cad = r_local + r_fx, exact in log space
        else:
            cad = local
        columns.append(cad)
        included.append(t)

    matrix = np.column_stack(columns) if columns else np.empty((0, 0))

    benchmark_returns = _aligned_benchmark_returns(
        benchmark_rows, benchmark_currency, common_dates, fx_closes
    )

    return ReturnsMatrix(
        tickers=included,
        dates=common_dates[1:],  # returns[i] belongs to the later date
        matrix=matrix,
        excluded=excluded,
        benchmark_returns=benchmark_returns,
    )
