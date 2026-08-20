"""Honest track record for published stock-pick cohorts.

The product publishes a ranked list of picks each run ("cohort"). A per-entry
scoreboard is dishonest in two ways this module is built to fix:

**Per-entry averaging double-counts persistence.** A name republished 30 runs
in a row appears 30 times with near-identical overlapping windows, dominating
every average. Here the unit of account is the *cohort*: one published list is
one observation, its return the equal-weighted mean of its members. Summary
stats then average across cohorts, never across raw entries.

**Partially elapsed horizons flatter whoever reports them.** A "30-day return"
measured 12 days in is whatever the market did this week. A horizon is
reported only once ``run_date + H`` is on or before the latest benchmark date
— i.e. the window has fully elapsed — otherwise it is ``None``.

Fixed measurement conventions (each defends a hindsight/lookahead trap):

- **Entry bar = last close strictly BEFORE run_date.** Picks publish
  pre-market, so the entry price freezes at the prior close; using run_date's
  own close would grant the pick a day of hindsight.
- **Exit bar = last close on or before ``run_date + H`` days** (calendar
  days; the exit naturally lands on the preceding trading day).
- **Benchmark over the identical span**: entry = last benchmark close before
  run_date, exit = last benchmark close ≤ run_date + H. Comparing a pick
  window against a different benchmark window manufactures alpha.
- **One consistent adjusted-close series version.** Inputs must be
  dividend/split-adjusted closes from a single series version; mixing raw and
  adjusted (or two adjustment epochs) fabricates a return at the seam.

``simulate_top_picks`` answers the natural follow-up — "what if I had bought
the top N every run?" — as a replay NAV: equal-weight the top N at each run's
entry bar, buy-and-hold between runs (weights drift with prices, as a real
account's would), rebalance into the new top N at the next run's entry bar.
No transaction costs (a later phase nets them). Members without a pre-run
close are dropped from that window's basket (weights renormalize); if a whole
basket is unpriceable the NAV carries flat until the next priceable rebalance.

Pure and I/O-free: callers pass ``(date, adjusted_close)`` series; every
output is a plain dict/list of JSON-safe values.
"""

from __future__ import annotations

import datetime as dt
from bisect import bisect_left, bisect_right
from typing import Any

import numpy as np

from app.quant import performance, tailrisk

DEFAULT_HORIZONS_DAYS = (7, 30, 91, 182)

# (sorted dates, prices) — the internal shape of a cleaned price series.
_Series = tuple[list[dt.date], list[float]]


def clean_series(rows: list[tuple[dt.date, float]] | None) -> _Series:
    """Sort a ``(date, price)`` series and drop non-positive prices.

    Duplicate dates keep the last value seen. A non-positive adjusted close is
    a data defect (it would fabricate a nonsense return), never a real price.
    """
    pairs = sorted((d, float(p)) for d, p in (rows or []) if p is not None and p > 0)
    dates: list[dt.date] = []
    prices: list[float] = []
    for d, p in pairs:
        if dates and dates[-1] == d:
            prices[-1] = p
        else:
            dates.append(d)
            prices.append(p)
    return dates, prices


def last_before(series: _Series, day: dt.date) -> tuple[dt.date, float] | None:
    """Last (date, price) bar strictly before ``day``, or None."""
    dates, prices = series
    i = bisect_left(dates, day) - 1
    return (dates[i], prices[i]) if i >= 0 else None


def last_on_or_before(series: _Series, day: dt.date) -> tuple[dt.date, float] | None:
    """Last (date, price) bar on or before ``day``, or None (LOCF lookup)."""
    dates, prices = series
    i = bisect_right(dates, day) - 1
    return (dates[i], prices[i]) if i >= 0 else None


# Backwards-compatible aliases (helpers were private before forecastscore.py
# began sharing the same measurement conventions).
_clean_series = clean_series
_last_before = last_before
_last_on_or_before = last_on_or_before


def _cohorts(entries: list[dict[str, Any]]) -> list[tuple[dt.date, list[str]]]:
    """Group entries into (run_date, ordered member tickers), oldest first.

    Members are ordered by (rank, ticker) — the ticker tiebreak keeps rank
    ties deterministic. A ticker repeated within a cohort is deduplicated to
    its best (lowest) rank so it can't be double-weighted.
    """
    by_run: dict[dt.date, dict[str, int]] = {}
    for e in entries:
        run_date, ticker, rank = e["run_date"], e["ticker"], int(e["rank"])
        ranks = by_run.setdefault(run_date, {})
        ranks[ticker] = min(rank, ranks.get(ticker, rank))
    out: list[tuple[dt.date, list[str]]] = []
    for run_date in sorted(by_run):
        ranks = by_run[run_date]
        members = sorted(ranks, key=lambda t: (ranks[t], t))
        out.append((run_date, members))
    return out


