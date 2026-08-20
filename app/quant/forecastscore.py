"""Resolution and calibration scoring for the forecast ledger.

Every row in ``forecasts`` (migration 035) is a claim some pipeline published
about the future. This module decides — from stored adjusted closes alone —
whether each claim came true, and aggregates the results into calibration
stats ("when the analyst says high confidence, how often is it right?").

Measurement conventions are identical to ``trackrecord.py`` (its helpers are
imported, not copied), because they defend the same hindsight traps:

- **Entry bar = last close strictly BEFORE as_of_date.** Claims publish with
  the morning digest / pre-market picks; using the issue date's own close
  would grant the claim a day of hindsight.
- **Exit bar = last close on or before due_date.**
- **A claim resolves only once fully elapsed against the benchmark
  calendar** (latest benchmark bar >= due_date); before that the resolver
  returns None and the row stays open.
- **Benchmark over the identical span** for relative claims.

Scoring:

- ``direction``: up = positive return, down = negative, flat = within the
  per-horizon band. A stated magnitude tightens the rule (an "up 5%+" claim
  only hits at +5%).
- ``relative_performance``: return vs the benchmark's same-span return.
- ``risk_warning``: hit when the max drawdown from the entry bar within the
  horizon exceeds the per-horizon band — a warning is "right" when the risk
  materialized.
- ``event`` / ``volatility``: not resolvable from prices (yet); the ledger
  job expires them at due_date, keeping the rows for the dataset but out of
  every score.

``probability`` is never model-asserted: extracted claims carry a verbal
confidence mapped through ``CONFIDENCE_PRIOR_MAP`` (versioned; re-fit from
realized data later), picks rows carry the pipeline's Python-computed
confidence. Calibration is therefore reported per verbal bucket; the priors
just make Brier scores computable.

Headline stats score per claim *family* (``family_key`` groups the same claim
restated across days), mirroring trackrecord's cohort logic: a thesis repeated
in 30 digests must not count as 30 independent successes.

Pure and I/O-free: callers pass ``(date, adjusted_close)`` series; every
output is a plain dict/list of JSON-safe values.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.quant.trackrecord import clean_series, last_before, last_on_or_before

RESOLVER_VERSION = 1

ALLOWED_HORIZONS_DAYS = (7, 30, 91, 182)

# 'flat' means the absolute return stayed inside this band (pct, per horizon).
FLAT_BAND_PCT = {7: 1.0, 30: 2.0, 91: 3.5, 182: 5.0}

# A risk_warning hits when max drawdown from entry exceeds this band (pct).
DRAWDOWN_BAND_PCT = {7: 5.0, 30: 8.0, 91: 12.0, 182: 15.0}

# Versioned verbal-confidence -> prior probability map (see module docstring).
CONFIDENCE_PRIOR_VERSION = 1
CONFIDENCE_PRIOR_MAP = {
    "high": 0.75,
    "medium": 0.62,
    "low": 0.55,
    "speculative": 0.50,
}

# Claim types resolvable from daily adjusted closes alone.
RESOLVABLE_CLAIM_TYPES = frozenset(
    {"direction", "relative_performance", "risk_warning"}
)

# Defaults when the author stated no horizon: a directional call reads as
# "the coming month"; a risk warning as "the coming quarter".
DEFAULT_HORIZON_BY_TYPE = {
    "direction": 30,
    "relative_performance": 91,
    "risk_warning": 91,
    "event": 30,
    "volatility": 30,
}

MIN_BUCKET_FAMILIES = 30  # the public-exposure gate, per bucket


def snap_horizon(stated_days: int | None, claim_type: str) -> int:
    """Snap a stated horizon to the nearest allowed one (ties go longer);
    unstated horizons take the per-type default."""
    if stated_days is None or stated_days <= 0:
        return DEFAULT_HORIZON_BY_TYPE.get(claim_type, 30)
    return min(ALLOWED_HORIZONS_DAYS, key=lambda h: (abs(h - stated_days), -h))


def brier(probability: float, hit: bool) -> float:
    """Brier score of a single binary forecast: (p - outcome)^2."""
    return (float(probability) - (1.0 if hit else 0.0)) ** 2


def _max_drawdown_pct(
    series: tuple[list[dt.date], list[float]],
    entry: tuple[dt.date, float],
    end: dt.date,
) -> float | None:
    """Max peak-to-trough decline (negative pct) from the entry bar through
    ``end``, peak seeded at the entry price. None when no bar follows entry."""
    dates, prices = series
    peak = entry[1]
    worst = 0.0
    seen = False
    for d, p in zip(dates, prices):
        if d <= entry[0] or d > end:
            continue
        seen = True
        peak = max(peak, p)
        worst = min(worst, p / peak - 1.0)
    return worst * 100.0 if seen else None


def resolve_forecast(
    claim: dict[str, Any],
    prices: dict[str, list[tuple[dt.date, float]]],
    benchmark: list[tuple[dt.date, float]],
) -> dict[str, Any] | None:
    """Resolve one open claim against stored prices, or None if not yet
    resolvable (horizon not fully elapsed / claim needs a series we lack).

    ``claim`` needs: claim_type, primary_ticker, direction, horizon_days,
    as_of_date, due_date, probability (optional), magnitude_min_pct
    (optional). Returns {"outcome", "realized_value", "benchmark_value",
    "brier", "resolution_detail"} with pct values rounded to 4 decimals.
    """
    claim_type = claim["claim_type"]
    if claim_type not in RESOLVABLE_CLAIM_TYPES:
        return None

    as_of: dt.date = claim["as_of_date"]
    due: dt.date = claim["due_date"]
    horizon = int(claim["horizon_days"])

    bench = clean_series(benchmark)
    if not bench[0] or bench[0][-1] < due:
        return None  # horizon not fully elapsed against the benchmark calendar

    ticker = claim.get("primary_ticker")
    series = clean_series(prices.get(ticker)) if ticker else bench

    entry = last_before(series, as_of)
    exit_bar = last_on_or_before(series, due)

    b_entry = last_before(bench, as_of)
    b_exit = last_on_or_before(bench, due)
    bench_ret_pct: float | None = None
    if b_entry is not None and b_exit is not None and b_exit[0] > b_entry[0]:
        bench_ret_pct = (b_exit[1] / b_entry[1] - 1.0) * 100.0

    def _result(
        outcome: str,
        realized: float | None,
        detail_extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        p = claim.get("probability")
        b = (
            round(brier(float(p), outcome == "hit"), 4)
            if p is not None and outcome in ("hit", "miss")
            else None
        )
        detail: dict[str, Any] = {
            "method": claim_type,
            "entry_bar_date": entry[0].isoformat() if entry else None,
            "entry_price": round(entry[1], 6) if entry else None,
            "exit_bar_date": exit_bar[0].isoformat() if exit_bar else None,
            "exit_price": round(exit_bar[1], 6) if exit_bar else None,
        }
        if detail_extra:
            detail.update(detail_extra)
        return {
            "outcome": outcome,
            "realized_value": round(realized, 4) if realized is not None else None,
            "benchmark_value": (
                round(bench_ret_pct, 4) if bench_ret_pct is not None else None
            ),
            "brier": b,
            "resolution_detail": detail,
        }

    # No measurable span for the subject series -> indeterminate (visible,
    # never silently dropped).
    if entry is None or exit_bar is None or exit_bar[0] <= entry[0]:
        return _result("indeterminate", None, {"reason": "no_measurable_span"})

    ret_pct = (exit_bar[1] / entry[1] - 1.0) * 100.0

    if claim_type == "direction":
        direction = claim.get("direction")
        band = FLAT_BAND_PCT.get(horizon, FLAT_BAND_PCT[30])
        magnitude = claim.get("magnitude_min_pct")
        if direction == "up":
            hit = ret_pct >= float(magnitude) if magnitude is not None else ret_pct > 0
        elif direction == "down":
            hit = (
                ret_pct <= -abs(float(magnitude))
                if magnitude is not None
                else ret_pct < 0
            )
        elif direction == "flat":
            hit = abs(ret_pct) < band
        else:
            return _result("indeterminate", ret_pct, {"reason": "no_direction"})
        return _result("hit" if hit else "miss", ret_pct)

    if claim_type == "relative_performance":
        if bench_ret_pct is None:
            return _result("indeterminate", ret_pct, {"reason": "no_benchmark_span"})
        direction = claim.get("direction") or "outperform"
        if direction == "underperform":
            hit = ret_pct < bench_ret_pct
        else:
            hit = ret_pct > bench_ret_pct
        return _result("hit" if hit else "miss", ret_pct)

    # risk_warning: did the warned-about decline materialize?
    band = DRAWDOWN_BAND_PCT.get(horizon, DRAWDOWN_BAND_PCT[91])
    magnitude = claim.get("magnitude_min_pct")
    threshold = abs(float(magnitude)) if magnitude is not None else band
    dd_pct = _max_drawdown_pct(series, entry, due)
    if dd_pct is None:
        return _result("indeterminate", None, {"reason": "no_measurable_span"})
    hit = dd_pct <= -threshold
    return _result(
        "hit" if hit else "miss", dd_pct, {"drawdown_threshold_pct": threshold}
    )


def _family_observations(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse resolved rows into one observation per claim family: hit is
    the family's mean hit fraction, brier/probability its member means."""
    by_family: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_family.setdefault(r["family_key"], []).append(r)
    out = []
    for family_key, members in by_family.items():
        hits = [1.0 if m["outcome"] == "hit" else 0.0 for m in members]
        briers = [float(m["brier"]) for m in members if m.get("brier") is not None]
        probs = [
            float(m["probability"])
            for m in members
            if m.get("probability") is not None
        ]
        first = members[0]
        out.append(
            {
                "family_key": family_key,
                "source": first["source"],
                "claim_type": first["claim_type"],
                "confidence_verbal": first["confidence_verbal"],
                "hit_fraction": sum(hits) / len(hits),
                "avg_brier": sum(briers) / len(briers) if briers else None,
                "avg_probability": sum(probs) / len(probs) if probs else None,
                "rows": len(members),
            }
        )
    return out


