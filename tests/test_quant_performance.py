"""Closed-form guardrails for risk-adjusted performance metrics."""

from __future__ import annotations

import numpy as np

from app.quant import performance as perf


def test_sharpe_matches_definition():
    returns = np.array([0.02, -0.01, 0.03, 0.0, 0.01])
    s = perf.sharpe(returns, rf_annual=0.0)
    expected = returns.mean() / returns.std(ddof=1) * np.sqrt(perf.TRADING_DAYS)
    assert abs(s - expected) < 1e-12


def test_sharpe_none_on_zero_variance():
    assert perf.sharpe(np.array([0.01, 0.01, 0.01])) is None


def test_annualized_vol_scales_by_sqrt_252():
    returns = np.array([0.01, -0.01, 0.02, -0.02, 0.0])
    assert abs(perf.annualized_vol(returns) - returns.std(ddof=1) * np.sqrt(252)) < 1e-12


def test_annualized_return_geometric():
    # +1% every day for 252 days compounds to (1.01)^252 - 1.
    returns = np.full(252, 0.01)
    assert abs(perf.annualized_return(returns) - (1.01**252 - 1)) < 1e-9


def test_sortino_at_least_sharpe_for_positive_mean():
    # Downside deviation <= total std, so with positive excess mean Sortino >= Sharpe.
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0008, 0.012, size=500)
    s = perf.sharpe(returns, rf_annual=0.0)
    so = perf.sortino(returns, rf_annual=0.0)
    assert so is not None and s is not None
    assert so >= s - 1e-9


def test_tracking_error_zero_when_matching_benchmark():
    port = np.array([0.01, -0.02, 0.03, 0.0])
    assert perf.tracking_error(port, port.copy()) == 0.0
    # Information ratio is undefined (no active risk) -> None.
    assert perf.information_ratio(port, port.copy()) is None


def test_tracking_error_drops_nan_benchmark_days():
    port = np.array([0.01, 0.02, -0.01, 0.03])
    bench = np.array([0.01, np.nan, -0.01, 0.02])
    te = perf.tracking_error(port, bench)
    # Only 3 aligned days; active = [0, 0, 0.01] -> nonzero, finite.
    assert te is not None and te > 0


def test_performance_stats_without_benchmark_has_no_tracking_error():
    returns = np.array([0.01, -0.01, 0.02, 0.0, 0.015])
    stats = perf.performance_stats(returns, None)
    assert stats.tracking_error_pct is None
    assert stats.information_ratio is None
    assert stats.sharpe is not None
