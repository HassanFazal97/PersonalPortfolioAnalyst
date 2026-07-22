"""Covariance estimation for the returns matrix.

Sample covariance with ~250-500 daily observations and ≤30 assets is
full-rank and fine for computing wᵀΣw, but noisy — its eigenvalue spread is
inflated and its smallest eigenvalues are biased low. That noise is harmless
for portfolio volatility and risk contributions (which use Σw, not Σ⁻¹) but
dangerous the moment Σ is inverted (min-variance, efficient frontier).

**Ledoit-Wolf shrinkage toward a constant-correlation target** (Ledoit & Wolf,
2004, "Honey, I Shrunk the Sample Covariance Matrix") is the fix: a closed-form,
tuning-free convex combination

    Σ_shrunk = δ·F + (1 − δ)·S

where S is the sample covariance, F the constant-correlation target (each
asset's own sample variance, all pairwise correlations replaced by their
average r̄), and δ ∈ [0, 1] the analytically optimal shrinkage intensity.

The constant-correlation target is deliberate: the single-index (market-model)
target mis-specifies Canadian names that load poorly on ^GSPC, and the
diagonal target shrinks the off-diagonals toward zero — destroying exactly the
cross-correlations this product exists to surface.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TRADING_DAYS = 252


@dataclass
class CovarianceEstimate:
    """A shrunk daily covariance matrix and the pieces used to build it.

    ``cov`` is the shrunk daily covariance (annualize by ×252 for reporting).
    ``shrinkage`` is δ (0 = pure sample, 1 = pure target); ``avg_corr`` is the
    average pairwise correlation r̄ that defines the target.
    """

    cov: np.ndarray
    sample_cov: np.ndarray
    shrinkage: float
    avg_corr: float


def _constant_correlation_target(sample_cov: np.ndarray) -> tuple[np.ndarray, float]:
    """The constant-correlation target F and the average correlation r̄.

    Off-diagonals: r̄·σ_i·σ_j. Diagonal: the asset's own sample variance.
    """
    var = np.diag(sample_cov)
    std = np.sqrt(var)
    outer_std = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = sample_cov / outer_std
    corr = np.where(outer_std > 0, corr, 0.0)
    n = sample_cov.shape[0]
    # Average of the off-diagonal correlations.
    if n > 1:
        mask = ~np.eye(n, dtype=bool)
        avg_corr = float(corr[mask].mean())
    else:
        avg_corr = 0.0
    target = avg_corr * outer_std
    np.fill_diagonal(target, var)
    return target, avg_corr


def ledoit_wolf(returns: np.ndarray) -> CovarianceEstimate:
    """Ledoit-Wolf constant-correlation shrinkage estimate of daily covariance.

    ``returns`` is shape (n_obs, n_assets). The optimal intensity δ* = κ/T is
    clamped to [0, 1]; κ = (π − ρ) / γ where π is the sum of asymptotic
    variances of the sample covariance entries, ρ the covariance between the
    estimation error of the target and the sample, and γ the squared
    Frobenius distance between S and F.
    """
    x = np.asarray(returns, dtype=float)
    t, n = x.shape
    if t < 2:
        raise ValueError("need at least 2 observations to estimate covariance")

    mean = x.mean(axis=0)
    xc = x - mean
    # Sample covariance (MLE / T normalization, matching Ledoit-Wolf's derivation).
    sample = xc.T @ xc / t

    if n == 1:
        return CovarianceEstimate(
            cov=sample.copy(), sample_cov=sample, shrinkage=0.0, avg_corr=0.0
        )

    target, avg_corr = _constant_correlation_target(sample)

    # π: sum over i,j of Var(sqrt(T)·s_ij) estimated by the fourth moments.
    xc2 = xc**2
    pi_mat = (xc2.T @ xc2) / t - sample**2
    pi_hat = float(pi_mat.sum())

    # γ: squared Frobenius norm of (F − S).
    gamma_hat = float(((target - sample) ** 2).sum())

    # ρ: sum of asymptotic covariances between target and sample estimators.
    # Diagonal part is the diagonal of π; off-diagonal uses the constant-corr
    # term (Ledoit-Wolf 2004, appendix B).
    var = np.diag(sample)
    std = np.sqrt(var)
    rho_diag = float(np.diag(pi_mat).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        # theta_ii,ij terms: E[xc_i^2 · xc_i·xc_j] - s_ii·s_ij
        term1 = (xc2 * xc).T @ xc / t  # (n,n): mean of xc_i^2 · xc_j
        theta_ij = term1 - var[:, None] * sample  # asymptotic cov, one direction
        ratio = np.where(std[None, :] > 0, std[:, None] / std[None, :], 0.0)
    off = avg_corr / 2.0 * (ratio * theta_ij + ratio.T * theta_ij.T)
    off_mask = ~np.eye(n, dtype=bool)
    rho_hat = rho_diag + float(off[off_mask].sum())

    if gamma_hat <= 0:
        delta = 0.0
    else:
        kappa = (pi_hat - rho_hat) / gamma_hat
        delta = max(0.0, min(1.0, kappa / t))

    cov = delta * target + (1.0 - delta) * sample
    return CovarianceEstimate(
        cov=cov, sample_cov=sample, shrinkage=float(delta), avg_corr=avg_corr
    )


def correlation_from_cov(cov: np.ndarray) -> np.ndarray:
    """Correlation matrix from a covariance matrix (zero-variance-safe)."""
    std = np.sqrt(np.diag(cov))
    outer = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(outer > 0, cov / outer, 0.0)
    # Clamp tiny numerical overshoots past ±1.
    return np.clip(corr, -1.0, 1.0)
