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

from app.quant import frontier as qfrontier
from app.quant import performance, tailrisk
from app.quant import returns as qreturns
from app.quant import simulate as qsimulate
from app.quant.covariance import ledoit_wolf
from app.quant.riskdecomp import decompose
from app.tools import fundamentals, portfolio, price_store
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
                # Reads the persistent daily_prices store (fill-on-miss), so
                # repeated risk calls are reproducible and don't re-hit Yahoo.
                return t, await price_store.get_adjusted_closes(ctx.repo, t, HISTORY_DAYS)
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
# Visual Risk Lab: one rich payload for the /app/risk page (not the chat model)
# --------------------------------------------------------------------------

# Weekly samples of the Monte Carlo fan keep the page's SVG light (~52 points
# per band over a year instead of 252).
_FAN_STRIDE = 5


async def risk_analytics_payload(ctx: Any) -> dict[str, Any]:
    """Everything the visual Risk Lab renders, computed in one pass.

    Distinct from the chat tools (which return compact, narration-shaped JSON):
    this returns the full correlation matrix and the Monte Carlo fan for
    charting. Called directly by the /portfolio/risk-analytics route — never by
    the model."""
    loaded = await _load_portfolio_returns({}, ctx, with_benchmark=True)
    if loaded.note:
        return {"available": False, "note": loaded.note}

    rm = loaded.rm
    est = ledoit_wolf(rm.matrix)
    d = decompose(est.cov, loaded.weights, rm.tickers)
    total_mv = sum(loaded.mv_by_ticker[t] for t in rm.tickers)

    port = tailrisk.portfolio_return_series(rm.matrix, loaded.weights)
    var95 = tailrisk.value_at_risk(port, 0.95)
    rf = float(
        getattr(ctx.settings, "risk_free_rate_annual", performance.DEFAULT_RISK_FREE_ANNUAL)
    )
    stats = performance.performance_stats(port, rm.benchmark_returns, rf_annual=rf)
    beta_value = (
        tailrisk.beta(port, rm.benchmark_returns) if rm.benchmark_returns is not None else None
    )
    mc = qsimulate.simulate_portfolio(
        est.cov, loaded.weights, horizon_days=_MC_HORIZON_DAYS, n_sims=5000
    )

    # Holdings sorted by risk contribution (the story ordering).
    order = sorted(range(len(d.tickers)), key=lambda i: d.risk_contrib_pct[i], reverse=True)
    holdings = [
        {
            "ticker": d.tickers[i],
            "weight_pct": round(loaded.mv_by_ticker[d.tickers[i]] / total_mv * 100, 2)
            if total_mv
            else 0.0,
            "risk_contribution_pct": round(d.risk_contrib_pct[i], 2),
            "annualized_vol_pct": round(d.per_asset_vol[i] * 100, 2),
        }
        for i in order
    ]

    # Correlation matrix in the SAME (risk-sorted) order as the holdings, so the
    # heatmap and the bar chart read consistently.
    corr = d.correlation
    idx = order
    matrix = [[round(float(corr[i, j]), 3) for j in idx] for i in idx]

    def _band(p: int) -> list[float]:
        series = mc.fan[p]
        sampled = series[:: _FAN_STRIDE] + [series[-1]]
        return [round((v - 1.0) * 100, 2) for v in sampled]  # % change from start

    return {
        "available": True,
        "summary": {
            "portfolio_value_cad": round(total_mv, 2),
            "annualized_volatility_pct": round(d.portfolio_vol * 100, 2),
            "weighted_avg_volatility_pct": round(d.weighted_avg_vol * 100, 2),
            "diversification_ratio": round(d.diversification_ratio, 2),
            "diversification_benefit_pct": round(
                (d.weighted_avg_vol - d.portfolio_vol) * 100, 2
            ),
            "effective_number_of_bets": round(d.effective_bets, 2),
            "holdings_analyzed": len(d.tickers),
            "average_correlation": round(d.avg_correlation, 2),
            "var95_1d_pct": round(var95.headline_pct * 100, 2),
            "var95_1d_cad": round(var95.headline_pct * total_mv, 2),
            "cvar95_1d_pct": round(var95.cvar_pct * 100, 2),
            "sharpe_ratio": round(stats.sharpe, 2) if stats.sharpe is not None else None,
            "portfolio_beta": round(beta_value, 2) if beta_value is not None else None,
        },
        "holdings": holdings,
        "correlation": {"tickers": [d.tickers[i] for i in idx], "matrix": matrix},
        "monte_carlo": {
            "horizon_days": mc.horizon_days,
            "simulations": mc.n_sims,
            "probability_of_loss_pct": round(mc.prob_loss * 100, 2),
            "bands_pct": {f"p{p}": _band(p) for p in (5, 25, 50, 75, 95)},
        },
        "notes": _analytics_notes(loaded, rm.tickers),
    }


