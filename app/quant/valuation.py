"""Per-ticker "cheap or expensive" verdict. Pure functions, no I/O.

Built on top of ``screener.score_universe()``'s ``value_evidence`` — the
peer-relative robust z of a ticker's valuation multiples (trailing/forward
P/E, PEG, P/S, P/B, EV/EBITDA, P/FCF) against its closest peer group: its
industry when there are enough scored industry peers, falling back to its
(coarser) sector, then to the whole tracked universe, when there aren't
(see ``screener.MIN_INDUSTRY_SIZE``/``MIN_SECTOR_SIZE``). This is a
*peer-relative* verdict only: "cheap vs. peers today," not "cheap vs. its
own 10-year history." ``fundamentals_snapshots`` (migration 026,
2026-07-30) hasn't accumulated the years of point-in-time history a real
own-ticker time-series percentile would need, so this module doesn't fake
one — see ``own_history_percentile`` below, which is unused by
``compute_valuations`` until that data exists in useful depth. Overstating
what's actually measured here is the one thing this module must never do:
every row that can't be scored says why, the same "excluded always carries a
reason" ethos as ``screener.py``.

Calibration constants (module-level so they're easy to sweep/tune, same
convention as ``screener.py``):
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.quant.screener import ScreenerResult

# Robust-z thresholds for the verdict buckets. 1.4826*MAD approximates a
# normal stdev, so +-1.0 reads as "about one typical deviation from the
# sector's median cheapness" -- a defensible first cut, not a proven
# optimum. Sanity-check the resulting bucket distribution over the live
# universe before treating these as final.
UNDERVALUED_Z = 1.0
EXPENSIVE_Z = -1.0

VERDICT_UNDERVALUED = "Undervalued"
VERDICT_FAIR = "Fairly Valued"
VERDICT_EXPENSIVE = "Expensive"
VERDICT_NOT_SCORED = "Not enough data"

# Own-history lens (Phase 2, not wired into compute_valuations yet): the
# minimum number of point-in-time snapshots before a time-series percentile
# is shown at all, so a handful of days of accrual can't produce a noisy,
# overconfident second signal. ~3-4 months of trading days.
OWN_HISTORY_MIN_SNAPSHOTS = 60
# Blend weight when both lenses are available: sector_z * SECTOR_WEIGHT +
# own_z * (1 - SECTOR_WEIGHT).
SECTOR_WEIGHT = 0.6


def verdict_from_z(z: float | None) -> str:
    """Classify a peer-relative value z-score into a verdict label.

    ``z is None`` (no scored value factor) is always "Not enough data" --
    never fabricate a mid-pack verdict for a ticker with too few metrics.
    """
    if z is None or not np.isfinite(z):
        return VERDICT_NOT_SCORED
    if z >= UNDERVALUED_Z:
        return VERDICT_UNDERVALUED
    if z <= EXPENSIVE_Z:
        return VERDICT_EXPENSIVE
    return VERDICT_FAIR


def value_eligibility(metrics_used: int) -> bool:
    """Whether a ticker has enough value metrics to carry a verdict at all.

    Mirrors ``screener._MIN_METRICS_PER_FACTOR["value"] = 2`` -- kept as its
    own named check (rather than inlining ``>= 2``) so the threshold has one
    place to change and a docstring, matching how it enters
    ``ScreenerResult.value_evidence`` (already gated by the same rule inside
    ``score_universe``, so this mostly documents/re-affirms the invariant
    rather than re-deriving it).
    """
    return metrics_used >= 2


def own_history_percentile(
    current_multiple: float | None, historical_multiples: list[float]
) -> dict[str, Any] | None:
    """Percentile rank of ``current_multiple`` within its own history.

    Phase 2 building block, intentionally not called by
    ``compute_valuations`` yet: ``fundamentals_snapshots`` doesn't hold
    enough depth for a meaningful own-ticker lens (see module docstring).
    Returns ``None`` below ``OWN_HISTORY_MIN_SNAPSHOTS`` rather than a noisy
    percentile off a handful of points. The window length is always
    reported alongside the percentile so callers can disclose it honestly
    ("vs. its own N-day history") instead of implying a fixed depth.
    """
    if current_multiple is None or not np.isfinite(current_multiple):
        return None
    values = [v for v in historical_multiples if v is not None and np.isfinite(v)]
    if len(values) < OWN_HISTORY_MIN_SNAPSHOTS:
        return None
    arr = np.asarray(values, dtype=float)
    percentile = float((arr <= current_multiple).sum()) / arr.size * 100.0
    return {"percentile": round(percentile, 1), "window_size": arr.size}


def _profile(fundamentals: dict[str, dict[str, Any]], ticker: str) -> dict[str, Any]:
    return (fundamentals.get(ticker) or {}).get("profile") or {}


def compute_valuations(
    screen: ScreenerResult,
    fundamentals: dict[str, dict[str, Any]],
    last_price: dict[str, float],
    *,
    tickers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """One valuation row per universe ticker (scored or not).

    ``screen`` is a ``score_universe()`` result over the same universe
    ``fundamentals``/``last_price`` were built from. ``fundamentals`` and
    ``last_price`` supply display fields (name/sector/industry/market cap/
    price) even
    for tickers ``screen`` couldn't score at all (e.g. "no fundamentals",
    "not an equity") -- mirroring valucurve's "Not scored" cards, which
    still show the ticker and price.

    ``tickers``, when given, is the authoritative requested universe (e.g.
    the picks pipeline's convention is to drop fetch-error rows from
    ``fundamentals`` entirely before scoring -- see ``run_valuation_refresh``
    -- which would otherwise make a dead ticker silently vanish here instead
    of surfacing as "Not enough data" the way a genuinely-tracked-but-broken
    name should).
    """
    universe = sorted(
        set(tickers or [])
        | set(screen.value_evidence)
        | set(screen.excluded)
        | set(fundamentals)
    )
    out: list[dict[str, Any]] = []
    for ticker in universe:
        profile = _profile(fundamentals, ticker)
        base = {
            "ticker": ticker,
            "name": profile.get("name"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "market_cap": profile.get("market_cap"),
            "last_price": last_price.get(ticker),
        }
        ve = screen.value_evidence.get(ticker)
        if ve is None:
            out.append(
                {
                    **base,
                    "verdict": VERDICT_NOT_SCORED,
                    "sector_z": None,
                    "metrics_used": 0,
                    "sector_comparison": None,
                    "evidence": None,
                    "not_scored_reason": screen.excluded.get(
                        ticker,
                        "no fundamentals" if ticker not in fundamentals else "not scored",
                    ),
                }
            )
            continue
        z = ve["value_z"]
        industry = ve.get("industry") or base["industry"]
        out.append(
            {
                **base,
                "sector": ve["sector"] or base["sector"],
                "industry": industry,
                "verdict": verdict_from_z(z),
                "sector_z": z,
                "metrics_used": ve["metrics_used"],
                "sector_comparison": ve["sector_comparison"],
                "evidence": {"metrics": ve["metrics"], "industry": industry},
                "not_scored_reason": None,
            }
        )
    return out
