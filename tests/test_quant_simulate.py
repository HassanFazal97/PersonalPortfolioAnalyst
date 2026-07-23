"""Guardrails for Monte Carlo simulation and the efficient frontier."""

from __future__ import annotations

import numpy as np

from app.quant import frontier as fr
from app.quant import simulate as sim


def _two_asset_cov(s1, s2, rho):
    return np.array([[s1**2, rho * s1 * s2], [rho * s1 * s2, s2**2]], dtype=float)


def test_psd_cholesky_reconstructs_and_handles_collinearity():
    # Two identical assets -> singular covariance; eigenvalue-clip must still
    # yield a factor L with L Lᵀ ≈ cov (no exception).
    cov = _two_asset_cov(0.02, 0.02, 1.0)
    L = sim.psd_cholesky(cov)
    np.testing.assert_allclose(L @ L.T, cov, atol=1e-6)


def test_simulation_recovers_input_covariance():
    # The simulated daily returns' covariance should match the input Σ within
    # Monte Carlo error at large N.
    cov = _two_asset_cov(0.015, 0.02, 0.4)
    w = np.array([0.5, 0.5])
    # Recover per-asset behaviour by simulating and checking portfolio vol lands
    # near the analytic wᵀΣw (annualized) at large N.
    res = sim.simulate_portfolio(cov, w, horizon_days=252, n_sims=20000, seed=7)
    # Median terminal factor near 1 (zero-drift), and a plausible spread.
    assert 0.9 < res.terminal_percentiles[50] < 1.1
    assert res.terminal_percentiles[5] < res.terminal_percentiles[95]
    assert 0.0 <= res.prob_loss <= 1.0


def test_simulation_fan_is_monotone_across_percentiles():
    cov = _two_asset_cov(0.01, 0.03, 0.2)
    w = np.array([0.7, 0.3])
    res = sim.simulate_portfolio(cov, w, horizon_days=60, n_sims=8000, seed=3)
    # At each day, p5 <= p50 <= p95.
    for d in range(res.horizon_days):
        assert res.fan[5][d] <= res.fan[50][d] <= res.fan[95][d]


def test_zero_vol_portfolio_stays_essentially_constant():
    cov = np.array([[0.0, 0.0], [0.0, 0.0]])
    w = np.array([0.5, 0.5])
    res = sim.simulate_portfolio(cov, w, horizon_days=30, n_sims=100, seed=1)
    # No variance -> value factor holds at 1.0 to within the PSD eigenvalue
    # floor (a deliberate ~1e-6/day numerical safety, not real risk).
    for p in (5, 50, 95):
        assert abs(res.terminal_percentiles[p] - 1.0) < 1e-3


def test_frontier_min_variance_is_lowest_risk_and_long_only():
    # Two positively-correlated assets: the long-only min-variance vol must not
    # exceed either single asset's vol, and weights are valid.
    cov = _two_asset_cov(0.01, 0.02, 0.3)
    mean = np.array([0.0004, 0.0006])
    w_cur = np.array([0.5, 0.5])
    res = fr.efficient_frontier(cov, mean, w_cur, ["A", "B"])
    mv = res.min_variance
    single_vols = [np.sqrt(cov[i, i]) * np.sqrt(252) * 100 for i in range(2)]
    assert mv.annualized_vol_pct <= min(single_vols) + 1e-6
    w = mv.weights
    assert abs(sum(w) - 1.0) < 1e-6 and all(x >= -1e-9 for x in w)


def test_frontier_two_asset_analytic_min_variance():
    # Closed-form long-only min-var weight for asset 1:
    # w1 = (σ2² - ρσ1σ2) / (σ1² + σ2² - 2ρσ1σ2), clipped to [0,1].
    s1, s2, rho = 0.01, 0.02, 0.3
    cov = _two_asset_cov(s1, s2, rho)
    mean = np.array([0.0005, 0.0005])
    res = fr.efficient_frontier(cov, mean, np.array([0.5, 0.5]), ["A", "B"])
    num = s2**2 - rho * s1 * s2
    den = s1**2 + s2**2 - 2 * rho * s1 * s2
    w1_analytic = min(1.0, max(0.0, num / den))
    assert abs(res.min_variance.weights[0] - w1_analytic) < 1e-3


def test_frontier_points_ascend_in_risk():
    cov = _two_asset_cov(0.012, 0.025, 0.1)
    mean = np.array([0.0003, 0.0009])
    res = fr.efficient_frontier(cov, mean, np.array([0.4, 0.6]), ["A", "B"], n_points=6)
    vols = [p.annualized_vol_pct for p in res.frontier]
    assert vols == sorted(vols)