def cohort_returns(
    entries: list[dict[str, Any]],
    prices: dict[str, list[tuple[dt.date, float]]],
    benchmark: list[tuple[dt.date, float]],
    *,
    horizons_days: tuple[int, ...] = DEFAULT_HORIZONS_DAYS,
) -> dict[str, Any]:
    """Per-cohort and per-horizon equal-weighted returns vs the benchmark.

    ``entries`` are ``{"run_date": date, "ticker": str, "rank": int}`` dicts;
    ``prices`` maps ticker -> ``[(date, adjusted_close), ...]`` oldest first;
    ``benchmark`` is the same shape (e.g. SPY adjusted closes).

    For each cohort and horizon H (calendar days): each member's return runs
    from its entry bar (last close strictly before run_date) to its exit bar
    (last close ≤ run_date + H). A member with no entry bar, or no bar after
    the entry bar within the horizon, is excluded from that horizon (the
    ``measured`` counts make the exclusions visible). A horizon is reported
    only when fully elapsed against the benchmark calendar and the benchmark
    span itself is computable; otherwise its slot is ``None``.

    Returns ``{"cohorts": [...newest first...], "horizon_summary": {...}}``
    with percents rounded to 2 decimals. ``beat`` compares unrounded values.
    """
    series = {t: clean_series(rows) for t, rows in prices.items()}
    bench = clean_series(benchmark)
    latest_bench = bench[0][-1] if bench[0] else None

    cohorts_out: list[dict[str, Any]] = []
    # str(H) -> list of (cohort_return, benchmark_return), unrounded.
    raw_by_horizon: dict[str, list[tuple[float, float]]] = {
        str(h): [] for h in horizons_days
    }

    for run_date, members in reversed(_cohorts(entries)):
        entries_bars: dict[str, tuple[dt.date, float]] = {}
        for t in members:
            s = series.get(t)
            bar = last_before(s, run_date) if s else None
            if bar is not None:
                entries_bars[t] = bar

        horizons: dict[str, dict[str, Any] | None] = {}
        measured = 0
        for h in horizons_days:
            key = str(h)
            end = run_date + dt.timedelta(days=h)
            if latest_bench is None or end > latest_bench:
                horizons[key] = None  # horizon not fully elapsed: don't report
                continue
            b_entry = last_before(bench, run_date)
            b_exit = last_on_or_before(bench, end)
            if b_entry is None or b_exit is None or b_exit[0] <= b_entry[0]:
                horizons[key] = None  # no benchmark span to compare against
                continue
            rets: list[float] = []
            for t in members:
                bar = entries_bars.get(t)
                if bar is None:
                    continue
                exit_bar = last_on_or_before(series[t], end)
                if exit_bar is None or exit_bar[0] <= bar[0]:
                    continue  # no bar after entry within the horizon
                rets.append(exit_bar[1] / bar[1] - 1.0)
            if not rets:
                horizons[key] = None
                continue
            ret = float(np.mean(rets))
            bench_ret = b_exit[1] / b_entry[1] - 1.0
            raw_by_horizon[key].append((ret, bench_ret))
            # Measurability is monotone in H (a later exit bar only helps), so
            # the max across reported horizons is the union of measured names.
            measured = max(measured, len(rets))
            horizons[key] = {
                "return_pct": round(ret * 100, 2),
                "benchmark_return_pct": round(bench_ret * 100, 2),
                "beat": ret > bench_ret,
                "measured": len(rets),
            }

        cohorts_out.append(
            {
                "run_date": run_date.isoformat(),
                "members": len(members),
                "measured": measured,
                "horizons": horizons,
            }
        )

    horizon_summary: dict[str, dict[str, Any] | None] = {}
    for h in horizons_days:
        key = str(h)
        vals = raw_by_horizon[key]
        if not vals:
            horizon_summary[key] = None
            continue
        n = len(vals)
        beats = sum(1 for r, b in vals if r > b)
        horizon_summary[key] = {
            "cohorts": n,
            "avg_return_pct": round(sum(r for r, _ in vals) / n * 100, 2),
            "avg_benchmark_return_pct": round(sum(b for _, b in vals) / n * 100, 2),
            "beat_rate_pct": round(100.0 * beats / n, 2),
        }

    return {"cohorts": cohorts_out, "horizon_summary": horizon_summary}


def _benchmark_navs(bench: _Series, dates: list[dt.date]) -> np.ndarray:
    """Benchmark NAV at each date (LOCF), normalized to 1.0 at ``dates[0]``."""
    if not bench[0]:
        return np.ones(len(dates))
    base_bar = last_on_or_before(bench, dates[0])
    base = base_bar[1] if base_bar else bench[1][0]
    out = []
    for d in dates:
        bar = last_on_or_before(bench, d)
        out.append((bar[1] if bar else base) / base)
    return np.array(out, dtype=float)


