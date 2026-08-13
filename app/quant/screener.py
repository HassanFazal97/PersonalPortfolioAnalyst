"""Cross-sectional factor screen over the picks universe. Pure numpy, no I/O.

Consumes the stored ``ticker_fundamentals`` payload shape
(``app/tools/fundamentals.py::_normalize_fundamentals``) and stored adjusted
closes (``{date, adj_close}`` rows), and produces a ranked composite plus the
day's notable movers. Every number the LLM stage is allowed to cite comes out
of here in each row's ``evidence`` dict.

Methodology (constants below are the calibration surface):

- **Robust peer-relative z-scores, industry-first.** Each metric is
  normalized within the tightest peer group with enough scored members:
  industry (``MIN_INDUSTRY_SIZE``) -> sector (``MIN_SECTOR_SIZE``) ->
  the whole universe, as ``clip((x - median) / (1.4826 * MAD + eps), -3, 3)``
  — median and MAD, not mean and stdev, because valuation ratios are
  fat-tailed and a single 400x P/E would drag a group's whole distribution.
  A ticker with no/undersized industry falls straight through to the sector
  tier; missing sector falls through to the universe tier. Signs are flipped
  so higher z always means more attractive.
- **Factors renormalize over what's available** rather than imputing missing
  data (imputation would fabricate mid-pack scores for the least-covered
  names, which skews TSX). A name must have the value factor and at least
  ``MIN_OTHER_FACTORS`` others to be ranked at all.
- **Momentum skips the most recent month** (12-1 construction) — the last
  month carries short-term reversal, the classical result this guards.
- **Analyst upside is coverage-shrunk** (``z * min(1, count/8)``) so a
  two-analyst target can't dominate a rank.

Exclusions always carry a reason (the ``ReturnsMatrix`` convention): a name
silently missing from the output is a bug, a name excluded with a reason is a
decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

# --- Calibration constants (module-level so a sweep script can patch them) ---

FACTOR_WEIGHTS: dict[str, float] = {
    "value": 0.30,
    "quality": 0.20,
    "momentum": 0.20,
    "growth": 0.10,
    "analyst_upside": 0.10,
    "low_risk": 0.10,
}
# A name needs the value factor plus at least this many others to be ranked.
MIN_OTHER_FACTORS = 3
# Industry groups smaller than this fall back to the sector tier. Lower than
# MIN_SECTOR_SIZE on purpose: industries are much narrower than sectors (the
# tracked universe spans ~150 industry labels vs. ~11 sectors), so reusing
# the sector threshold here would almost never let the industry tier fire.
MIN_INDUSTRY_SIZE = 5
# Sector groups smaller than this fall back to universe-wide normalization.
MIN_SECTOR_SIZE = 8
# Robust-z winsorization bound.
Z_CLIP = 3.0
# Current-ratio attractiveness saturates: hoarding cash isn't linearly better.
CURRENT_RATIO_Z_CAP = 1.5
# Analyst factor: minimum coverage to count, full weight at this many analysts.
ANALYST_MIN_COUNT = 4
ANALYST_FULL_COVERAGE = 8

# Eligibility gates.
MIN_PRICE_BARS = 200
MAX_BAR_AGE_DAYS = 5
MAX_FUNDAMENTALS_AGE_HOURS = 48.0

# Movers: last daily log return vs its own trailing distribution.
MOVER_Z_WINDOW = 60
MOVER_Z_THRESHOLD = 2.5

# Trading-day offsets for momentum construction.
_ONE_MONTH = 21
_SIX_MONTHS = 126
_TWELVE_MONTHS = 252

_EPS = 1e-9

# (payload_section, key, sign) — sign +1 means bigger raw value is more
# attractive, -1 the opposite. positive_only guards ratios that are
# meaningless when non-positive (negative EBITDA, negative book value).
_VALUE_METRICS = [
    ("valuation", "trailing_pe", -1, True),
    ("valuation", "forward_pe", -1, True),
    ("valuation", "price_to_sales", -1, True),
    ("valuation", "price_to_book", -1, True),
    ("valuation", "ev_to_ebitda", -1, True),
    ("valuation", "price_to_fcf", -1, True),
    ("valuation", "peg", -1, True),
]
_QUALITY_METRICS = [
    ("profitability", "roe_pct", +1, False),
    ("profitability", "gross_margin_pct", +1, False),
    ("profitability", "operating_margin_pct", +1, False),
    ("profitability", "net_margin_pct", +1, False),
    ("financial_health", "debt_to_equity", -1, True),
    ("financial_health", "current_ratio", +1, True),
]
_GROWTH_METRICS = [
    ("growth", "revenue_growth_pct", +1, False),
    ("growth", "earnings_growth_pct", +1, False),
]

_MIN_METRICS_PER_FACTOR = {"value": 2, "quality": 2, "growth": 1}


@dataclass
class ScreenerResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    movers: list[dict[str, Any]] = field(default_factory=list)
    excluded: dict[str, str] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    # Value factor + evidence for every eligible ticker with a scored value
    # factor (>= _MIN_METRICS_PER_FACTOR["value"] metrics resolved),
    # independent of whether the ticker clears the composite's *other*-factor
    # gates. A valuation verdict (app/quant/valuation.py) shouldn't require
    # momentum/analyst/quality coverage the way the picks composite does —
    # a recently-listed name can be cheap without having 12 months of
    # momentum history. Superset of the tickers in ``rows``.
    value_evidence: dict[str, dict[str, Any]] = field(default_factory=dict)


def robust_z(values: np.ndarray) -> np.ndarray:
    """NaN-aware winsorized robust z over one metric's cross-section.

    ``1.4826 * MAD`` estimates the stdev of a normal distribution, so the z
    scale stays comparable to a classical z while ignoring fat tails. A
    degenerate cross-section (MAD ~ 0) returns zeros rather than exploding.
    """
    out = np.full(values.shape, np.nan)
    mask = np.isfinite(values)
    if mask.sum() < 2:
        return out
    med = np.median(values[mask])
    mad = np.median(np.abs(values[mask] - med))
    scale = 1.4826 * mad
    if scale < _EPS:
        out[mask] = 0.0
        return out
    out[mask] = np.clip((values[mask] - med) / (scale + _EPS), -Z_CLIP, Z_CLIP)
    return out


def _group_z_and_median(
    values: np.ndarray, groups: list[str | None], min_size: int
) -> tuple[np.ndarray, np.ndarray]:
    """Robust z and median within each group that has >= min_size scored
    members. Positions whose own group is missing or undersized get NaN in
    both outputs — the caller decides what to fall back to next. A None/""
    group never enters a bucket, so it's indistinguishable from "undersized"
    and falls through the same way, with no special-casing needed."""
    z = np.full(values.shape, np.nan)
    med = np.full(values.shape, np.nan)
    by_group: dict[str, list[int]] = {}
    for i, g in enumerate(groups):
        if g:
            by_group.setdefault(g, []).append(i)
    for _group, idxs in by_group.items():
        idx = np.array(idxs)
        vals = values[idx]
        if np.isfinite(vals).sum() >= min_size:
            z[idx] = robust_z(vals)
            med[idx] = float(np.median(vals[np.isfinite(vals)]))
    return z, med


def _peer_relative_z(
    values: np.ndarray, industries: list[str | None], sectors: list[str | None]
) -> tuple[np.ndarray, np.ndarray]:
    """Robust z against the finest peer group with enough scored members:
    industry -> sector -> the whole universe. Returns ``(z, tier)`` where
    ``tier`` is a per-row array of "industry"/"sector"/"universe" naming
    which level actually fired."""
    industry_z, _ = _group_z_and_median(values, industries, MIN_INDUSTRY_SIZE)
    sector_z, _ = _group_z_and_median(values, sectors, MIN_SECTOR_SIZE)
    universe_z = robust_z(values)
    z = np.where(
        np.isfinite(industry_z), industry_z, np.where(np.isfinite(sector_z), sector_z, universe_z)
    )
    tier = np.where(
        np.isfinite(industry_z), "industry", np.where(np.isfinite(sector_z), "sector", "universe")
    )
    return z, tier


def _peer_medians(
    values: np.ndarray, industries: list[str | None], sectors: list[str | None]
) -> np.ndarray:
    """Per-row median of the row's own peer group (industry, falling back to
    sector, falling back to the universe) — the comparison number shown as
    evidence. Sector-tier medians come from the *full* sector bucket, not
    just the industry tier's leftovers, so a sector-tier fallback still
    compares against a legitimate full cross-section."""
    _, industry_med = _group_z_and_median(values, industries, MIN_INDUSTRY_SIZE)
    _, sector_med = _group_z_and_median(values, sectors, MIN_SECTOR_SIZE)
    finite = values[np.isfinite(values)]
    universe_med = float(np.median(finite)) if finite.size else np.nan
    return np.where(
        np.isfinite(industry_med),
        industry_med,
        np.where(np.isfinite(sector_med), sector_med, universe_med),
    )


def _get(payload: dict[str, Any], section: str, key: str) -> float | None:
    v = (payload.get(section) or {}).get(key)
    return float(v) if isinstance(v, (int, float)) and np.isfinite(v) else None


def _log_returns(closes: list[float]) -> np.ndarray:
    arr = np.asarray(closes, dtype=float)
    if arr.size < 2:
        return np.array([])
    return np.diff(np.log(arr))


def daily_return_zscore(closes: list[dict[str, Any]], window: int = MOVER_Z_WINDOW) -> float | None:
    """Last daily log return as a z-score against its own trailing ``window``
    returns (exclusive of the last). Stateless twin of the ZScore detector —
    the streaming class carries per-ticker state this cross-section doesn't need."""
    rets = _log_returns([r["adj_close"] for r in closes])
    if rets.size < window + 1:
        return None
    hist = rets[-(window + 1) : -1]
    sd = float(np.std(hist, ddof=1))
    if sd < _EPS:
        return None
    return float((rets[-1] - float(np.mean(hist))) / sd)


