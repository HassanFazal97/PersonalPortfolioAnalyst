"""Tail-risk analytics: Value at Risk, Expected Shortfall, drawdown, scenarios.

All functions take a *simple* daily return series (the reconstructed portfolio
return, one number per day) and are pure numpy — the tool layer builds the
series from the returns matrix and current weights.

Conventions (fixed once, centrally):
- Losses are reported as **positive magnitudes** (a 95%% VaR of 0.03 means "a
  loss of 3%% or more is expected on ~5%% of days").
- Confidence ``c`` (e.g. 0.95) ⇒ tail probability ``α = 1 − c``.
- Parametric VaR scales across horizons by √t (iid-Gaussian assumption).
  Historical VaR is **not** √t-scaled — that assumption doesn't hold in the
  empirical tail; report it at its native 1-day horizon only.

The inverse-normal CDF uses Acklam's rational approximation (max relative error
~1.15e-9) so no scipy dependency is pulled for VaR.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log, sqrt

import numpy as np

TRADING_DAYS = 252

# Acklam (2003) coefficients for the inverse standard-normal CDF.
_A = [
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
]
_B = [
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
]
_C = [
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
]
_D = [
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
]


def inverse_normal_cdf(p: float) -> float:
    """Φ⁻¹(p) — the standard-normal quantile — via Acklam's approximation."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = sqrt(-2 * log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5]) * q / (
            ((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1
        )
    q = sqrt(-2 * log(1 - p))
    return -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
        (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1
    )


@dataclass
class VaRResult:
    confidence: float
    horizon_days: int
    gaussian_pct: float  # parametric normal VaR, loss %
    cornish_fisher_pct: float  # skew/kurtosis-adjusted VaR, loss %
    historical_pct: float  # empirical 1-day VaR, loss %
    cvar_pct: float  # expected shortfall (historical), loss %
    method: str  # "cornish_fisher" or "historical" (chosen headline)
    headline_pct: float  # the VaR we lead with, after the CF validity guard


def gaussian_var(mu: float, sigma: float, confidence: float, horizon_days: int = 1) -> float:
    """Parametric normal VaR as a positive loss fraction, √t-scaled."""
    alpha = 1 - confidence
    z = inverse_normal_cdf(alpha)  # negative
    scale = sqrt(horizon_days)
    var = -(mu * horizon_days + z * sigma * scale)
    return var


def _cf_quantile(z: float, skew: float, exkurt: float) -> float:
    """Cornish-Fisher expansion of the α-quantile."""
    return (
        z
        + (z**2 - 1) / 6 * skew
        + (z**3 - 3 * z) / 24 * exkurt
        - (2 * z**3 - 5 * z) / 36 * skew**2
    )


def _cf_is_monotone(z: float, skew: float, exkurt: float) -> bool:
    """The CF map z→z_cf must be increasing near z, else the quantile expansion
    is out of its validity domain and can report a *less* extreme loss than the
    Gaussian — nonsense. Guard via the derivative."""
    deriv = (
        1
        + (2 * z) / 6 * skew
        + (3 * z**2 - 3) / 24 * exkurt
        - (6 * z**2 - 5) / 36 * skew**2
    )
    return deriv > 0


def cornish_fisher_var(
    mu: float, sigma: float, skew: float, exkurt: float, confidence: float, horizon_days: int = 1
) -> tuple[float, bool]:
    """CF VaR (positive loss fraction) and whether the expansion was valid."""
    alpha = 1 - confidence
    z = inverse_normal_cdf(alpha)
    valid = _cf_is_monotone(z, skew, exkurt)
    z_cf = _cf_quantile(z, skew, exkurt)
    scale = sqrt(horizon_days)
    var = -(mu * horizon_days + z_cf * sigma * scale)
    return var, valid


def historical_var(returns: np.ndarray, confidence: float) -> float:
    """Empirical 1-day VaR: negative of the α-quantile of realized returns."""
    alpha = 1 - confidence
    q = float(np.percentile(returns, alpha * 100))
    return -q


def cvar(returns: np.ndarray, confidence: float) -> float:
    """Expected shortfall: mean loss in the worst α tail (≥ historical VaR)."""
    alpha = 1 - confidence
    threshold = np.percentile(returns, alpha * 100)
    tail = returns[returns <= threshold]
    if tail.size == 0:
        return -float(threshold)
    return -float(tail.mean())


def _moments(returns: np.ndarray) -> tuple[float, float, float, float]:
    """(mean, std, skew, excess-kurtosis) of a return series."""
    n = returns.size
    mu = float(returns.mean())
    sigma = float(returns.std(ddof=1)) if n > 1 else 0.0
    if sigma == 0 or n < 3:
        return mu, sigma, 0.0, 0.0
    z = (returns - mu) / sigma
    skew = float((z**3).mean())
    exkurt = float((z**4).mean() - 3.0)
    return mu, sigma, skew, exkurt


def value_at_risk(
    returns: np.ndarray, confidence: float, horizon_days: int = 1
) -> VaRResult:
    """Full VaR panel with the Cornish-Fisher validity guard.

    The headline VaR is Cornish-Fisher when its expansion is valid (captures
    the fat left tail equities actually have); otherwise it falls back to the
    empirical historical VaR and says so.
    """
    mu, sigma, skew, exkurt = _moments(returns)
    g = gaussian_var(mu, sigma, confidence, horizon_days)
    cf, cf_valid = cornish_fisher_var(mu, sigma, skew, exkurt, confidence, horizon_days)
    hist = historical_var(returns, confidence)
    es = cvar(returns, confidence)
    if cf_valid:
        method, headline = "cornish_fisher", cf
    else:
        method, headline = "historical", hist
    return VaRResult(
        confidence=confidence,
        horizon_days=horizon_days,
        gaussian_pct=g,
        cornish_fisher_pct=cf,
        historical_pct=hist,
        cvar_pct=es,
        method=method,
        headline_pct=headline,
    )


def portfolio_return_series(matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Reconstruct the daily portfolio SIMPLE return from a LOG-return matrix.

    Portfolio simple return = Σ w_i (e^{r_i} − 1); weights are normalized to
    shares. Simple returns are the right space for VaR magnitudes.
    """
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    simple = np.expm1(matrix)  # log -> simple, per asset per day
    return simple @ w


def max_drawdown(returns: np.ndarray) -> float:
    """Worst peak-to-trough decline of the cumulative return, as a positive %."""
    if returns.size == 0:
        return 0.0
    cum = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    return float(-dd.min())


def worst_rolling_loss(returns: np.ndarray, window: int) -> float:
    """Worst realized ``window``-day cumulative loss, as a positive fraction."""
    if returns.size < window:
        return 0.0
    logret = np.log1p(returns)
    cum = np.concatenate([[0.0], np.cumsum(logret)])
    # k-day log return ending at i = cum[i] - cum[i-window]
    rolling = cum[window:] - cum[:-window]
    worst_log = float(rolling.min())
    return -float(np.expm1(worst_log))


def beta(port_returns: np.ndarray, bench_returns: np.ndarray) -> float | None:
    """Portfolio beta to a benchmark: cov(p, b) / var(b) over aligned days.

    NaNs (dates the benchmark lacked) are dropped pairwise.
    """
    p = np.asarray(port_returns, dtype=float)
    b = np.asarray(bench_returns, dtype=float)
    mask = ~(np.isnan(p) | np.isnan(b))
    p, b = p[mask], b[mask]
    if p.size < 2:
        return None
    var_b = float(b.var(ddof=1))
    if var_b == 0:
        return None
    cov = float(np.cov(p, b, ddof=1)[0, 1])
    return cov / var_b


def scenario_loss(beta_value: float, benchmark_shock: float) -> float:
    """Estimated portfolio return under a benchmark shock, via beta.

    ``benchmark_shock`` is a return (e.g. −0.30 for a 30%% benchmark drop);
    returns the estimated portfolio return (negative = loss).
    """
    return beta_value * benchmark_shock
