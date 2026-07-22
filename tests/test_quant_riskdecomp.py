"""Closed-form guardrails for the covariance + risk-decomposition engine."""

from __future__ import annotations

import numpy as np

from app.quant.covariance import TRADING_DAYS, correlation_from_cov, ledoit_wolf
from app.quant.riskdecomp import decompose


def _two_asset_cov(s1: float, s2: float, rho: float) -> np.ndarray:
    return np.array(
        [[s1**2, rho * s1 * s2], [rho * s1 * s2, s2**2]], dtype=float
    )


def test_two_asset_portfolio_vol_matches_closed_form():
    # σ_p² = w1²σ1² + w2²σ2² + 2 w1 w2 ρ σ1 σ2 (daily), then annualize.
    s1, s2, rho = 0.01, 0.02, 0.3
    w = np.array([0.6, 0.4])
    cov = _two_asset_cov(s1, s2, rho)
    d = decompose(cov, w, ["A", "B"])
    daily_var = (
        w[0] ** 2 * s1**2 + w[1] ** 2 * s2**2 + 2 * w[0] * w[1] * rho * s1 * s2
    )
    expected = np.sqrt(daily_var) * np.sqrt(TRADING_DAYS)
    assert abs(d.portfolio_vol - expected) < 1e-12


def test_euler_component_contributions_sum_to_total_vol():
    # Σ_i CRC_i == σ_p, exactly (Euler on the degree-1 homogeneous σ_p).
    rng = np.random.default_rng(0)
    x = rng.normal(0, 0.01, size=(400, 5))
    cov = np.cov(x, rowvar=False)
    w = np.array([0.3, 0.25, 0.2, 0.15, 0.1])
    d = decompose(cov, w, list("ABCDE"))
    assert abs(sum(d.component_contrib) - d.portfolio_vol) < 1e-10
    assert abs(sum(d.risk_contrib_pct) - 100.0) < 1e-9


def test_diversification_ratio_bounds():
    # ρ = 1 -> ratio == 1; ρ < 1 -> ratio > 1.
    w = np.array([0.5, 0.5])
    perfect = decompose(_two_asset_cov(0.01, 0.02, 1.0), w, ["A", "B"])
    assert abs(perfect.diversification_ratio - 1.0) < 1e-9
    imperfect = decompose(_two_asset_cov(0.01, 0.02, 0.0), w, ["A", "B"])
    assert imperfect.diversification_ratio > 1.0


def test_effective_bets_equals_k_for_independent_equal_weight():
    # k independent, equal-vol, equal-weight assets -> effective bets == k.
    k = 4
    cov = np.eye(k) * (0.015**2)
    w = np.full(k, 1.0 / k)
    d = decompose(cov, w, list("WXYZ"))
    assert abs(d.effective_bets - k) < 1e-9


def test_effective_bets_collapses_when_one_holding_dominates_risk():
    # A tiny-weight, tiny-vol asset next to a dominant one -> effective ≈ 1.
    cov = np.array([[0.03**2, 0.0], [0.0, 0.0001**2]])
    w = np.array([0.99, 0.01])
    d = decompose(cov, w, ["BIG", "small"])
    assert d.effective_bets < 1.1


def test_ledoit_wolf_reduces_to_sample_when_target_equals_sample():
    # Two assets with identical variance and their sample correlation already
    # equal to r̄ (trivially true for n=2): shrinkage leaves cov PSD and close.
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.01, size=(500, 2))
    est = ledoit_wolf(x)
    assert 0.0 <= est.shrinkage <= 1.0
    # Shrunk matrix stays symmetric PSD.
    evals = np.linalg.eigvalsh(est.cov)
    assert (evals > -1e-12).all()
    assert np.allclose(est.cov, est.cov.T)


def test_ledoit_wolf_shrinks_toward_target_on_noisy_high_dim():
    # p close to T: sample cov is noisy, so optimal shrinkage should be > 0.
    rng = np.random.default_rng(2)
    x = rng.normal(0, 0.01, size=(60, 25))
    est = ledoit_wolf(x)
    assert est.shrinkage > 0.0
    evals = np.linalg.eigvalsh(est.cov)
    assert (evals > -1e-10).all()  # shrinkage keeps it PSD


def test_correlation_from_cov_is_unit_diagonal():
    cov = _two_asset_cov(0.01, 0.02, 0.4)
    corr = correlation_from_cov(cov)
    assert abs(corr[0, 0] - 1.0) < 1e-12
    assert abs(corr[1, 1] - 1.0) < 1e-12
    assert abs(corr[0, 1] - 0.4) < 1e-12
