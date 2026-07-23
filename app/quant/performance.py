"""Risk-adjusted performance: Sharpe, Sortino, tracking error, information ratio.

Pure numpy over the reconstructed daily portfolio SIMPLE return series (see
``tailrisk.portfolio_return_series``). Ratios are annualized with the usual
√252 / ×252 conventions.

The risk-free rate enters as an ANNUAL figure and is converted to a daily rate
by dividing by ``TRADING_DAYS`` — a small, standard approximation at the daily
horizon. Sharpe and Sortino use it as the hurdle; Sortino's downside deviation
is measured against that same rate as the minimum acceptable return (MAR).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TRADING_DAYS = 252
DEFAULT_RISK_FREE_ANNUAL = 0.04  # ~13-week T-bill order of magnitude; tunable.


@dataclass
class PerformanceStats:
    annualized_return_pct: float
    annualized_vol_pct: float
    sharpe: float | None
    sortino: float | None
    tracking_error_pct: float | None
    information_ratio: float | None
    risk_free_rate_pct: float
    obs: int


def annualized_return(returns: np.ndarray) -> float:
    """Geometric annualized return from a daily simple-return series."""
    n = returns.size
    if n == 0:
        return 0.0
    growth = float(np.prod(1.0 + returns))
    if growth <= 0:
        return -1.0
    return growth ** (TRADING_DAYS / n) - 1.0


def annualized_vol(returns: np.ndarray) -> float:
    if returns.size < 2:
        return 0.0
    return float(returns.std(ddof=1)) * np.sqrt(TRADING_DAYS)


def sharpe(returns: np.ndarray, rf_annual: float = DEFAULT_RISK_FREE_ANNUAL) -> float | None:
    """Annualized Sharpe ratio: mean daily excess return / daily vol × √252."""
    if returns.size < 2:
        return None
    rf_daily = rf_annual / TRADING_DAYS
    excess = returns - rf_daily
    sd = float(returns.std(ddof=1))
    if sd == 0:
        return None
    return float(excess.mean()) / sd * np.sqrt(TRADING_DAYS)


def sortino(returns: np.ndarray, rf_annual: float = DEFAULT_RISK_FREE_ANNUAL) -> float | None:
    """Annualized Sortino ratio: excess return / downside deviation.

    Downside deviation penalizes only returns below the risk-free MAR, so a
    portfolio isn't dinged for upside volatility the way Sharpe is.
    """
    if returns.size < 2:
        return None
    rf_daily = rf_annual / TRADING_DAYS
    excess = returns - rf_daily
    downside = np.minimum(excess, 0.0)
    downside_var = float((downside**2).mean())
    if downside_var == 0:
        return None
    downside_dev = np.sqrt(downside_var)
    return float(excess.mean()) / downside_dev * np.sqrt(TRADING_DAYS)


def _aligned(port: np.ndarray, bench: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mask = ~np.isnan(bench)
    return port[mask], bench[mask]


def tracking_error(port: np.ndarray, bench: np.ndarray) -> float | None:
    """Annualized standard deviation of the active (port − benchmark) return."""
    p, b = _aligned(port, bench)
    if p.size < 2:
        return None
    active = p - b
    return float(active.std(ddof=1)) * np.sqrt(TRADING_DAYS)


def information_ratio(port: np.ndarray, bench: np.ndarray) -> float | None:
    """Annualized active return / tracking error."""
    p, b = _aligned(port, bench)
    if p.size < 2:
        return None
    active = p - b
    sd = float(active.std(ddof=1))
    if sd == 0:
        return None
    return float(active.mean()) / sd * np.sqrt(TRADING_DAYS)


def performance_stats(
    port: np.ndarray,
    bench: np.ndarray | None,
    *,
    rf_annual: float = DEFAULT_RISK_FREE_ANNUAL,
) -> PerformanceStats:
    te = tracking_error(port, bench) if bench is not None else None
    return PerformanceStats(
        annualized_return_pct=annualized_return(port) * 100,
        annualized_vol_pct=annualized_vol(port) * 100,
        sharpe=sharpe(port, rf_annual),
        sortino=sortino(port, rf_annual),
        tracking_error_pct=te * 100 if te is not None else None,
        information_ratio=information_ratio(port, bench) if bench is not None else None,
        risk_free_rate_pct=rf_annual * 100,
        obs=int(port.size),
    )