def _bucket_stats(
    fams: list[dict[str, Any]], *, min_families: int
) -> dict[str, Any]:
    n = len(fams)
    if n < min_families:
        return {"families": n, "rows": sum(f["rows"] for f in fams), "gated": True}
    briers = [f["avg_brier"] for f in fams if f["avg_brier"] is not None]
    probs = [f["avg_probability"] for f in fams if f["avg_probability"] is not None]
    return {
        "families": n,
        "rows": sum(f["rows"] for f in fams),
        "gated": False,
        "hit_rate_pct": round(100.0 * sum(f["hit_fraction"] for f in fams) / n, 2),
        "avg_brier": round(sum(briers) / len(briers), 4) if briers else None,
        "avg_stated_probability_pct": (
            round(100.0 * sum(probs) / len(probs), 2) if probs else None
        ),
    }


def calibration_summary(
    rows: list[dict[str, Any]], *, min_families: int = MIN_BUCKET_FAMILIES
) -> dict[str, Any]:
    """Calibration stats over resolved hit/miss rows.

    ``rows`` need: family_key, source, claim_type, confidence_verbal,
    outcome ('hit'/'miss'), brier (optional), probability (optional). The
    unit of account is the claim family. Buckets under ``min_families``
    report counts only (``gated: true``) — small samples read as noise.
    """
    scored = [r for r in rows if r.get("outcome") in ("hit", "miss")]
    fams = _family_observations(scored)

    by_bucket: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    by_confidence: dict[str, list[dict[str, Any]]] = {}
    for f in fams:
        by_bucket.setdefault(
            (f["source"], f["claim_type"], f["confidence_verbal"]), []
        ).append(f)
        by_confidence.setdefault(f["confidence_verbal"], []).append(f)

    buckets = [
        {
            "source": source,
            "claim_type": claim_type,
            "confidence_verbal": confidence,
            **_bucket_stats(fams_b, min_families=min_families),
        }
        for (source, claim_type, confidence), fams_b in sorted(by_bucket.items())
    ]
    # The calibration curve: stated probability vs observed hit rate per
    # verbal bucket, across all sources/types.
    calibration_points = [
        {"confidence_verbal": confidence, **_bucket_stats(fams_c, min_families=min_families)}
        for confidence, fams_c in sorted(by_confidence.items())
    ]
    return {
        "resolver_version": RESOLVER_VERSION,
        "confidence_prior_version": CONFIDENCE_PRIOR_VERSION,
        "min_families": min_families,
        "overall": _bucket_stats(fams, min_families=1) if fams else None,
        "buckets": buckets,
        "calibration_points": calibration_points,
    }