def _analytics_notes(loaded: _Loaded, analyzed: list[str]) -> list[str]:
    notes: list[str] = []
    if loaded.rm is not None and loaded.rm.excluded:
        notes.append(
            "Excluded for insufficient/mismatched history: "
            + ", ".join(f"{t} ({why})" for t, why in loaded.rm.excluded.items())
        )
    if loaded.dropped_for_size:
        notes.append(
            f"Showing the {len(analyzed)} largest holdings; "
            f"skipped smaller: {', '.join(loaded.dropped_for_size)}."
        )
    return notes


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


# --------------------------------------------------------------------------
# Tool 4: forward projection — Monte Carlo + efficient frontier (Tier 4)
# --------------------------------------------------------------------------

# Fan-chart horizon snapshots (trading-day index, label).
_MC_HORIZON_DAYS = 252
_MC_SNAPSHOTS = [(21, "1 month"), (63, "3 months"), (126, "6 months"), (251, "1 year")]


async def project_portfolio_outcomes(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    loaded = await _load_portfolio_returns(payload, ctx, with_benchmark=False)
    if loaded.note:
        return {"note": loaded.note}

    rm = loaded.rm
    est = ledoit_wolf(rm.matrix)
    total_mv = sum(loaded.mv_by_ticker[t] for t in rm.tickers)

    # Monte Carlo projection (zero drift — the cone reflects risk, not a return
    # forecast; a 1-2yr sample mean is too noisy to trust as drift).
    mc = qsimulate.simulate_portfolio(
        est.cov, loaded.weights, horizon_days=_MC_HORIZON_DAYS, n_sims=5000
    )
    projected_value = {
        f"p{p}": round(f * total_mv, 2) for p, f in mc.terminal_percentiles.items()
    }
    projected_change = {
        f"p{p}": round((f - 1.0) * 100, 2) for p, f in mc.terminal_percentiles.items()
    }
    snapshots = []
    for day, label in _MC_SNAPSHOTS:
        if day < mc.horizon_days:
            snapshots.append(
                {
                    "horizon": label,
                    "p5_change_pct": round((mc.fan[5][day] - 1.0) * 100, 2),
                    "p50_change_pct": round((mc.fan[50][day] - 1.0) * 100, 2),
                    "p95_change_pct": round((mc.fan[95][day] - 1.0) * 100, 2),
                }
            )

    # Efficient frontier — descriptive reference only ("you are here").
    mean_daily = rm.matrix.mean(axis=0)
    fr = qfrontier.efficient_frontier(est.cov, mean_daily, loaded.weights, rm.tickers)
    frontier_block = {
        "current": {
            "annualized_vol_pct": round(fr.current.annualized_vol_pct, 2),
            "annualized_return_pct": round(fr.current.annualized_return_pct, 2),
        },
        "min_variance_reference": {
            "annualized_vol_pct": round(fr.min_variance.annualized_vol_pct, 2),
            "annualized_return_pct": round(fr.min_variance.annualized_return_pct, 2),
        },
        # Vol/return coordinates only — deliberately NO target weights in the
        # narration payload, so the frontier reads as a descriptive reference,
        # never a rebalance instruction.
        "frontier_points": [
            {
                "annualized_vol_pct": round(p.annualized_vol_pct, 2),
                "annualized_return_pct": round(p.annualized_return_pct, 2),
            }
            for p in fr.frontier
        ],
    }
    if fr.note:
        frontier_block["note"] = fr.note

    out: dict[str, Any] = {
        "monte_carlo": {
            "horizon_days": mc.horizon_days,
            "simulations": mc.n_sims,
            "starting_value_cad": round(total_mv, 2),
            "projected_value_cad": projected_value,
            "projected_change_pct": projected_change,
            "probability_of_loss_pct": round(mc.prob_loss * 100, 2),
            "snapshots": snapshots,
        },
        "efficient_frontier": frontier_block,
        "interpretation": {
            "monte_carlo": (
                "A statistical projection from the holdings' historical "
                "covariance with ZERO assumed drift — the spread shows risk, "
                "not an expected return. p5–p95 is a 90% range of where the "
                "portfolio could sit. NOT a forecast."
            ),
            "efficient_frontier": (
                "Where the portfolio sits on the risk/return plane vs the "
                "minimum-variance reference and the frontier of least-risk "
                "portfolios at each return level. An educational reference "
                "only — not a recommendation to rebalance."
            ),
        },
    }
    _attach_notes(out, loaded, rm.tickers)
    return out


# --------------------------------------------------------------------------
# Tool 3: risk-adjusted performance & exposure (Tier 3)
# --------------------------------------------------------------------------


async def assess_risk_adjusted_performance(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    loaded = await _load_portfolio_returns(payload, ctx, with_benchmark=True)
    if loaded.note:
        return {"note": loaded.note}

    rm = loaded.rm
    port = tailrisk.portfolio_return_series(rm.matrix, loaded.weights)
    rf = float(
        getattr(ctx.settings, "risk_free_rate_annual", performance.DEFAULT_RISK_FREE_ANNUAL)
    )
    stats = performance.performance_stats(port, rm.benchmark_returns, rf_annual=rf)
    beta_value = (
        tailrisk.beta(port, rm.benchmark_returns) if rm.benchmark_returns is not None else None
    )

    sector_exposure = await _sector_exposure(rm.tickers, loaded.mv_by_ticker, ctx)

    out: dict[str, Any] = {
        "risk_adjusted": {
            "annualized_return_pct": round(stats.annualized_return_pct, 2),
            "annualized_volatility_pct": round(stats.annualized_vol_pct, 2),
            "sharpe_ratio": round(stats.sharpe, 2) if stats.sharpe is not None else None,
            "sortino_ratio": round(stats.sortino, 2) if stats.sortino is not None else None,
            "tracking_error_pct": (
                round(stats.tracking_error_pct, 2)
                if stats.tracking_error_pct is not None
                else None
            ),
            "information_ratio": (
                round(stats.information_ratio, 2)
                if stats.information_ratio is not None
                else None
            ),
            "portfolio_beta": round(beta_value, 2) if beta_value is not None else None,
            "risk_free_rate_pct": round(stats.risk_free_rate_pct, 2),
            "history_obs": stats.obs,
        },
        "sector_exposure": sector_exposure,
        "interpretation": {
            "sharpe_ratio": (
                "Return per unit of total volatility above the risk-free rate; "
                "higher is better, <1 is modest, >1 good, >2 strong."
            ),
            "sortino_ratio": (
                "Like Sharpe but penalizes only downside volatility — usually "
                "higher than Sharpe for a portfolio with upside swings."
            ),
            "tracking_error_pct": (
                "How much the portfolio's return wanders from the benchmark, "
                "annualized. Information ratio is active return per unit of it."
            ),
        },
    }
    _attach_notes(out, loaded, rm.tickers)
    return out


async def _sector_exposure(
    tickers: list[str], mv_by_ticker: dict[str, float], ctx: Any
) -> list[dict[str, Any]]:
    """Portfolio weight grouped by GICS-ish sector, from the fundamentals cache.

    A holding whose sector is unknown (e.g. many ETFs) folds into 'Unknown';
    the model can note the uncovered share."""
    try:
        funds = await fundamentals.get_fundamentals(
            tickers, repo=ctx.repo, settings=ctx.settings
        )
    except Exception:  # noqa: BLE001 - exposure is a nice-to-have, never fatal
        funds = {}

    total = sum(mv_by_ticker[t] for t in tickers) or 1.0
    by_sector: dict[str, float] = {}
    for t in tickers:
        sector = ((funds.get(t) or {}).get("profile") or {}).get("sector") or "Unknown"
        by_sector[sector] = by_sector.get(sector, 0.0) + mv_by_ticker[t]

    rows = [
        {"sector": s, "weight_pct": round(mv / total * 100, 2)}
        for s, mv in by_sector.items()
    ]
    rows.sort(key=lambda r: r["weight_pct"], reverse=True)
    return rows


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
