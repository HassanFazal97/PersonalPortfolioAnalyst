"""Mean-variance efficient frontier — DESCRIPTIVE reference only.

This module computes where the current portfolio sits on the risk/return plane
and a few reference portfolios (minimum-variance, and the long-only efficient
frontier) purely as an educational illustration. It NEVER emits a
recommendation: the tool layer presents "here is the frontier and where you
are", not "rebalance to these weights". That framing is the product's legal
line ("inform, not advise").

Long-only weights have no closed form — that's a quadratic program, solved with
scipy SLSQP. The unconstrained global minimum-variance portfolio IS closed form
(w ∝ Σ⁻¹1), but requires inverting Σ, so shrinkage-before-inversion and a
condition-number guard are mandatory (a near-singular Σ produces absurd
weights).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from app.quant.simulate import condition_number

TRADING_DAYS = 252
# Refuse to invert a covariance matrix worse-conditioned than this; the
# resulting weights would be numerical noise. Shrinkage keeps real books well
# under it.
MAX_CONDITION_NUMBER = 1e8


@dataclass
class FrontierPoint:
    annualized_vol_pct: float
    annualized_return_pct: float
    weights: list[float] | None = None


@dataclass
class FrontierResult:
    current: FrontierPoint
    min_variance: FrontierPoint
    frontier: list[FrontierPoint]  # long-only, ascending risk
    tickers: list[str]
    condition_number: float
    note: str | None = None


def _annualize_vol(daily_var: float) -> float:
    return float(np.sqrt(max(daily_var, 0.0)) * np.sqrt(TRADING_DAYS))


def _annualize_ret(daily_mean: float) -> float:
    return float(daily_mean * TRADING_DAYS)


def _port_stats(cov, mean, w):
    daily_var = float(w @ cov @ w)
    daily_mean = float(mean @ w)
    return _annualize_vol(daily_var), _annualize_ret(daily_mean)


def long_only_min_variance(cov: np.ndarray) -> np.ndarray:
    """Long-only global minimum-variance weights via SLSQP (sum=1, w≥0)."""
    n = cov.shape[0]
    w0 = np.full(n, 1.0 / n)
    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bounds = [(0.0, 1.0)] * n
    res = minimize(
        lambda w: float(w @ cov @ w),
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 500},
    )
    w = np.clip(res.x, 0.0, None)
    return w / w.sum()


def _long_only_target_return(cov: np.ndarray, mean: np.ndarray, target: float) -> np.ndarray | None:
    """Min-variance long-only weights achieving at least ``target`` daily mean."""
    n = cov.shape[0]
    w0 = np.full(n, 1.0 / n)
    constraints = [
        {"type": "eq", "fun": lambda w: w.sum() - 1.0},
        {"type": "ineq", "fun": lambda w, t=target: float(mean @ w) - t},
    ]
    bounds = [(0.0, 1.0)] * n
    res = minimize(
        lambda w: float(w @ cov @ w),
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-12, "maxiter": 500},
    )
    if not res.success:
        return None
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else None


def efficient_frontier(
    cov: np.ndarray,
    mean: np.ndarray,
    current_weights: np.ndarray,
    tickers: list[str],
    *,
    n_points: int = 8,
) -> FrontierResult:
    """Current point + min-variance + long-only frontier (ascending risk)."""
    cond = condition_number(cov)
    w_cur = np.asarray(current_weights, dtype=float)
    w_cur = w_cur / w_cur.sum()
    cur_vol, cur_ret = _port_stats(cov, mean, w_cur)
    current = FrontierPoint(cur_vol * 100, cur_ret * 100, [float(x) for x in w_cur])

    if cond > MAX_CONDITION_NUMBER:
        # Too ill-conditioned to trust the optimizer's inversion-adjacent work.
        return FrontierResult(
            current=current,
            min_variance=current,
            frontier=[current],
            tickers=list(tickers),
            condition_number=cond,
            note="Covariance too ill-conditioned for a reliable frontier.",
        )

    w_mv = long_only_min_variance(cov)
    mv_vol, mv_ret = _port_stats(cov, mean, w_mv)
    min_variance = FrontierPoint(mv_vol * 100, mv_ret * 100, [float(x) for x in w_mv])

    # Sweep target returns from the min-variance return up to the best single
    # asset's mean; each target yields a long-only frontier portfolio.
    max_ret = float(mean.max())
    targets = np.linspace(float(mean @ w_mv), max_ret, n_points)
    frontier: list[FrontierPoint] = []
    seen: set[tuple[int, int]] = set()
    for t in targets:
        w = _long_only_target_return(cov, mean, t)
        if w is None:
            continue
        vol, ret = _port_stats(cov, mean, w)
        key = (round(vol * 1e4), round(ret * 1e4))
        if key in seen:
            continue
        seen.add(key)
        frontier.append(FrontierPoint(vol * 100, ret * 100, [float(x) for x in w]))
    frontier.sort(key=lambda p: p.annualized_vol_pct)

    return FrontierResult(
        current=current,
        min_variance=min_variance,
        frontier=frontier or [min_variance],
        tickers=list(tickers),
        condition_number=cond,
    )
