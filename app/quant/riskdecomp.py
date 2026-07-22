"""Portfolio-level risk decomposition — the flagship analytics.

Everything here is a function of a covariance matrix Σ and a weight vector w
(weights are CAD market-value shares that sum to 1). All quantities are
reported annualized (daily × √252 for volatility).

The load-bearing identity is Euler's theorem on the (degree-1 homogeneous)
volatility σ_p = √(wᵀΣw):

    ∂σ_p/∂w_i = (Σw)_i / σ_p                       (marginal contribution)
    CRC_i     = w_i · (Σw)_i / σ_p                  (component contribution)
    Σ_i CRC_i = wᵀΣw / σ_p = σ_p                     (they sum to total risk)

That last equality is exact and is asserted in the tests — it is the guardrail
that keeps "Python computes every number" honest.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.quant.covariance import TRADING_DAYS, correlation_from_cov


@dataclass
class RiskDecomposition:
    tickers: list[str]
    weights: list[float]
    portfolio_vol: float  # annualized σ_p
    weighted_avg_vol: float  # annualized Σ w_i σ_i (the naive "sum of parts")
    diversification_ratio: float  # weighted_avg_vol / portfolio_vol, ≥ 1
    per_asset_vol: list[float]  # annualized σ_i
    marginal_contrib: list[float]  # annualized ∂σ_p/∂w_i
    component_contrib: list[float]  # annualized CRC_i (sum == portfolio_vol)
    risk_contrib_pct: list[float]  # CRC_i / σ_p × 100 (sum == 100)
    correlation: np.ndarray  # n×n correlation matrix
    avg_correlation: float
    effective_bets: float  # entropy-based effective number of independent bets


def _annualize_vol(daily_vol: float) -> float:
    return float(daily_vol * np.sqrt(TRADING_DAYS))


def decompose(
    cov: np.ndarray, weights: np.ndarray, tickers: list[str]
) -> RiskDecomposition:
    """Full risk decomposition from a daily covariance matrix and weights."""
    w = np.asarray(weights, dtype=float)
    if w.ndim != 1 or w.shape[0] != cov.shape[0]:
        raise ValueError("weights length must match covariance dimension")
    total = w.sum()
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    w = w / total  # normalize to shares

    sigma_w = cov @ w  # (Σw)_i, daily
    var_p = float(w @ sigma_w)  # wᵀΣw, daily variance
    daily_vol = float(np.sqrt(max(var_p, 0.0)))
    portfolio_vol = _annualize_vol(daily_vol)

    per_asset_daily = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    per_asset_vol = [_annualize_vol(v) for v in per_asset_daily]

    weighted_avg_daily = float(w @ per_asset_daily)
    weighted_avg_vol = _annualize_vol(weighted_avg_daily)

    # Diversification ratio ≥ 1, = 1 iff perfectly correlated.
    div_ratio = (
        weighted_avg_daily / daily_vol if daily_vol > 0 else 1.0
    )

    if daily_vol > 0:
        marginal_daily = sigma_w / daily_vol  # ∂σ_p/∂w_i, daily
    else:
        marginal_daily = np.zeros_like(w)
    component_daily = w * marginal_daily  # CRC_i, daily; sums to daily_vol
    marginal_contrib = [_annualize_vol(m) for m in marginal_daily]
    component_contrib = [_annualize_vol(c) for c in component_daily]
    risk_pct = (
        (component_daily / daily_vol * 100.0) if daily_vol > 0 else np.zeros_like(w)
    )

    corr = correlation_from_cov(cov)
    n = cov.shape[0]
    if n > 1:
        mask = ~np.eye(n, dtype=bool)
        avg_corr = float(corr[mask].mean())
    else:
        avg_corr = 0.0

    effective = _effective_bets(risk_pct / 100.0)

    return RiskDecomposition(
        tickers=list(tickers),
        weights=[float(x) for x in w],
        portfolio_vol=portfolio_vol,
        weighted_avg_vol=weighted_avg_vol,
        diversification_ratio=float(div_ratio),
        per_asset_vol=per_asset_vol,
        marginal_contrib=marginal_contrib,
        component_contrib=component_contrib,
        risk_contrib_pct=[float(x) for x in risk_pct],
        correlation=corr,
        avg_correlation=avg_corr,
        effective_bets=effective,
    )


def _effective_bets(risk_shares: np.ndarray) -> float:
    """Effective number of independent bets = exp(entropy of risk shares).

    For k assets each contributing an equal 1/k of total risk this returns k;
    when one holding dominates the risk it collapses toward 1 — the honest
    "you hold fewer real bets than positions" number. (Shannon-entropy form of
    the diversification measure; equivalent to 1/HHI only in the equal-share
    limit, and more discriminating off it.)
    """
    p = np.asarray(risk_shares, dtype=float)
    p = p[p > 0]
    if p.size == 0:
        return 0.0
    p = p / p.sum()
    entropy = -float((p * np.log(p)).sum())
    return float(np.exp(entropy))