def simulate_top_picks(
    entries: list[dict[str, Any]],
    prices: dict[str, list[tuple[dt.date, float]]],
    benchmark: list[tuple[dt.date, float]],
    *,
    top_n: int = 5,
) -> dict[str, Any]:
    """Replay NAV of buying the top-N picks at every run, no costs.

    Mechanics: at each run_date's entry bar (last close before the run),
    rebalance into the top-N of that cohort, equal-weighted; buy-and-hold
    until the next run's entry bar (weights drift with prices). The top-N is
    selected by (rank, ticker) BEFORE the coverage filter — an unpriceable
    top pick is dropped and its weight renormalized over the rest, never
    backfilled with rank N+1 (that would quietly change the published bet).

    The trading calendar per window is the union of the basket members' own
    dates; a member missing an interior date is carried at its last observed
    close (LOCF), so its return accrues when it next prints. If an entire
    basket has no pre-run close, the NAV carries flat until the next
    priceable rebalance.

    Returns daily ``nav`` points (4 dp; benchmark NAV normalized to 1.0 at
    the start date, LOCF between benchmark prints) plus ``stats`` computed
    from the unrounded daily simple returns of the NAV series, reusing
    ``performance.sharpe`` / ``performance.tracking_error`` /
    ``tailrisk.max_drawdown``. Fewer than 2 NAV points -> ``{"nav": [],
    "stats": None}``.
    """
    series = {t: clean_series(rows) for t, rows in prices.items()}
    bench = clean_series(benchmark)

    # Per cohort: the priceable top-N basket, its union calendar, and its
    # rebalance bar (last union date strictly before run_date).
    plans: list[tuple[dt.date, list[str], list[dt.date], dt.date | None]] = []
    for run_date, members in _cohorts(entries):
        basket = [
            t
            for t in members[:top_n]
            if t in series and last_before(series[t], run_date) is not None
        ]
        if basket:
            union = sorted(set().union(*(set(series[t][0]) for t in basket)))
            entry_date = union[bisect_left(union, run_date) - 1]
        else:
            union, entry_date = [], None
        plans.append((run_date, basket, union, entry_date))

    nav = 1.0
    points: list[tuple[dt.date, float]] = []
    for i, (run_date, basket, union, entry_date) in enumerate(plans):
        if not basket:
            continue  # unpriceable basket: NAV carries flat until next rebalance
        assert entry_date is not None
        # Segment end: the next cohort's rebalance bar; if the next basket is
        # unpriceable, mark the position at our own last bar before that run
        # (the NAV then sits flat); the final segment holds to the end of data.
        if i + 1 < len(plans):
            next_run, next_basket, _, next_entry = plans[i + 1]
            if next_basket:
                seg_end = max(next_entry, entry_date)  # type: ignore[type-var]
            else:
                j = bisect_left(union, next_run) - 1
                seg_end = union[j] if j >= 0 else entry_date
        else:
            seg_end = union[-1]

        if not points:
            points.append((entry_date, nav))
        elif entry_date > points[-1][0]:
            points.append((entry_date, nav))  # flat carry across any gap

        # Rebalance: equal weights at each member's entry-bar price.
        share = nav / len(basket)
        values = {t: share for t in basket}
        prev = {t: last_on_or_before(series[t], entry_date)[1] for t in basket}

        grid = [d for d in union if entry_date < d <= seg_end]
        if seg_end > entry_date and (not grid or grid[-1] != seg_end):
            grid.append(seg_end)  # boundary bar may come from the next basket
        for d in grid:
            for t in basket:
                bar = last_on_or_before(series[t], d)
                price = bar[1] if bar else prev[t]
                values[t] *= price / prev[t]
                prev[t] = price
            nav = sum(values.values())
            if d > points[-1][0]:
                points.append((d, nav))

    if len(points) < 2:
        return {"nav": [], "stats": None}

    dates = [d for d, _ in points]
    navs = np.array([v for _, v in points], dtype=float)
    bench_navs = _benchmark_navs(bench, dates)
    rets = navs[1:] / navs[:-1] - 1.0
    bench_rets = bench_navs[1:] / bench_navs[:-1] - 1.0

    sharpe = performance.sharpe(rets)
    te = performance.tracking_error(rets, bench_rets)
    stats = {
        "total_return_pct": round(float(navs[-1] / navs[0] - 1.0) * 100, 2),
        "benchmark_return_pct": round(
            float(bench_navs[-1] / bench_navs[0] - 1.0) * 100, 2
        ),
        "max_drawdown_pct": round(tailrisk.max_drawdown(rets) * 100, 2),
        "sharpe": round(sharpe, 2) if sharpe is not None else None,
        "tracking_error_pct": round(te * 100, 2) if te is not None else None,
        "days": int(rets.size),
    }
    nav_out = [
        {
            "date": d.isoformat(),
            "nav": round(float(v), 4),
            "benchmark_nav": round(float(b), 4),
        }
        for d, v, b in zip(dates, navs, bench_navs, strict=True)
    ]
    return {"nav": nav_out, "stats": stats}