def _momentum_12_1(closes: list[float]) -> float | None:
    if len(closes) < _TWELVE_MONTHS or closes[-_TWELVE_MONTHS] <= 0:
        return None
    return closes[-_ONE_MONTH] / closes[-_TWELVE_MONTHS] - 1.0

def _return_6m(closes: list[float]) -> float | None:
    if len(closes) < _SIX_MONTHS or closes[-_SIX_MONTHS] <= 0:
        return None
    return closes[-1] / closes[-_SIX_MONTHS] - 1.0


def _annualized_vol(closes: list[float]) -> float | None:
    rets = _log_returns(closes[-(_TWELVE_MONTHS + 1) :])
    if rets.size < 60:
        return None
    return float(np.std(rets, ddof=1) * np.sqrt(252))


def _eligibility(
    ticker: str,
    payload: dict[str, Any] | None,
    bars: list[dict[str, Any]] | None,
    *,
    as_of: date,
    fundamentals_age_hours: float | None,
) -> str | None:
    """Reason this ticker can't be scored, or None if eligible."""
    if payload is None:
        return "no fundamentals"
    if fundamentals_age_hours is not None and fundamentals_age_hours > MAX_FUNDAMENTALS_AGE_HOURS:
        return "stale fundamentals"
    if payload.get("quote_type") != "EQUITY":
        return f"not an equity ({payload.get('quote_type')})"
    if _get(payload, "profile", "market_cap") is None:
        return "no market cap"
    if not bars or len(bars) < MIN_PRICE_BARS:
        return "insufficient price history"
    latest = date.fromisoformat(bars[-1]["date"])
    if (as_of - latest).days > MAX_BAR_AGE_DAYS:
        return "stale prices"
    return None


