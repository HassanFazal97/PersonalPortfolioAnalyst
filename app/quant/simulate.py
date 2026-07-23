"""Monte Carlo projection of portfolio value (multivariate GBM).

Simulates correlated daily asset returns from the shrunk covariance matrix and
compounds them into portfolio-value paths, then reports the percentile fan
(the distribution of where the book could be in N days). This is a statistical
projection from historical covariance, NOT a forecast — framed that way to the
user.

Correctness choices (each defends a trap flagged in review):
- **Cholesky via eigenvalue-clip.** Near-collinear holdings (a stock + its ADR)
  can leave the shrunk covariance with a tiny negative eigenvalue, so a plain
  Cholesky throws. We clip eigenvalues to a small floor and reconstruct, which
  is robust and lets us report the condition number.
- **Drift ≈ 0.** A one- to two-year sample mean daily return is almost pure
  noise; using it would make the fan chart's center lie about expected
  outcomes. We simulate with zero drift by default (a small capped drift is
  optional), so the cone reflects *risk*, not a return prediction.
- **Log-space GBM with the −½σ² Itô term**, so compounding is unbiased.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TRADING_DAYS = 252
_PERCENTILES = (5, 25, 50, 75, 95)


@dataclass
class SimulationResult:
    horizon_days: int
    n_sims: int
    # Multiplicative value factors (1.0 = starting value) at the horizon.
    terminal_percentiles: dict[int, float]
    # Percentile of the value factor at each simulated day (for a fan chart):
    # {percentile: [factor_day_1, ...]}.
    fan: dict[int, list[float]]
    prob_loss: float  # P(portfolio below its starting value at the horizon)
    condition_number: float  # of the covariance used (diagnostic)


def psd_cholesky(cov: np.ndarray) -> np.ndarray:
    """Lower-triangular-ish factor L with L Lᵀ ≈ cov, robust to tiny negative
    eigenvalues via eigenvalue clipping (more robust than jitter)."""
    cov = np.asarray(cov, dtype=float)
    # Symmetrize defensively.
    cov = (cov + cov.T) / 2
    evals, evecs = np.linalg.eigh(cov)
    floor = 1e-12
    clipped = np.clip(evals, floor, None)
    return evecs @ np.diag(np.sqrt(clipped))


def condition_number(cov: np.ndarray) -> float:
    evals = np.linalg.eigvalsh((cov + cov.T) / 2)
    lo = float(np.clip(evals.min(), 1e-18, None))
    hi = float(evals.max())
    return hi / lo


def simulate_portfolio(
    cov: np.ndarray,
    weights: np.ndarray,
    *,
    horizon_days: int = TRADING_DAYS,
    n_sims: int = 5000,
    drift_daily: np.ndarray | float = 0.0,
    seed: int = 12345,
) -> SimulationResult:
    """Project portfolio value over ``horizon_days`` via multivariate GBM.

    ``cov`` and ``weights`` are the daily covariance and normalized weights
    (weights are re-normalized here). Returns the percentile fan of the
    portfolio value factor (1.0 = start).
    """
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    n_assets = cov.shape[0]
    rng = np.random.default_rng(seed)

    factor = psd_cholesky(cov)  # (n_assets, n_assets)
    sigma2 = np.clip(np.diag(cov), 0.0, None)
    mu = np.full(n_assets, drift_daily) if np.isscalar(drift_daily) else np.asarray(drift_daily, dtype=float)

    # Daily log-return draws: r_t = (mu - 0.5σ²) + L z, z ~ N(0, I).
    # Shape (horizon, n_sims, n_assets).
    z = rng.standard_normal((horizon_days, n_sims, n_assets))
    correlated = z @ factor.T
    log_returns = (mu - 0.5 * sigma2) + correlated  # broadcast over (h, sims)

    # Portfolio value path: start at 1.0, each day grows by the weighted simple
    # return of that day's asset log returns.
    simple = np.expm1(log_returns)  # (h, sims, n_assets)
    port_daily = simple @ w  # (h, sims): portfolio simple return per day
    value_paths = np.cumprod(1.0 + port_daily, axis=0)  # (h, sims)

    terminal = value_paths[-1, :]
    terminal_pct = {p: float(np.percentile(terminal, p)) for p in _PERCENTILES}
    fan = {
        p: [float(v) for v in np.percentile(value_paths, p, axis=1)]
        for p in _PERCENTILES
    }
    prob_loss = float((terminal < 1.0).mean())

    return SimulationResult(
        horizon_days=horizon_days,
        n_sims=n_sims,
        terminal_percentiles=terminal_pct,
        fan=fan,
        prob_loss=prob_loss,
        condition_number=condition_number(cov),
    )
