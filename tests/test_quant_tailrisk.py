"""Closed-form guardrails for the tail-risk math (VaR/CVaR/drawdown/beta)."""

from __future__ import annotations

import numpy as np

from app.quant import tailrisk


def test_inverse_normal_cdf_known_quantiles():
    assert abs(tailrisk.inverse_normal_cdf(0.975) - 1.959964) < 1e-4
    assert abs(tailrisk.inverse_normal_cdf(0.95) - 1.644854) < 1e-4
    assert abs(tailrisk.inverse_normal_cdf(0.5)) < 1e-6
    # Symmetry.
    assert abs(tailrisk.inverse_normal_cdf(0.05) + 1.644854) < 1e-4


def test_gaussian_var_equals_z_sigma():
    # μ=0: VaR_95 = z_95 · σ.
    sigma = 0.02
    var = tailrisk.gaussian_var(0.0, sigma, 0.95)
    assert abs(var - 1.644854 * sigma) < 1e-5


def test_cornish_fisher_equals_gaussian_at_zero_skew_kurt():
    var_cf, valid = tailrisk.cornish_fisher_var(0.001, 0.02, 0.0, 0.0, 0.95)
    var_g = tailrisk.gaussian_var(0.001, 0.02, 0.95)
    assert valid
    assert abs(var_cf - var_g) < 1e-12


def test_cornish_fisher_guard_flags_extreme_moments():
    # Large skew (the z·skew² term dominates) pushes the CF map non-monotone
    # -> the guard must refuse it (caller falls back to historical VaR).
    _, valid = tailrisk.cornish_fisher_var(0.0, 0.02, 6.0, 2.0, 0.99)
    assert valid is False


def test_var_monotone_in_confidence_and_cvar_dominates():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0005, 0.015, size=1000)
    v95 = tailrisk.value_at_risk(returns, 0.95)
    v99 = tailrisk.value_at_risk(returns, 0.99)
    assert v99.headline_pct >= v95.headline_pct
    # CVaR (mean of the worst tail) is at least the historical VaR.
    assert v95.cvar_pct >= v95.historical_pct - 1e-12
    assert v99.cvar_pct >= v99.historical_pct - 1e-12


def test_historical_var_matches_hand_counted_percentile():
    returns = np.array([-0.10, -0.05, -0.02, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    # 5th percentile via numpy is what the function must use.
    expected = -float(np.percentile(returns, 5))
    assert abs(tailrisk.historical_var(returns, 0.95) - expected) < 1e-12


def test_max_drawdown_known_series():
    # Prices 100 -> 120 -> 90 -> 100: worst peak-to-trough is 120 -> 90 = -25%.
    prices = np.array([100.0, 120.0, 90.0, 100.0])
    rets = prices[1:] / prices[:-1] - 1
    dd = tailrisk.max_drawdown(rets)
    assert abs(dd - 0.25) < 1e-9


def test_worst_rolling_loss():
    # 5 straight -1% days -> worst 3-day loss ≈ 1-(0.99^3).
    returns = np.array([-0.01] * 5)
    worst3 = tailrisk.worst_rolling_loss(returns, 3)
    assert abs(worst3 - (1 - 0.99**3)) < 1e-9


def test_beta_recovers_slope():
    rng = np.random.default_rng(1)
    bench = rng.normal(0, 0.01, size=500)
    port = 1.5 * bench  # exact -> beta == 1.5
    assert abs(tailrisk.beta(port, bench) - 1.5) < 1e-9


def test_beta_drops_nan_pairs():
    bench = np.array([0.01, np.nan, -0.02, 0.03, -0.01])
    port = 2.0 * np.array([0.01, 0.5, -0.02, 0.03, -0.01])
    # The NaN benchmark day is dropped; the rest are exactly 2× -> beta 2.
    assert abs(tailrisk.beta(port, bench) - 2.0) < 1e-9


def test_scenario_loss_is_beta_times_shock():
    assert abs(tailrisk.scenario_loss(1.3, -0.20) - (-0.26)) < 1e-12