def score_universe(
    fundamentals: dict[str, dict[str, Any]],
    closes: dict[str, list[dict[str, Any]]],
    *,
    as_of: date,
    fundamentals_age_hours: dict[str, float] | None = None,
    max_movers: int = 10,
) -> ScreenerResult:
    """Rank the universe by composite factor score and flag the day's movers.

    ``fundamentals`` maps ticker -> stored payload (error rows should simply
    be absent); ``fundamentals_age_hours`` optionally maps ticker -> age of
    that row for the freshness gate. ``closes`` maps ticker -> stored
    adjusted-close rows (oldest first).
    """
    universe = sorted(set(fundamentals) | set(closes))
    ages = fundamentals_age_hours or {}

    excluded: dict[str, str] = {}
    eligible: list[str] = []
    for t in universe:
        reason = _eligibility(
            t, fundamentals.get(t), closes.get(t), as_of=as_of,
            fundamentals_age_hours=ages.get(t),
        )
        if reason:
            excluded[t] = reason
        else:
            eligible.append(t)

    n = len(eligible)
    result = ScreenerResult(excluded=excluded)
    result.coverage = {
        "universe": len(universe),
        "eligible": n,
        "excluded": len(excluded),
        "as_of": as_of.isoformat(),
    }
    if n == 0:
        return result

    payloads = [fundamentals[t] for t in eligible]
    close_vals = [[r["adj_close"] for r in closes[t]] for t in eligible]
    sectors = [(p.get("profile") or {}).get("sector") for p in payloads]
    industries = [(p.get("profile") or {}).get("industry") for p in payloads]

    # ---- collect raw metric columns -------------------------------------
    raw: dict[str, np.ndarray] = {}

    def column(section: str, key: str, positive_only: bool) -> np.ndarray:
        col = np.full(n, np.nan)
        for i, p in enumerate(payloads):
            v = _get(p, section, key)
            if v is not None and (not positive_only or v > 0):
                col[i] = v
        return col

    for section, key, _sign, pos in [*_VALUE_METRICS, *_QUALITY_METRICS, *_GROWTH_METRICS]:
        raw[key] = column(section, key, pos)

    last_price = np.array([c[-1] for c in close_vals])
    raw["momentum_12_1"] = np.array(
        [m if (m := _momentum_12_1(c)) is not None else np.nan for c in close_vals]
    )
    raw["return_6m"] = np.array(
        [m if (m := _return_6m(c)) is not None else np.nan for c in close_vals]
    )
    raw["volatility_252d"] = np.array(
        [m if (m := _annualized_vol(c)) is not None else np.nan for c in close_vals]
    )
    raw["short_pct_of_float"] = column("price_action", "short_pct_of_float", False)
    beta = column("price_action", "beta", False)
    raw["beta_distance"] = np.abs(beta - 1.0)

    target = column("price_action", "analyst_target", True)
    count = column("price_action", "analyst_count", True)
    upside = np.full(n, np.nan)
    ok = np.isfinite(target) & (last_price > 0) & np.isfinite(count) & (count >= ANALYST_MIN_COUNT)
    upside[ok] = target[ok] / last_price[ok] - 1.0
    raw["analyst_upside"] = upside

    # ---- normalize into factor z's --------------------------------------
    def stacked_mean(zs: np.ndarray, min_available: int = 1) -> np.ndarray:
        """Row-wise mean over finite entries; NaN below ``min_available``.
        (nanmean warns on all-NaN columns, so the mask is explicit.)"""
        finite = np.isfinite(zs)
        counts = finite.sum(axis=0)
        sums = np.where(finite, zs, 0.0).sum(axis=0)
        out = np.divide(
            sums, counts, out=np.full(zs.shape[1], np.nan), where=counts > 0
        )
        out[counts < min_available] = np.nan
        return out

    def metric_z(key: str, sign: int, *, sector_relative: bool) -> np.ndarray:
        z = (
            _peer_relative_z(raw[key], industries, sectors)[0]
            if sector_relative
            else robust_z(raw[key])
        )
        z = z * sign
        if key == "current_ratio":
            z = np.minimum(z, CURRENT_RATIO_Z_CAP)
        return z

    def factor_from(metrics: list[tuple], name: str, *, sector_relative: bool) -> np.ndarray:
        zs = np.vstack([metric_z(k, s, sector_relative=sector_relative) for _, k, s, _ in metrics])
        return stacked_mean(zs, _MIN_METRICS_PER_FACTOR[name])

    factors: dict[str, np.ndarray] = {
        "value": factor_from(_VALUE_METRICS, "value", sector_relative=True),
        "quality": factor_from(_QUALITY_METRICS, "quality", sector_relative=True),
        "growth": factor_from(_GROWTH_METRICS, "growth", sector_relative=True),
    }

    factors["momentum"] = stacked_mean(
        np.vstack([robust_z(raw["momentum_12_1"]), robust_z(raw["return_6m"])])
    )

    analyst_z = robust_z(raw["analyst_upside"])
    shrink = np.minimum(1.0, np.where(np.isfinite(count), count, 0) / ANALYST_FULL_COVERAGE)
    factors["analyst_upside"] = analyst_z * shrink

    factors["low_risk"] = stacked_mean(
        np.vstack(
            [
                -robust_z(raw["volatility_252d"]),
                -robust_z(raw["short_pct_of_float"]),
                -robust_z(raw["beta_distance"]),
            ]
        )
    )

    # ---- composite -------------------------------------------------------
    names = list(FACTOR_WEIGHTS)
    fmat = np.vstack([factors[f] for f in names])
    weights = np.array([FACTOR_WEIGHTS[f] for f in names])[:, None] * np.ones((1, n))
    weights[~np.isfinite(fmat)] = 0.0
    wsum = weights.sum(axis=0)
    composite = np.where(
        wsum > _EPS,
        np.nansum(np.where(np.isfinite(fmat), fmat, 0.0) * weights, axis=0) / np.maximum(wsum, _EPS),
        np.nan,
    )

    value_present = np.isfinite(factors["value"])
    others_present = np.vstack(
        [np.isfinite(factors[f]) for f in names if f != "value"]
    ).sum(axis=0)
    rankable = value_present & (others_present >= MIN_OTHER_FACTORS)

    # ---- evidence: peer medians of the raw valuation/quality metrics -----
    medians = {
        key: _peer_medians(raw[key], industries, sectors)
        for _, key, _s, _p in [*_VALUE_METRICS, *_QUALITY_METRICS, *_GROWTH_METRICS]
    }

    def _r(v: Any, nd: int = 4) -> float | None:
        return round(float(v), nd) if v is not None and np.isfinite(v) else None

    # ---- value-only evidence, independent of the composite's rankable gate
    value_metric_keys = [key for _, key, _s, _p in _VALUE_METRICS]
    industry_counts: dict[str, int] = {}
    for ind in industries:
        if ind:
            industry_counts[ind] = industry_counts.get(ind, 0) + 1
    sector_counts: dict[str, int] = {}
    for s in sectors:
        if s:
            sector_counts[s] = sector_counts.get(s, 0) + 1

    def _comparison_tier(i: int) -> str:
        # Approximate: whether this ticker's *industry*/*sector* had enough
        # scored peers overall to normalize against, vs. falling back to a
        # broader tier (mirrors MIN_INDUSTRY_SIZE/MIN_SECTOR_SIZE, but per
        # metric the real fallback can vary slightly — this is the
        # disclosed, honest approximation, not a per-metric audit).
        ind, sec = industries[i], sectors[i]
        if ind and industry_counts.get(ind, 0) >= MIN_INDUSTRY_SIZE:
            return "industry"
        if sec and sector_counts.get(sec, 0) >= MIN_SECTOR_SIZE:
            return "sector"
        return "universe (too small)"

    for i, t in enumerate(eligible):
        vz = factors["value"][i]
        if not np.isfinite(vz):
            continue
        metrics = {
            key: {"value": _r(raw[key][i]), "sector_median": _r(medians[key][i])}
            for key in value_metric_keys
            if np.isfinite(raw[key][i])
        }
        result.value_evidence[t] = {
            "sector": sectors[i],
            "industry": industries[i],
            "value_z": _r(vz),
            "metrics_used": len(metrics),
            "metrics": metrics,
            "sector_comparison": _comparison_tier(i),
        }

    rows: list[dict[str, Any]] = []
    for i, t in enumerate(eligible):
        if not rankable[i]:
            excluded[t] = "insufficient factor coverage"
            continue
        p = payloads[i]
        evidence_metrics = {
            key: {"value": _r(raw[key][i]), "sector_median": _r(medians[key][i])}
            for _, key, _s, _p in [*_VALUE_METRICS, *_QUALITY_METRICS, *_GROWTH_METRICS]
            if np.isfinite(raw[key][i])
        }
        pa = p.get("price_action") or {}
        rows.append(
            {
                "ticker": t,
                "name": (p.get("profile") or {}).get("name"),
                "sector": sectors[i],
                "industry": industries[i],
                "last_price": _r(last_price[i]),
                "factors": {f: _r(factors[f][i]) for f in names},
                "composite": _r(composite[i]),
                "evidence": {
                    "metrics": evidence_metrics,
                    "momentum_12_1_pct": _r(raw["momentum_12_1"][i] * 100, 2),
                    "return_6m_pct": _r(raw["return_6m"][i] * 100, 2),
                    "volatility_252d_pct": _r(raw["volatility_252d"][i] * 100, 2),
                    "beta": _r(beta[i], 2),
                    "short_pct_of_float": _r(raw["short_pct_of_float"][i], 2),
                    "analyst_target": _r(target[i], 2),
                    "analyst_count": int(count[i]) if np.isfinite(count[i]) else None,
                    "analyst_upside_pct": _r(raw["analyst_upside"][i] * 100, 2),
                    "pct_from_52w_high": _r(
                        (last_price[i] / pa["high_52w"] - 1) * 100, 2
                    )
                    if isinstance(pa.get("high_52w"), (int, float)) and pa["high_52w"] > 0
                    else None,
                },
            }
        )

    rows.sort(key=lambda r: r["composite"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    # ---- movers ----------------------------------------------------------
    movers: list[dict[str, Any]] = []
    for i, t in enumerate(eligible):
        z = daily_return_zscore(closes[t])
        if z is None or abs(z) < MOVER_Z_THRESHOLD:
            continue
        c = close_vals[i]
        day_pct = (c[-1] / c[-2] - 1) * 100 if len(c) >= 2 and c[-2] > 0 else None
        movers.append(
            {
                "ticker": t,
                "name": (payloads[i].get("profile") or {}).get("name"),
                "day_return_pct": _r(day_pct, 2),
                "zscore": _r(z, 2),
                "direction": "up" if z > 0 else "down",
            }
        )
    movers.sort(key=lambda m: abs(m["zscore"]), reverse=True)
    result.movers = movers[:max_movers]

    result.rows = rows
    result.coverage["ranked"] = len(rows)
    result.coverage["excluded"] = len(excluded)
    return result
