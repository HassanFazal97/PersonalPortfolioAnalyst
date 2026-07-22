"""Portfolio-level risk tools: analyze_portfolio_risk + estimate_downside_risk.

The scalar sibling ``risk.get_portfolio_risk`` answers per-holding questions
(this stock's beta/vol). These tools answer the questions a single stock can't:
how the holdings behave *jointly* (analyze_portfolio_risk) and how much the
book could lose (estimate_downside_risk).

All numbers are precomputed in ``app/quant/`` (pure numpy, unit-tested against
closed-form identities). The model only narrates them. Framing is descriptive
— it reports the risk the portfolio *has*, never a trade to make.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.quant import returns as qreturns
from app.quant import tailrisk
from app.quant.covariance import ledoit_wolf
from app.quant.riskdecomp import decompose
from app.tools import market, portfolio
from app.tools.tickers import normalize_tickers

# ~2 calendar years so the covariance has ~500 daily observations — enough for
# a stable estimate without over-weighting stale regime data.
HISTORY_DAYS = 730
# Bound the fan-out of live history fetches; beyond this the largest positions
# win (they dominate the risk anyway).
MAX_TICKERS = 25
_FETCH_CONCURRENCY = 4
# How many correlated pairs / risk drivers to surface in the narration payload.
_TOP_N = 5
# Benchmark for portfolio beta / scenario stress. US index; converted to CAD in
# the returns builder so beta is currency-consistent with the CAD book.
BENCHMARK_TICKER = "^GSPC"

# Beta-scaled market-shock scenarios. Stated as benchmark (S&P 500, in CAD
# terms) returns; portfolio impact = beta × shock. Sized to real historical
# drawdowns but framed as hypothetical scenarios, not predictions.
SCENARIOS: list[dict[str, Any]] = [
    {"name": "Market -10% correction", "benchmark_return": -0.10},
    {"name": "Severe bear market -20%", "benchmark_return": -0.20},
    {"name": "2020-style crash -34%", "benchmark_return": -0.34},
]

VAR_CONFIDENCES = (0.95, 0.99)


@dataclass
class _Loaded:
    """Shared result of fetching + building the returns matrix for a portfolio."""

    rm: qreturns.ReturnsMatrix
    weights: np.ndarray
    mv_by_ticker: dict[str, float]
    dropped_for_size: list[str]
    note: str | None = None  # set when there's nothing analyzable


async def _load_portfolio_returns(
    payload: dict[str, Any], ctx: Any, *, with_benchmark: bool
) -> _Loaded:
    """Fetch adjusted closes for the (largest) holdings + FX (+ benchmark) and
    build the CAD returns matrix. Shared by both portfolio-risk tools."""
    if ctx is None or getattr(ctx, "repo", None) is None:
        raise RuntimeError("portfolio risk tools require database access")

    pf = await portfolio.get_portfolio({}, ctx)
    positions = pf.get("positions") or []
    if not positions:
        return _Loaded(None, np.empty(0), {}, [], note="No positions on record.")

    requested = payload.get("tickers")
    if requested:
        wanted = set(normalize_tickers(requested))
        positions = [p for p in positions if p["ticker"] in wanted]
        if not positions:
            return _Loaded(
                None, np.empty(0), {}, [],
                note="None of the requested tickers are in the portfolio.",
            )

    usdcad = (pf.get("totals") or {}).get("usdcad_rate")

    mv_by_ticker: dict[str, float] = {}
    currency_by_ticker: dict[str, str] = {}
    for p in positions:
        mv = p.get("market_value")
        if mv is None:
            continue
        currency = (p.get("currency") or "CAD").upper()
        mv_cad = portfolio._to_cad(mv, currency, usdcad)
        if mv_cad is None:
            continue
        t = p["ticker"]
        mv_by_ticker[t] = mv_by_ticker.get(t, 0.0) + mv_cad
        currency_by_ticker.setdefault(t, currency)

    if len(mv_by_ticker) < 2:
        return _Loaded(
            None, np.empty(0), {}, [],
            note=(
                "Portfolio-level risk analytics need at least two priceable "
                "holdings; there aren't enough here."
            ),
        )

    ranked = sorted(mv_by_ticker, key=mv_by_ticker.get, reverse=True)
    tickers = ranked[:MAX_TICKERS]
    dropped_for_size = ranked[MAX_TICKERS:]

    needs_fx = any(currency_by_ticker.get(t) == "USD" for t in tickers)
    # FX is also needed to convert a USD benchmark to CAD.
    fetch_fx = needs_fx or with_benchmark
    sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

    async def _one(t: str) -> tuple[str, list[dict]]:
        async with sem:
            try:
                return t, await market.get_adjusted_closes(t, HISTORY_DAYS)
            except Exception:  # noqa: BLE001 - one bad ticker never kills the scan
                return t, []

    targets = list(tickers)
    if fetch_fx:
        targets.append(qreturns.FX_TICKER)
    if with_benchmark:
        targets.append(BENCHMARK_TICKER)
    fetched = dict(await asyncio.gather(*(_one(t) for t in targets)))

    fx_rows = fetched.get(qreturns.FX_TICKER) if fetch_fx else None
    benchmark_rows = fetched.get(BENCHMARK_TICKER) if with_benchmark else None
    closes_by_ticker = {t: fetched.get(t, []) for t in tickers}

    rm = qreturns.build_returns_matrix(
        closes_by_ticker,
        {t: currency_by_ticker[t] for t in tickers},
        fx_rows,
        benchmark_rows=benchmark_rows,
        benchmark_currency="USD",
    )
    if rm.n_assets < 2:
        note = "Not enough overlapping price history to build a covariance matrix."
        if rm.excluded:
            note += " Excluded: " + ", ".join(
                f"{t} ({why})" for t, why in rm.excluded.items()
            )
        return _Loaded(rm, np.empty(0), mv_by_ticker, dropped_for_size, note=note)

    weights = np.array([mv_by_ticker[t] for t in rm.tickers], dtype=float)
    return _Loaded(rm, weights, mv_by_ticker, dropped_for_size)


# --------------------------------------------------------------------------
# Tool 1: risk decomposition (Tier 1)
# --------------------------------------------------------------------------


async def analyze_portfolio_risk(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    loaded = await _load_portfolio_returns(payload, ctx, with_benchmark=False)
    if loaded.note:
        return {"note": loaded.note}

    est = ledoit_wolf(loaded.rm.matrix)
    d = decompose(est.cov, loaded.weights, loaded.rm.tickers)
    return _shape_decomposition(d, est, loaded)


def _shape_decomposition(d, est, loaded: _Loaded) -> dict[str, Any]:
    """Compact, narration-ready JSON. The full correlation matrix is left for
    the visual page; here we surface only what the model should talk about."""
    mv_by_ticker = loaded.mv_by_ticker
    total_mv = sum(mv_by_ticker[t] for t in d.tickers)
    order = sorted(range(len(d.tickers)), key=lambda i: d.risk_contrib_pct[i], reverse=True)

    holdings = []
    for i in order:
        t = d.tickers[i]
        weight_pct = round(mv_by_ticker[t] / total_mv * 100, 2) if total_mv else None
        holdings.append(
            {
                "ticker": t,
                "weight_pct": weight_pct,
                "risk_contribution_pct": round(d.risk_contrib_pct[i], 2),
                "annualized_vol_pct": round(d.per_asset_vol[i] * 100, 2),
                # The story metric: risk share minus capital share. Positive =
                # this holding punches above its weight in risk.
                "risk_vs_weight_gap_pct": (
                    round(d.risk_contrib_pct[i] - weight_pct, 2)
                    if weight_pct is not None
                    else None
                ),
            }
        )

    corr = d.correlation
    pairs = []
    n = len(d.tickers)
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append((abs(corr[i, j]), d.tickers[i], d.tickers[j], round(float(corr[i, j]), 2)))
    pairs.sort(reverse=True)
    top_pairs = [{"pair": [a, b], "correlation": c} for _, a, b, c in pairs[:_TOP_N]]

    div_benefit = round((d.weighted_avg_vol - d.portfolio_vol) * 100, 2)
    out: dict[str, Any] = {
        "portfolio": {
            "annualized_volatility_pct": round(d.portfolio_vol * 100, 2),
            "weighted_avg_volatility_pct": round(d.weighted_avg_vol * 100, 2),
            "diversification_ratio": round(d.diversification_ratio, 2),
            "diversification_benefit_pct": div_benefit,
            "effective_number_of_bets": round(d.effective_bets, 2),
            "holdings_analyzed": n,
            "average_correlation": round(d.avg_correlation, 2),
            "covariance_shrinkage": round(est.shrinkage, 2),
            "history_obs": loaded.rm.n_obs,
        },
        "holdings": holdings,
        "most_correlated_pairs": top_pairs,
        "interpretation": {
            "diversification_ratio": (
                "≥1; higher means correlations are cancelling more risk. "
                "1.0 means the holdings move as one."
            ),
            "effective_number_of_bets": (
                f"{round(d.effective_bets, 1)} of {n} holdings' worth of "
                "independent risk — lower than the count means concentrated bets."
            ),
            "risk_vs_weight_gap_pct": (
                "Positive = the holding contributes more risk than its share of "
                "capital (a hidden concentration)."
            ),
        },
    }
    _attach_notes(out, loaded, d.tickers)
    return out


# --------------------------------------------------------------------------
# Tool 2: downside / tail risk (Tier 2)
# --------------------------------------------------------------------------


async def estimate_downside_risk(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    loaded = await _load_portfolio_returns(payload, ctx, with_benchmark=True)
    if loaded.note:
        return {"note": loaded.note}

    rm = loaded.rm
    port = tailrisk.portfolio_return_series(rm.matrix, loaded.weights)
    total_mv = sum(loaded.mv_by_ticker[t] for t in rm.tickers)

    var_block = []
    for c in VAR_CONFIDENCES:
        v = tailrisk.value_at_risk(port, c, horizon_days=1)
        monthly = tailrisk.value_at_risk(port, c, horizon_days=21)
        var_block.append(
            {
                "confidence_pct": round(c * 100, 1),
                "daily_var_pct": round(v.headline_pct * 100, 2),
                "daily_var_cad": round(v.headline_pct * total_mv, 2),
                "daily_cvar_pct": round(v.cvar_pct * 100, 2),
                "daily_cvar_cad": round(v.cvar_pct * total_mv, 2),
                "monthly_var_pct": round(monthly.headline_pct * 100, 2),
                "monthly_var_cad": round(monthly.headline_pct * total_mv, 2),
                "method": v.method,
                "gaussian_daily_var_pct": round(v.gaussian_pct * 100, 2),
                "historical_daily_var_pct": round(v.historical_pct * 100, 2),
            }
        )

    max_dd = tailrisk.max_drawdown(port)
    worst = {
        "worst_day_pct": round(tailrisk.worst_rolling_loss(port, 1) * 100, 2),
        "worst_week_pct": round(tailrisk.worst_rolling_loss(port, 5) * 100, 2),
        "worst_month_pct": round(tailrisk.worst_rolling_loss(port, 21) * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
    }

    scenarios: list[dict[str, Any]] = []
    beta_value = tailrisk.beta(port, rm.benchmark_returns) if rm.benchmark_returns is not None else None
    if beta_value is not None:
        for s in SCENARIOS:
            impact = tailrisk.scenario_loss(beta_value, s["benchmark_return"])
            scenarios.append(
                {
                    "name": s["name"],
                    "benchmark_shock_pct": round(s["benchmark_return"] * 100, 1),
                    "estimated_portfolio_return_pct": round(impact * 100, 2),
                    "estimated_loss_cad": round(-impact * total_mv, 2) if impact < 0 else 0.0,
                }
            )

    out: dict[str, Any] = {
        "portfolio_value_cad": round(total_mv, 2),
        "value_at_risk": var_block,
        "worst_historical": worst,
        "scenarios": scenarios,
        "portfolio_beta": round(beta_value, 2) if beta_value is not None else None,
        "history_obs": rm.n_obs,
        "interpretation": {
            "value_at_risk": (
                "Daily VaR at 95%% is the loss the portfolio exceeds on ~1 day "
                "in 20; CVaR is the average loss on those worst days. Headline "
                "method is Cornish-Fisher (fat-tail-adjusted) unless its "
                "validity guard failed, then historical."
            ),
            "scenarios": (
                "Hypothetical: estimated impact = portfolio beta × a benchmark "
                "shock. Statistical illustration, not a prediction."
            ),
        },
    }
    _attach_notes(out, loaded, rm.tickers)
    return out


def _attach_notes(out: dict[str, Any], loaded: _Loaded, analyzed: list[str]) -> None:
    notes = []
    if loaded.rm is not None and loaded.rm.excluded:
        notes.append(
            "Excluded for insufficient/mismatched history: "
            + ", ".join(f"{t} ({why})" for t, why in loaded.rm.excluded.items())
        )
    if loaded.dropped_for_size:
        notes.append(
            f"Analyzed the {len(analyzed)} largest holdings; "
            f"skipped smaller: {', '.join(loaded.dropped_for_size)}."
        )
    if notes:
        out["notes"] = notes
